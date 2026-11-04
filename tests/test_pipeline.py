import ast
import queue
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from control.LidarAcquisitionStrategies import AcquisitionStrategyFactory, CompleteWorkpieceStrategy
from control.WorkpieceProcessingAdapter import WorkpieceProcessingAdapter as DataProcessingProcess
from model.formats.complete_workpiece.BlockDataFormat import BlockData, OutsideData
from model.dataprocess.complete_workpiece.CabinetTypeRecognizer import CabinetTypeRecognizer


class PipelineTests(unittest.TestCase):
    def test_original_factory_still_provides_complete_workpiece(self):
        self.assertIsInstance(AcquisitionStrategyFactory.create_strategy('complete_workpiece', {}), CompleteWorkpieceStrategy)

    def test_plc_process_has_no_motion_or_send_frame_call(self):
        code = (Path(__file__).resolve().parents[1] / 'control/PlcCommunicationProcess.py').read_text(encoding='utf-8-sig')
        tree = ast.parse(code)
        calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertNotIn('send_frame', calls)
        self.assertNotIn('model.motionplan', code)

    def processor(self, identifier=7):
        processor = DataProcessingProcess.__new__(DataProcessingProcess)
        processor.result_queue = queue.Queue()
        processor.viz_queue = queue.Queue(maxsize=2)
        processor.read_data_config = {'translate_data_origin': 1, 'workpiece_origin_side': 'left'}
        processor.sequence = 0
        processor.top_cover_enabled = None
        processor.machine_data_queue = processor.result_queue
        processor.cabinet_type_recognizer = Mock()
        processor.cabinet_type_recognizer.recognize.return_value = identifier
        processor._build_block_data = Mock(return_value=BlockData())
        return processor

    def test_processing_emits_identifier_instead_of_motion_data(self):
        processor = self.processor()
        processor._process_data({'all_data': np.array([[1., 2., 3.]]), 'lidar_status': 0, 'translate_data_origin': 1})
        result = processor.result_queue.get_nowait()
        self.assertEqual(result['identifier'], 7)
        self.assertEqual(result['sequence'], 1)
        self.assertEqual(result['status'], 'matched')
        self.assertNotIn('left', result)
        np.testing.assert_array_equal(processor.viz_queue.get_nowait()['points'], [[1, 2, 3]])

    def test_zero_is_unmatched_not_success(self):
        processor = self.processor(identifier=0)
        processor._process_data({'all_data': np.ones((3, 3)), 'translate_data_origin': 1})
        result = processor.result_queue.get_nowait()
        self.assertIsNone(result['identifier'])
        self.assertEqual(result['status'], 'unmatched')

    def test_uses_actual_cabinet_recognizer_identifier_unchanged(self):
        processor = self.processor()
        processor.cabinet_type_recognizer = CabinetTypeRecognizer({
            'matching': {'tolerance_mm': 0},
            'cabinet_types': [{'type': 9, 'enabled': True, 'outside_bounds_mm': [0, 1, 0, 2, 0, 3], 'inside_bounds_mm': []}]})
        blocks = BlockData(outside_data=[OutsideData(0, 1, 0, 2, 0, 3)], inside_data=[])
        processor._build_block_data.return_value = blocks
        processor._process_data({'all_data': np.ones((3, 3)), 'translate_data_origin': 1})
        self.assertEqual(processor.result_queue.get_nowait()['identifier'], 9)

    def test_lidar_status_only_packet_does_not_create_workpiece(self):
        processor = self.processor()
        processor._process_data({'lidar_status': 0})
        self.assertTrue(processor.result_queue.empty())
