"""Existing four-process pipeline, wired only for complete-workpiece capture/matching."""

from __future__ import annotations

import multiprocessing
import os
import queue
import time

from control.AcquisitionPreviewAdapter import AcquisitionPreviewAdapter as LidarAcquisitionProcess
from control.PlcAcquisitionAdapter import PlcAcquisitionAdapter as PlcCommunicationProcess
from control.WorkpieceProcessingAdapter import WorkpieceProcessingAdapter as DataProcessingProcess
from control.WorkpieceProcessingAdapter import TxtAcquisitionAdapter as DataProcessWorker
from control.PointCloudFileProcess import PointCloudFileProcess, resolve_txt_files
from control.RuntimeStateCollector import RuntimeStateCollector
from control.ProcessHealthMonitor import ProcessHealthMonitor
from control.UiState import DeviceState, TaskState
from model.dataprocess.DataFilter import DataFilter
from model.utils.LidarDirectionUtil import get_active_lidar_config
from model.utils.LoggerUtil import logger, manage_log_files, log_directory
from model.utils.PointCloudSaveService import PointCloudSaveService, stop_pipeline
from model.utils.TomlLoader import TomlLoader
from model.utils.UiTelemetry import UiStatusPublisher


class SubprocessRedirect:
    def __init__(self, output_queue, is_stderr=False):
        self.output_queue, self.is_stderr = output_queue, is_stderr
        self._pending = ''

    def write(self, text):
        self._pending += text
        while '\n' in self._pending:
            line, self._pending = self._pending.split('\n', 1)
            if line.strip():
                self.output_queue.put(('stderr' if self.is_stderr else 'stdout', line.rstrip('\r')))
        return len(text)

    def flush(self):
        if self._pending:
            self.output_queue.put(('stderr' if self.is_stderr else 'stdout', self._pending))
            self._pending = ''


class QtPipelineRuntime:
    def __init__(self, config_dir=None, *, control_type=2, data_path=None, data_name=None):
        if type(control_type) is not int or control_type not in (1, 2, 3):
            raise ValueError('control_type 只支持 1/2/3')
        self.control_type = control_type
        self.data_path = os.path.abspath(os.path.expanduser(data_path)) if data_path else None
        self.data_name = data_name
        self.toml_path = os.path.abspath(config_dir or os.path.join(os.getcwd(), 'model', 'tomls'))
        self.mode_config_path = os.path.join(self.toml_path, 'ModeConfig.toml')
        self.mode_config = TomlLoader.load(self.mode_config_path)
        self._validate_mode(self.mode_config)
        self.strategy_name = 'complete_workpiece'
        self.read_data_config = TomlLoader.load(os.path.join(self.toml_path, 'ReadDataConfig.toml'))
        self.sys_config = TomlLoader.load(os.path.join(self.toml_path, 'SystemConfig.toml'))
        self.chain_speed = int(self.read_data_config.get('lidar_scan_speed', 25))
        self.process_heartbeat_interval_s = float(self.read_data_config.get('process_heartbeat_interval_s', 1))
        self.health_monitor = ProcessHealthMonitor(float(self.read_data_config.get('process_unresponsive_timeout_s', 60)))
        self.control_queue = multiprocessing.Queue()
        self.log_queue = multiprocessing.Queue()
        self.ui_status_queue = multiprocessing.Queue(maxsize=32)
        self.result_queue = multiprocessing.Queue(maxsize=128)
        self.collector = RuntimeStateCollector(self.log_queue, DataFilter(), float(self.read_data_config.get('point_cloud_preview_voxel_mm', 10)))
        self.processes, self.process_heartbeats = [], {}
        self.save_service = self.lidar_acquisition = self.plc_handler = self.data_processor = None
        self.file_loader = None
        self._stop_event = None
        self.running = False
        self.starting = False
        self._feedback, self._faults = {}, []
        self.latest_result = None
        self._display_result = None

    @staticmethod
    def _validate_mode(config):
        if type(config.get('strategy_name')) is not int or config['strategy_name'] != 2:
            raise ValueError('本版本仅支持 ModeConfig.toml 中 strategy_name = 2')

    @staticmethod
    def _heartbeat():
        return multiprocessing.Value('d', time.monotonic())

    def _register_and_start(self, process, heartbeat):
        self.processes.append(process)
        self.process_heartbeats[process] = heartbeat
        process.stdout = SubprocessRedirect(self.log_queue)
        process.stderr = SubprocessRedirect(self.log_queue, True)
        process.daemon = True
        process.start()

    def start_pipeline(self):
        if self.running:
            return
        if self.has_live_workers():
            raise RuntimeError('仍有工作进程未退出')
        self._validate_mode(TomlLoader.load(self.mode_config_path))
        # Validate recognition configuration before opening devices; model code stays untouched.
        if self.control_type != 3:
            TomlLoader.load(os.path.join(self.toml_path, 'CabinetTypeConfig.toml'))
        if self.control_type == 2 and not get_active_lidar_config(self.sys_config):
            raise ValueError('SystemConfig.toml 至少配置一个激光方向')
        files = resolve_txt_files(self.data_path, self.data_name) if self.control_type in (1, 3) else ()
        self.starting = True
        self._feedback.clear()
        self._faults.clear()
        self.latest_result = None
        self._display_result = None
        self.ui_status_queue = multiprocessing.Queue(maxsize=32)
        self.result_queue = multiprocessing.Queue(maxsize=128)
        raw_data_queue = multiprocessing.Queue()  # Original LiDAR puts must not block behind matching/status traffic.
        pulse_queue = multiprocessing.Queue(maxsize=32)
        viz_queue = multiprocessing.Queue(maxsize=2)
        self.collector.set_visualization_queue(viz_queue)
        self.running = True
        try:
            if self.control_type == 3:
                heartbeat = self._heartbeat()
                self.file_loader = PointCloudFileProcess(files, viz_queue, self.ui_status_queue,
                                                         heartbeat, self.process_heartbeat_interval_s, read_data_config=self.read_data_config)  # type: ignore
                self._register_and_start(self.file_loader, heartbeat)
                return
            manage_log_files(log_directory)
            self._stop_event = multiprocessing.Event()
            if self.control_type == 2:
                self.save_service = PointCloudSaveService.from_config_file(
                    os.path.join(self.toml_path, 'ReadDataConfig.toml'), os.path.join(os.getcwd(), 'data', 'points'), viz_queue)
                self.processes.append(self.save_service.worker)
                self.process_heartbeats[self.save_service.worker] = self.save_service.heartbeat
                self.save_service.start()
                self._stop_event = self.save_service.stop_event
            stop_event = self._stop_event
            if self.control_type in (1, 2):
                heartbeat = self._heartbeat()
                self.data_processor = DataProcessingProcess(raw_data_queue, self.result_queue, viz_queue,
                                                            config_dir=self.toml_path, heartbeat=heartbeat,
                                                            heartbeat_interval_s=self.process_heartbeat_interval_s, stop_event=stop_event)
                self._register_and_start(self.data_processor, heartbeat)
            heartbeat = self._heartbeat()
            self.plc_handler = PlcCommunicationProcess.create(self.strategy_name, raw_data_queue, pulse_queue,
                                                              self.control_queue, heartbeat=heartbeat, heartbeat_interval_s=self.process_heartbeat_interval_s,
                                                              config_dir=self.toml_path, stop_event=stop_event)
            self.plc_handler.ui_status = UiStatusPublisher(self.ui_status_queue, 'plc')
            self._register_and_start(self.plc_handler, heartbeat)
            heartbeat = self._heartbeat()
            if self.control_type == 1:
                self.file_loader = DataProcessWorker(raw_data_queue, pulse_queue, None, self.data_path,
                                                     data_name=self.data_name, strategy_name=self.strategy_name, config_dir=self.toml_path,
                                                     heartbeat=heartbeat, heartbeat_interval_s=self.process_heartbeat_interval_s, stop_event=stop_event,
                                                     result_queue=self.result_queue)
                if not self.file_loader._discover_point_cloud_datasets():
                    raise ValueError('未找到符合原点配置的 TXT 数据集')
                self._register_and_start(self.file_loader, heartbeat)
            else:
                self.lidar_acquisition = LidarAcquisitionProcess(pulse_queue, raw_data_queue, viz_queue,
                                                                 get_active_lidar_config(self.sys_config), self.toml_path, strategy_name=self.strategy_name,
                                                                 heartbeat=heartbeat, heartbeat_interval_s=self.process_heartbeat_interval_s,
                                                                 save_pool_descriptor=self.save_service.pool.descriptor, save_task_queue=self.save_service.task_queue,  # type: ignore
                                                                 save_ack_queue=self.save_service.ack_queue, save_status_queue=self.save_service.status_queue,  # type: ignore
                                                                 stop_event=stop_event)
                self.lidar_acquisition.ui_status = UiStatusPublisher(self.ui_status_queue, 'lidar')
                self._register_and_start(self.lidar_acquisition, heartbeat)
            logger.info('完整工件采集、匹配与点云保存管线已启动，无运动执行')
        finally:
            self.starting = False

    def stop_pipeline(self):
        self.running = False
        if self._stop_event is not None:
            self._stop_event.set()
        if not self.processes and self.save_service is None:
            return []
        # Preserve original stop order: stop acquisition, drain point-cloud saves, then release pool.
        started = [process for process in self.processes if process.pid is not None]
        errors = stop_pipeline(started, self.lidar_acquisition if self.lidar_acquisition is not None and self.lidar_acquisition.pid is not None else None,
                               self.save_service, float(self.read_data_config.get('point_cloud_acquisition_stop_timeout_s', 15)),  # type: ignore
                               float(self.read_data_config.get('point_cloud_save_shutdown_timeout_s', 120)))  # type: ignore
        if self.has_live_workers():
            return list(errors or []) + ['部分进程未退出，禁止重新启动']
        self.processes, self.process_heartbeats = [], {}
        self.save_service = self.lidar_acquisition = self.plc_handler = self.data_processor = None
        self.file_loader = None
        self._stop_event = None
        self._feedback.clear()
        self.collector.set_visualization_queue(None)
        return errors

    def has_live_workers(self):
        return any(process.pid is not None and process.is_alive() for process in self.processes)

    def poll(self):
        snapshot = self.collector.poll()
        for _ in range(32):
            try:
                message = self.ui_status_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, dict):
                self._feedback[message.get('source')] = message
        results = []
        for _ in range(32):
            try:
                message = self.result_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, dict):
                self.latest_result = message
                results.append(message)
                if message.get('status') == 'error':
                    snapshot['fault'] = message.get('message', '数据处理异常')
        snapshot['results'] = results
        if self.running and not self.starting:
            fault = self.health_monitor.check(self.processes, self.process_heartbeats, self.save_service, now=time.monotonic())
            if fault:
                snapshot['fault'] = fault.detail
        devices = []
        now = time.monotonic()
        for source, name, worker in (('plc', 'PLC', self.plc_handler), ('lidar', '激光', self.lidar_acquisition)):
            message = self._feedback.get(source, {})
            fresh = 0 <= now - float(message.get('timestamp', -10)) <= 5
            alive = worker is not None and worker.pid is not None and worker.is_alive()
            connected = bool(alive and fresh and message.get('connected'))
            devices.append(DeviceState(name, connected, '已连接' if connected else ('连接中/等待反馈' if self.running else '未连接')))
        snapshot.update(devices=tuple(devices), alarms=tuple(self._faults[-10:]),
                        chain_status='循环采集匹配中' if self.running else '待机')
        if devices[0].online:
            feedback = self._feedback.get('plc', {})
            snapshot['chain_position'] = int(feedback.get('pulse', 0))
            if self.running:
                snapshot['chain_status'] = {'moving_forward': '链条前进', 'moving_reverse': '链条后退',
                                            'stopped': '链条停止'}.get(feedback.get('motion'), '运行中')
        # GUI ID and cloud share one processing message; result_queue remains the independent SDK channel.
        if snapshot.get('preview_result') is not None:
            self._display_result = snapshot['preview_result']
        elif snapshot.get('updated'):
            self._display_result = None
            snapshot.update(matched_id=None, workpiece_index=0, match_status='waiting')
        if self._display_result:
            snapshot.update(matched_id=self._display_result.get('identifier'), workpiece_index=self._display_result.get('sequence', 0),
                            match_status=self._display_result.get('status', 'waiting'))
        snapshot['task'] = TaskState(name='完整工件采集与匹配', stage=snapshot['chain_status'])
        if self.control_type == 1:
            snapshot['devices'] = (devices[0], DeviceState('激光', False, 'TXT 联调 · 不启用激光'))
            snapshot['chain_status'] = 'TXT 联调 PLC' if self.running else '待机'
            snapshot['task'] = TaskState(name='TXT 完整工件匹配', stage=snapshot['chain_status'])
        elif self.control_type == 3:
            feedback = self._feedback.get('files', {})
            detail = feedback.get('detail', '等待导入 TXT 点云' if self.running else '待机')
            snapshot['chain_status'] = detail
            snapshot['task'] = TaskState(name='TXT 点云查看', stage=detail)
            snapshot['devices'] = (DeviceState('PLC', False, '文件查看 · 不启用'), DeviceState('激光', False, '文件查看 · 不启用'))
            if feedback.get('state') == 'error':
                snapshot['fault'] = detail
        if snapshot.get('fault') and snapshot['fault'] not in self._faults:
            self._faults.append(snapshot['fault'])
        snapshot['alarms'] = tuple(self._faults[-10:])
        return snapshot

    # Legacy upper-layer command entry points remain as no-ops; no model motion path is invoked.
    def save_chain_speed(self, speed):
        pass

    def send_control(self, command):
        pass

    def is_password_required(self):
        return False

    def verify_password(self, password):
        return True
