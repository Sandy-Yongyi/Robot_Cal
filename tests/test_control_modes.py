import queue
import contextlib
import io
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from qt_main import parse_launch_arguments
from control.QtPipelineRuntime import QtPipelineRuntime
from control.PointCloudFileProcess import load_txt_cloud, resolve_txt_files
from control.DataProcessWorker import DataProcessWorker


class ControlModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'combined_sample.txt'
        np.savetxt(self.file, [[1, 2, 3], [4, 5, 6]])

    def test_launch_arguments_preserve_configured_control_and_data(self):
        args = parse_launch_arguments([], control_type=1, data_path=str(self.file), data_name='sample.txt')
        self.assertEqual((args.control_type, args.data_path, args.data_name), (1, str(self.file), 'sample.txt'))
        args = parse_launch_arguments(['--control-type', '3', '--data-path', str(self.file)])
        self.assertEqual(args.control_type, 3)

    def test_replay_and_file_view_require_paths(self):
        for code in (1, 3):
            with self.subTest(code=code), self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    parse_launch_arguments(['--control-type', str(code)])

    def test_text_cloud_loading_is_available(self):
        files = resolve_txt_files(str(self.file))
        np.testing.assert_array_equal(load_txt_cloud(files), [[1, 2, 3], [4, 5, 6]])
        loader = DataProcessWorker(queue.Queue(), queue.Queue(), queue.Queue(), str(self.file),
                                   strategy_name='complete_workpiece')
        self.assertTrue(loader._discover_point_cloud_datasets())

    def test_view_only_starts_only_file_process(self):
        with patch('control.QtPipelineRuntime.PointCloudFileProcess') as viewer, \
             patch('control.QtPipelineRuntime.DataProcessingProcess') as processor, \
             patch('control.QtPipelineRuntime.PlcCommunicationProcess') as plc, \
             patch('control.QtPipelineRuntime.LidarAcquisitionProcess') as lidar, \
             patch('control.QtPipelineRuntime.PointCloudSaveService') as saver:
            runtime = QtPipelineRuntime(control_type=3, data_path=str(self.file))
            runtime._register_and_start = Mock()
            runtime.start_pipeline()
            viewer.assert_called_once()
            for unused in (processor, plc, lidar, saver.from_config_file):
                unused.assert_not_called()

    def test_file_view_process_loads_without_hardware_processes(self):
        runtime = QtPipelineRuntime(control_type=3, data_path=str(self.file))
        try:
            runtime.start_pipeline()
            deadline = time.monotonic() + 15
            snapshot = {}
            while time.monotonic() < deadline:
                snapshot = runtime.poll()
                if snapshot.get('points') is not None:
                    break
                self.assertFalse(snapshot.get('fault'), snapshot.get('fault'))
                time.sleep(.05)
            self.assertEqual(snapshot['points'].shape, (2, 3))
            self.assertIsNone(runtime.plc_handler)
            self.assertIsNone(runtime.lidar_acquisition)
            self.assertIsNone(runtime.data_processor)
            self.assertIsNone(runtime.save_service)
        finally:
            errors = runtime.stop_pipeline()
        self.assertEqual(errors, [])
        self.assertFalse(runtime.has_live_workers())

    def test_replay_uses_text_input_and_plc_not_real_lidar(self):
        with patch('control.QtPipelineRuntime.DataProcessWorker') as replay, \
             patch('control.QtPipelineRuntime.DataProcessingProcess') as processor, \
             patch('control.QtPipelineRuntime.PlcCommunicationProcess') as plc, \
             patch('control.QtPipelineRuntime.LidarAcquisitionProcess') as lidar, \
             patch('control.QtPipelineRuntime.PointCloudSaveService') as saver:
            runtime = QtPipelineRuntime(control_type=1, data_path=str(self.file))
            runtime._register_and_start = Mock()
            runtime.start_pipeline()
            replay.assert_called_once()
            self.assertIs(replay.call_args.args[0], processor.call_args.args[0])
            self.assertIsNone(replay.call_args.args[2])
            self.assertEqual(replay.call_args.kwargs['strategy_name'], 'complete_workpiece')
            processor.assert_called_once()
            plc.create.assert_called_once()
            lidar.assert_not_called()
            saver.from_config_file.assert_not_called()

    def test_strategy_still_rejects_one_and_three_for_all_control_types(self):
        for code in (1, 2, 3):
            for strategy in (1, 3):
                with self.subTest(code=code, strategy=strategy), \
                     patch('control.QtPipelineRuntime.TomlLoader.load', return_value={'strategy_name': strategy}):
                    with self.assertRaises(ValueError):
                        QtPipelineRuntime(control_type=code)

    def test_plc_debug_snapshot_exposes_current_position(self):
        runtime = QtPipelineRuntime(control_type=1, data_path=str(self.file))
        runtime.ui_status_queue = queue.Queue()
        runtime.plc_handler = Mock(pid=1)
        runtime.plc_handler.is_alive.return_value = True
        runtime.ui_status_queue.put({'source': 'plc', 'timestamp': time.monotonic(), 'connected': True,
                                     'pulse': 1234, 'motion': 'moving_forward'})
        snapshot = runtime.poll()
        self.assertEqual(snapshot['chain_position'], 1234)

    def test_file_import_failure_is_retained_in_alarms(self):
        runtime = QtPipelineRuntime(control_type=3, data_path=str(self.file))
        runtime.ui_status_queue = queue.Queue()
        message = 'TXT 导入失败：文件格式错误'
        runtime.ui_status_queue.put({'source': 'files', 'state': 'error', 'detail': message})
        snapshot = runtime.poll()
        self.assertEqual(snapshot['fault'], message)
        self.assertIn(message, snapshot['alarms'])
        runtime._feedback.clear()
        self.assertIn(message, runtime.poll()['alarms'])
