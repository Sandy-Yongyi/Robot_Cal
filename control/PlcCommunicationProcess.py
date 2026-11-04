import os
import sys
import math
import time
import multiprocessing
from typing import Any, cast
from model.utils.LoggerUtil import check_and_rotate_log, logger
from model.plc.PlcCommon import PlcManager
from model.utils.TomlLoader import TomlLoader
from model.plc.MovingFrameData import ReceiveMovingFrameData, SendMovingFrameData
from model.utils.StrategyUtil import is_complete_workpiece_mode, is_continuous_bidirectional_mode, validate_strategy_name
from model.utils.MachineConfigUtil import get_machine_config_path, normalize_machine_config_offsets
from model.utils.ProcessHeartbeat import ProcessHeartbeat
from model.utils.UiTelemetry import UiStatusPublisher


class SimulatedPlcData:
    def __init__(self):
        self.ChainPulse = 0.0
        self.ChainSpeed = 0
        self.ChainStatus = "stopped"
        self.ChainCountCM = 0
        self.Status = 1
        self.Operate = 0
        self.AxisList = []


class PlcCommunicationProcess(multiprocessing.Process):
    def _text(self, chinese, english):
        return english if is_continuous_bidirectional_mode(self.strategy_name) else chinese

    def __init__(self, raw_data_queue, pulse_queue, control_queue, machine_data_queue=None, strategy_name="frame_by_frame", heartbeat=None, heartbeat_interval_s: float = 1.0):
        super().__init__()
        self.raw_data_queue = raw_data_queue
        self.pulse_queue = pulse_queue
        self.control_queue = control_queue
        self.machine_data_queue = machine_data_queue  # 用于 complete_workpiece 模式
        self.strategy_name = validate_strategy_name(strategy_name)
        self._heartbeat = ProcessHeartbeat(heartbeat, heartbeat_interval_s)
        self.ui_status = UiStatusPublisher(None, "plc")

        self.config_dir = os.path.join(os.getcwd(), "model", "tomls")
        self.plc_config_path = os.path.join(self.config_dir, "PlcConfig.toml")
        self.read_data_config_path = os.path.join(self.config_dir, "ReadDataConfig.toml")
        self.machine_config_path = get_machine_config_path(self.config_dir, self.strategy_name)
        self.spray_config_path = os.path.join(self.config_dir, "SprayConfig.toml")
        self.system_config_path = os.path.join(self.config_dir, "SystemConfig.toml")
        self.mode_config_path = os.path.join(self.config_dir, "ModeConfig.toml")

        self.plc_config = cast(dict[str, Any], {})
        self.plc_manager = cast(PlcManager, None)
        self.read_data_config = cast(dict[str, Any], {})
        self.machine_config = cast(dict[str, Any], {})
        self.runtime_spray_config = cast(dict[str, Any], {})
        self.mode_config = cast(dict[str, Any], {})
        pass  # 已删除的运动对象不再构造。
        pass  # 已删除的运动对象不再构造。
        pass  # 已删除的运动对象不再构造。
        pass  # 已删除的运动对象不再构造。

        self.max_fifo = 0
        self.max_retries = 3
        self.diff_start_pulse = 7
        self.pulse_to_mm = 1
        self.fifo_unit_mm = 2
        self.workpiece_fifo_step_mm = 5
        self.plc_connected = False
        self.plc_reconnect_pending = False
        self.plc_connection_generation = 0
        self.pulse_history = []
        self.chain_motion_status = "stopped"
        self.lidar_status = 0
        self.last_lidar_status_log_time = 0.0
        self.last_synced_chain_fifo = None
        self.current_cycle_raw_shift_steps = 0
        self.last_raw_frame_time = 0.0
        self.last_raw_frame_fifo = None
        self.raw_data_timeout_active = False
        self.raw_data_timeout_s = 0.5
        self.total_mm = 0.0
        self.last_workpiece_chain_mm = {}
        self.last_workpiece_chain_mm_residual = {}

        # 运行时设备参数
        self.runtime_machine_config = {}
        self.runtime_param_keys = {
            "tracking", "y_move_min", "y_move_max",
            "x_pos_speed", "x_recip_speed", "y_pos_speed", "y_recip_speed", "z_zeroing_speed",
            "z_spray_position", "x_status_offset",
            "outside_total_cycles", "inside_total_cycles",
            "recip_reduce_distance",
            "out_front_x_offset", "out_after_x_offset", "in_front_x_offset", "in_after_x_offset",
            "origin_pos", "out_up_y_offset", "out_down_y_offset",
            "in_up_y_offset", "in_down_y_offset", "out_z_front_offset", "out_z_after_offset",
            "search_front_z_offset", "search_after_z_offset", "in_z_front_offset", "in_z_after_offset", "z_back_speed",
        }

        # 计算设备数量
        self.num_devices = 0

        # 模拟模式相关
        self.simulation_mode = False  # 启用模拟模式
        self.last_simulation_time = 0  # 记录上次模拟处理时间

        # 设备运动状态跟踪
        self.device_origin_complete = {}  # 跟踪每个设备是否全部轴回0
        self.last_operate_state = 0  # 记录上一次的Operate状态，用于检测设备状态变化
        self.device_returning_to_origin = {}  # 跟踪每个设备是否正在回原点
        # 标准输出重定向
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def _pulse_to_chaincountcm(self, pulse):
        """将 pulse 换算为 chaincountcm。"""
        pulse_to_mm = float(self.pulse_to_mm or 1)
        return int(round(float(pulse) / pulse_to_mm / 10))

    def _resolve_max_fifo(self):
        """基于 pulse 重置阈值推导 chaincountcm 的最大值。"""
        return max(1, self._pulse_to_chaincountcm(self.max_pulse))

    def _get_fifo_step_delta(self, last_fifo: int, current_fifo: int) -> int:
        """计算 FIFO 的有符号步数，支持 max_fifo -> 0 的正常回绕。"""
        ring_size = self.max_fifo + 1
        last_fifo = int(last_fifo) % ring_size
        current_fifo = int(current_fifo) % ring_size
        forward_gap = (current_fifo - last_fifo) % ring_size

        if forward_gap == 0:
            return 0

        # 例如 max_fifo=3018 时：3018 -> 0 的 forward_gap 为 1，视为正常前进一帧。
        if forward_gap <= ring_size // 2:
            return forward_gap

        return forward_gap - ring_size

    @staticmethod
    def create(strategy_name, raw_data_queue, pulse_queue, control_queue, machine_data_queue=None, heartbeat=None, heartbeat_interval_s: float = 1.0):
        """
        工厂方法：根据采集策略创建 PlcCommunicationProcess 实例
        Args:
            strategy_name: 采集策略名称 ('continuous_bidirectional', 'frame_by_frame', 'complete_workpiece')
            raw_data_queue: 原始数据队列
            pulse_queue: 脉冲数据队列
            machine_data_queue: 机器数据队列（仅用于 complete_workpiece 模式）
        Returns:
            PlcCommunicationProcess 实例
        """
        validate_strategy_name(strategy_name)
        if strategy_name == "complete_workpiece":
            if machine_data_queue is None:
                raise ValueError("machine_data_queue is required for 'complete_workpiece' strategy")
            return PlcCommunicationProcess(
                raw_data_queue,
                pulse_queue,
                control_queue,
                machine_data_queue=machine_data_queue,
                strategy_name=strategy_name,
                heartbeat=heartbeat,
                heartbeat_interval_s=heartbeat_interval_s,
            )
        else:
            # continuous_bidirectional 和 frame_by_frame 使用 raw_data_queue
            return PlcCommunicationProcess(raw_data_queue, pulse_queue, control_queue, strategy_name=strategy_name, heartbeat=heartbeat, heartbeat_interval_s=heartbeat_interval_s)

    def run(self):
        logger.info(f"PlcCommunicationProcess.run() entered, pid={os.getpid()}")
        self._heartbeat.touch(force=True)
        # 重定向输出
        if hasattr(self, "stdout"):
            sys.stdout = self.stdout
        if hasattr(self, "stderr"):
            sys.stderr = self.stderr

        try:
            self._initialize_runtime_state()
            # 如果不是模拟模式，初始化PLC连接
            if not self.simulation_mode:
                if not self._initialize_connection():
                    return  # 连接失败退出进程
            # time.sleep(5)  # TODO: 调试时使用，正式环境可移除或调整为更短时间，确保PLC连接稳定后再进入主循环
            # 主处理循环
            self._run_main_loop()

        except Exception as e:
            logger.error(f"Critical error in PLC handler: {str(e)}")
            self._heartbeat.sleep(1)
        finally:
            if self.plc_connected:
                self.plc.disconnect(self.connection_type)

    def _initialize_runtime_state(self):
        """在子进程内初始化重对象，避免 spawn 时在父进程构造/序列化大量数据。"""
        logger.info(f"Initialize PLC runtime with strategy_name={self.strategy_name}")
        self.plc_config = TomlLoader.load(self.plc_config_path)
        self.plc_manager = PlcManager(self.plc_config_path)
        self.read_data_config = TomlLoader.load(self.read_data_config_path)
        self.pulse_to_mm = float(self.read_data_config["pulse_to_mm"])
        if not math.isfinite(self.pulse_to_mm) or self.pulse_to_mm <= 0:
            raise ValueError(self._text("pulse_to_mm必须为正数", "pulse_to_mm must be a positive finite number."))
        self.machine_config = normalize_machine_config_offsets(TomlLoader.load(self.machine_config_path))
        if is_continuous_bidirectional_mode(self.strategy_name):
            self.runtime_spray_config = TomlLoader.load(self.spray_config_path)
            self.frame_queue_manager = self._create_frame_queue_manager()
            self._initialize_device_runtime_state(return_to_safe=True)
            self.continuous_scan_pending = False
            self.continuous_lidar_ready = False
            self.continuous_reported_error = ""
            logger.info("Continuous bidirectional mode initialized; lidar axes home before scanning when required.")
            return
        self.runtime_spray_config = TomlLoader.load(self.spray_config_path)
        self.mode_config = TomlLoader.load(self.mode_config_path)
        spray_mode = int(self.mode_config.get("spray_mode", 0) or 0)
        mode_text = "手动模式" if spray_mode == 1 else "自动模式"
        logger.info(f"PLC runtime spray mode: {mode_text} (spray_mode={spray_mode})")

        self.max_pulse = self.read_data_config.get("max_pulse", 160000)
        self.max_retries = self.read_data_config.get("plc_send_max_retries", 3)
        self.diff_start_pulse = self.read_data_config.get("diff_start_pulse", 7)
        self.fifo_unit_mm = self.read_data_config.get("fifo_unit_mm", 2)
        self.workpiece_fifo_step_mm = float(self.read_data_config.get("workpiece_fifo_step_mm", 5) or 5)
        self.max_fifo = self._resolve_max_fifo()
        self.raw_data_timeout_s = float(self.read_data_config.get("raw_data_timeout_s", 10) or 10)
        self.total_mm = float(self.max_pulse) / float(self.pulse_to_mm or 1)
        self.last_raw_frame_time = time.time()
        self.last_raw_frame_fifo = None
        self.last_synced_chain_fifo = None
        self.current_cycle_raw_shift_steps = 0
        self.raw_data_timeout_active = False
        self.reconnect_raw_packet_floor_fifo = None
        self.last_workpiece_chain_mm = {}
        self.last_workpiece_chain_mm_residual = {}

        self.frame_queue_manager = self._create_frame_queue_manager()

        self._initialize_device_runtime_state(return_to_safe=False)

    def _initialize_device_runtime_state(self, return_to_safe: bool):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _build_runtime_machine_config(self, cfg: dict) -> dict:
        runtime_cfg = {}
        for key in self.runtime_param_keys:
            if key in cfg:
                runtime_cfg[key] = cfg[key]

        flat_cfg = cfg.get("flat")
        if isinstance(flat_cfg, dict):
            runtime_cfg["flat"] = {key: value for key, value in flat_cfg.items() if key in self.runtime_param_keys}
        return runtime_cfg

    def _create_frame_queue_manager(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _initialize_connection(self):
        """初始化PLC连接"""
        try:
            # 获取配置信息
            self.connection_type = self.plc_config["1"]["connection_type"]
            self.plc = self.plc_manager.get_plc("1")

            # 初始连接
            if not self.plc.connect(self.connection_type):
                # 初始连接失败后尝试重连
                if not self._handle_connection_error(self.plc):
                    logger.error("PLC initial connection failed permanently. Exiting process.")
                    print(self._text("PLC连接失败，请检查连接并重新运行软件", "PLC connection failed. Check the connection and restart the software."))
                    return False
            print(self._text("PLC连接成功.", "PLC connected."))
            self.plc_connected = True

            return True

        except Exception as e:
            logger.error(f"Connection initialization failed: {str(e)}")
            return False

    def _run_main_loop(self):
        """主处理循环，同时处理模拟和实际模式"""
        while True:
            time.sleep(0.09)  # 减少CPU占用
            self._heartbeat.touch()
            if not self._update_plc_data():
                continue
            if is_continuous_bidirectional_mode(self.strategy_name):
                self._process_continuous_scan_cycle()
            elif is_complete_workpiece_mode(self.strategy_name):
                self._process_workpiece_data()
                self._sync_complete_workpiece_positions()
            else:
                self.current_cycle_raw_shift_steps = 0
                self._process_frame_data()
                self._sync_frame_queue_with_chain_fifo()
            self._update_enable_value()
            check_and_rotate_log()
            # 处理数据发送，发送给PLC
            if is_continuous_bidirectional_mode(self.strategy_name):
                self._publish_continuous_scan_state()

    def _update_plc_data(self):
        try:
            if is_continuous_bidirectional_mode(self.strategy_name):
                if self.simulation_mode:
                    self.plc_data = ReceiveMovingFrameData()
                else:
                    self.plc_data = self.plc.scan(self.connection_type)
                logger.info(f"continuous_bidirectional_mode: Status={self.plc_data.Status}, Operate={self.plc_data.Operate}, "
                            f"HeartBeat={self.plc_data.HeartBeat}, AxisList={self.plc_data.AxisList}")
                self._publish_ui_status(connected=True)
                return True

            # 模拟模式处理逻辑
            if self.simulation_mode:
                current_time = time.time()
                # 每0.04秒处理一次, 对应链速1.5
                if current_time - self.last_simulation_time >= 0.3:
                    if not hasattr(self, "simulated_plc_data"):
                        self.simulated_plc_data = SimulatedPlcData()

                    # 当前 fifo 使用 pulse 换算后的 chaincountcm，需与 pulse 同步回绕
                    pulse_step = max(1, int(round(float(self.fifo_unit_mm) * float(self.pulse_to_mm))))

                    self.simulated_plc_data.ChainPulse = self._advance_simulated_pulse(self.simulated_plc_data.ChainPulse, pulse_step)
                    self.simulated_plc_data.ChainCountCM = self._pulse_to_chaincountcm(self.simulated_plc_data.ChainPulse)

                    self.plc_data = self.simulated_plc_data
                    self.last_simulation_time = current_time
                    self._update_chain_status(self.plc_data.ChainCountCM, self.plc_data.ChainPulse)

            # 实际PLC模式处理逻辑
            else:
                # 接收并处理PLC数据
                self.plc_data = self.plc.scan(self.connection_type)
                chaincountcm = self._pulse_to_chaincountcm(self.plc_data.ChainPulse)
                setattr(self.plc_data, "ChainCountCM", chaincountcm)
                self._update_chain_status(chaincountcm, self.plc_data.ChainPulse)

                logger.info(f"plc tcp recv data: self.plc_data.AxisList: {self.plc_data.AxisList}")
                # # 处理脉冲和定位数据
                # self.pulse_queue.put({'pulse': self.plc_data.ChainPulse, 'fifo': self.plc_data.ChainCountCM})

            self._publish_ui_status(connected=True)
            return True

        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            if is_continuous_bidirectional_mode(self.strategy_name):
                self.pulse_queue.put({"pulse": -999, "fifo": 0, "status": "stopped"})
            # 处理连接异常
            if not self.simulation_mode:
                logger.error(f"Connection error during operation: {str(e)}")
                self._mark_plc_disconnected()
                # 尝试重连
                if not self._handle_connection_error(self.plc):
                    logger.error("Failed to reconnect after connection loss. Exiting process.")
            return False  # 本轮通信失败，不使用旧PLC数据继续计算或发送

        except Exception as e:
            # 处理其他异常
            logger.error(f"Unexpected error: {str(e)}")
            self._publish_ui_status(connected=False, force=True)
            return False

    def _publish_ui_status(self, connected: bool, force: bool = False):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _advance_simulated_pulse(self, current_pulse, pulse_step):
        """仿真脉冲：递增到 max_pulse 时重置为 0。"""
        next_pulse = int(current_pulse) + int(pulse_step)
        reset_threshold = int(self.max_pulse)
        return 0 if next_pulse >= reset_threshold else next_pulse

    def _reset_raw_data_timeout_timer(self, fifo=None):
        """重置激光数据超时计时，供链条重新启动或收到新帧时调用。"""
        self.last_raw_frame_time = time.time()
        if fifo is not None:
            self.last_raw_frame_fifo = fifo
        self.raw_data_timeout_active = False

    def _update_chain_status(self, fifo, pulse):
        self.pulse_history.append(pulse)
        if len(self.pulse_history) > 5:
            self.pulse_history.pop(0)

        status = "stopped"
        if len(self.pulse_history) == 5:
            pulse_delta = float(self.pulse_history[-1]) - float(self.pulse_history[0])
            half_pulse_range = float(self.max_pulse) / 2.0
            # 脉冲计数由最大值回到0时仍是正向运动，例如159997 -> 4的实际增量为7。
            if pulse_delta < -half_pulse_range:
                pulse_delta += float(self.max_pulse)
            elif pulse_delta > half_pulse_range:
                pulse_delta -= float(self.max_pulse)
            # logger.info(f"pulse_history: {self.pulse_history}")
            # 停止
            if len(set(self.pulse_history)) == 1:
                status = "stopped"
            elif pulse_delta > self.diff_start_pulse:
                status = "moving_forward"
            elif pulse_delta < -self.diff_start_pulse:
                status = "moving_reverse"

        last_status = getattr(self, "chain_motion_status", None)
        self.chain_motion_status = status
        if hasattr(self, "plc_data") and self.plc_data is not None:
            setattr(self.plc_data, "ChainStatus", status)

        if last_status != status:
            if status in ("moving_forward", "moving_reverse") and last_status == "stopped":
                self._reset_raw_data_timeout_timer(fifo=fifo)
        logger.info(f"PLC chain status changed: pulse={pulse}, fifo={fifo}, status={status}")
        self.pulse_queue.put({
            "pulse": pulse,
            "fifo": fifo,
            "status": status,
            "plc_generation": self.plc_connection_generation,
        })

    def _update_lidar_status_from_packet(self, fifo_data: dict):
        if "lidar_status" in fifo_data:
            self._update_lidar_status(int(fifo_data.get("lidar_status", 0) or 0))

    def _should_skip_raw_packet(self) -> bool:
        return int(getattr(self, "lidar_status", 0) or 0) in (1, 2, 3)

    def _process_frame_data(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _should_drop_reconnect_raw_packet(self, fifo_data: dict) -> bool:
        """重连补空后丢弃不晚于同步基准的旧包，避免队列被再次推进。"""
        floor_fifo = getattr(self, "reconnect_raw_packet_floor_fifo", None)
        if floor_fifo is None or "fifo" not in fifo_data:
            return False

        packet_fifo = int(fifo_data.get("fifo", 0) or 0)
        if self._get_fifo_step_delta(floor_fifo, packet_fifo) <= 0:
            logger.warning(
                f"Ignore stale lidar frame after PLC reconnect: floor={floor_fifo}, packet={packet_fifo}"
            )
            return True

        self.reconnect_raw_packet_floor_fifo = None
        return False

    def _process_continuous_scan_cycle(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _publish_continuous_scan_state(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _process_workpiece_data(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _update_workpiece_tracking_after_push(self, direction: str, sn: int, insert_index: int, shifted: bool):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _build_machine_workpiece(self, block_data, sn: int):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _handle_frame_packet_received(self, fifo_data: dict, repeat_count: int):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _push_empty_frames(self, repeat_count: int):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _sync_frame_queue_with_chain_fifo(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _resync_frame_queue_after_plc_reconnect(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _sync_complete_workpiece_positions(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _calc_delta_mm_with_wrap(self, current_mm: float, prev_mm: float) -> float:
        delta = float(current_mm) - float(prev_mm)
        if delta < -(self.total_mm / 2):
            delta += self.total_mm
        elif delta > (self.total_mm / 2):
            delta -= self.total_mm
        return delta

    def _update_raw_data_watchdog(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _update_lidar_status(self, new_status: int):
        """更新激光状态，并按要求输出节流日志。"""
        new_status = int(new_status or 0)
        old_status = int(getattr(self, "lidar_status", 0) or 0)
        self.lidar_status = new_status

        if new_status in (1, 2, 3):
            if old_status not in (1, 2, 3):
                self._clear_all_frame_queues()
                cleared_count = self._clear_pending_raw_data_queue()
                logger.warning(f"Lidar abnormal, cleared frame queues and dropped {cleared_count} pending raw packets")
            now = time.time()
            if new_status != old_status:
                self.last_lidar_status_log_time = 0.0
            if now - self.last_lidar_status_log_time >= 10:
                if new_status == 1:
                    msg = "激光有遮挡，已清空数据队列并禁止设备运动"
                elif new_status == 2:
                    msg = "激光异常，已清空数据队列并禁止设备运动"
                else:
                    msg = "激光断连，已清空数据队列并禁止设备运动"
                print(msg)
                logger.warning(msg)
                self.last_lidar_status_log_time = now
        elif old_status in (1, 2, 3):
            msg = "激光正常了，设备恢复正常运动"
            print(msg)
            logger.info(msg)
            self.last_lidar_status_log_time = 0.0

    def _clear_all_frame_queues(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _clear_pending_raw_data_queue(self):
        cleared_count = 0
        try:
            while True:
                self.raw_data_queue.get_nowait()
                cleared_count += 1
        except Exception:
            pass
        return cleared_count

    def _update_enable_value(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _handle_config_update(self, sn: int, config: dict):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _handle_spray_update(self, spray_cfg: dict):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _axis_to_moving_frame(self):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def after_spray_complete(self, direction: str, sn: int):
        pass  # 运动、停用策略或已删除模块的入口保留。

    def _handle_connection_error(self, plc):
        """处理连接异常，支持初始连接和已连接状态的断开重连"""
        self.plc_connected = False
        max_retries = self.read_data_config["plc_connect_max_retries"]
        for attempt in range(max_retries):
            try:
                self._heartbeat.touch()
                print(self._text(f"PLC连接失败，正在尝试第{attempt+1}次重连...", f"PLC connection failed; reconnect attempt {attempt+1}..."))
                try:
                    plc.disconnect(connection_type=self.connection_type)
                except Exception:
                    pass
                self._heartbeat.sleep(10)
                # 尝试重连
                if plc.connect(connection_type=self.connection_type):
                    logger.info("PLC reconnected successfully")
                    print(self._text("PLC重连成功.", "PLC reconnected."))
                    self.plc_connected = True
                    return True
            except Exception as e:
                logger.error(f"Reconnect attempt {attempt+1} failed: {str(e)}")

        logger.error(f"Failed to reconnect to PLC after {max_retries} attempts")
        return False

    def _mark_plc_disconnected(self):
        """立即暂停链条相关计时，并通知激光进程 PLC 已断连。"""
        self.plc_connected = False
        self.chain_motion_status = "stopped"
        self._publish_ui_status(connected=False, force=True)
        self.raw_data_timeout_active = False
        self.pulse_history.clear()
        if not self.plc_reconnect_pending:
            self.plc_connection_generation += 1
        self.plc_reconnect_pending = True

        plc_data = getattr(self, "plc_data", None)
        if plc_data is not None:
            setattr(plc_data, "ChainStatus", "stopped")
        fifo = int(getattr(plc_data, "ChainCountCM", 0) or 0)
        self.pulse_queue.put({
            "pulse": -999,
            "fifo": fifo,
            "status": "stopped",
            "plc_generation": self.plc_connection_generation,
        })
        logger.warning(f"PLC disconnected, lidar acquisition paused at fifo={fifo}")
