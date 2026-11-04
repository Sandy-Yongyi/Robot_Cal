import ast
import queue
import unittest
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from model.formats.complete_workpiece.BlockDataFormat import BlockData

ROOT = Path(__file__).resolve().parents[1]

class LegacyCompatibilityTests(unittest.TestCase):
    def test_user_processing_source_is_preserved(self):
        import hashlib
        self.assertEqual(hashlib.sha256((ROOT / 'control/DataProcessingProcess.py').read_text(encoding='utf-8-sig').encode()).hexdigest(), '34448fd41642acea9eb8e32bed784e9f945a2859578921ffd6c81a1631aa510c')

    def test_independent_origins_require_all_recognized_types_to_agree(self):
        from control.WorkpieceProcessingAdapter import WorkpieceProcessingAdapter
        worker = WorkpieceProcessingAdapter(None, queue.Queue(), queue.Queue())
        worker._build_block_data = Mock(return_value=BlockData())
        worker.cabinet_type_recognizer = Mock()
        worker.cabinet_type_recognizer.recognize.side_effect = [9, 0]
        worker._process_data({'translate_data_origin': 2, 'left_data': np.ones((2,3)), 'right_data': np.ones((2,3))})
        self.assertEqual(worker.result_queue.get_nowait()['status'], 'unmatched')
        self.assertEqual([c.kwargs['same_origin'] for c in worker._build_block_data.call_args_list], [False, False])

    def test_txt_worker_source_is_original(self):
        import subprocess
        original = subprocess.check_output(['git', '-c', 'safe.directory=D:/Code/Robot_Cal', 'show', 'HEAD:control/DataProcessWorker.py'], cwd=ROOT).decode('utf-8-sig')
        self.assertEqual((ROOT / 'control/DataProcessWorker.py').read_text(encoding='utf-8-sig'), original.replace('\r\n', '\n'))

    def test_retired_plc_methods_remain_as_pass(self):
        from control.PlcCommunicationProcess import PlcCommunicationProcess
        for name in ('_process_frame_data', '_process_continuous_scan_cycle', '_axis_to_moving_frame'):
            self.assertIsNone(getattr(PlcCommunicationProcess.__new__(PlcCommunicationProcess), name)())

    def test_same_origin_right_and_top_cover_use_original_recognition_rule(self):
        import multiprocessing
        from control.WorkpieceProcessingAdapter import WorkpieceProcessingAdapter
        worker = WorkpieceProcessingAdapter(None, queue.Queue(), queue.Queue(), top_cover_enabled=multiprocessing.Value('b', True))
        worker.read_data_config['workpiece_origin_side'] = 'right'
        worker._build_block_data = Mock(return_value=BlockData())
        worker.cabinet_type_recognizer = Mock()
        worker.cabinet_type_recognizer.recognize.return_value = 3
        worker._process_data({'all_data': np.ones((2,3))})
        self.assertEqual(worker.result_queue.get_nowait()['identifier'], 9)
        self.assertTrue(worker._build_block_data.call_args.kwargs['same_origin'])

    def test_failed_partition_still_displays_cloud_with_unmatched_result(self):
        from control.WorkpieceProcessingAdapter import WorkpieceProcessingAdapter
        worker = WorkpieceProcessingAdapter(None, queue.Queue(), queue.Queue())
        worker._build_block_data = Mock(return_value=None)
        worker._process_data({'all_data': np.ones((2,3))})
        result = worker.result_queue.get_nowait()
        preview = worker.viz_queue.get_nowait()
        self.assertEqual(result['status'], 'unmatched')
        self.assertEqual(preview['match_result'], result)
        from model.utils.WorkpieceOriginUtil import transform_points_for_origin
        np.testing.assert_array_equal(preview['points'], transform_points_for_origin(np.ones((2,3)), worker.read_data_config))

    def test_plc_reads_chainpulse_through_original_method_entrypoints(self):
        from control.PlcCommunicationProcess import PlcCommunicationProcess
        worker = PlcCommunicationProcess(None, queue.Queue(), queue.Queue(), strategy_name="complete_workpiece")
        worker.plc = Mock()
        worker.plc.scan.return_value = Mock(ChainPulse=36)
        worker.connection_type = 'tcp'
        worker.pulse_to_mm = 1
        worker.max_pulse = 160000
        worker.diff_start_pulse = 7
        worker.pulse_history = []
        worker.plc_connection_generation = 1
        worker.chain_motion_status = 'stopped'
        self.assertTrue(worker._update_plc_data())
        packet = worker.pulse_queue.get_nowait()
        self.assertEqual(packet['pulse'], 36)
        self.assertEqual(packet['fifo'], 4)
        worker.plc.send_frame.assert_not_called()

    def test_plc_read_connection_and_pulse_methods_are_original(self):
        import subprocess
        original = subprocess.check_output(['git', '-c', 'safe.directory=D:/Code/Robot_Cal', 'show', 'HEAD:control/PlcCommunicationProcess.py'], cwd=ROOT).decode('utf-8-sig')
        def methods(code):
            cls = next(n for n in ast.parse(code).body if isinstance(n, ast.ClassDef) and n.name == 'PlcCommunicationProcess')
            return {n.name: ast.dump(n, include_attributes=False) for n in cls.body if isinstance(n, ast.FunctionDef)}
        before = methods(original)
        after = methods((ROOT/'control/PlcCommunicationProcess.py').read_text(encoding='utf-8-sig'))
        for name in ('_pulse_to_chaincountcm','_get_fifo_step_delta','_initialize_connection','_update_plc_data','_update_chain_status','_handle_connection_error','_mark_plc_disconnected'):
            self.assertEqual(before[name], after[name], name)
