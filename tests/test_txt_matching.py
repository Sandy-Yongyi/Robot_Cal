import queue
import contextlib
import io
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from control.WorkpieceProcessingAdapter import TxtAcquisitionAdapter, WorkpieceProcessingAdapter
from model.dataprocess.complete_workpiece.CabinetTypeRecognizer import CabinetTypeRecognizer
from model.formats.complete_workpiece.BlockDataFormat import BlockData, OutsideData


class TxtMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'combined_one.txt'
        np.savetxt(self.file, [[1, 2, 3], [4, 5, 6]])
        self.raw, self.results, self.preview = queue.Queue(), queue.Queue(), queue.Queue()

    def pair(self, matching=True):
        reader = TxtAcquisitionAdapter(self.raw, queue.Queue(), None, str(self.file))
        reader._heartbeat_sleep = Mock()
        processor = WorkpieceProcessingAdapter(self.raw, self.results, self.preview)
        processor.cabinet_type_recognizer = CabinetTypeRecognizer({
            'matching': {'tolerance_mm': 0},
            'cabinet_types': [{'type': 9, 'enabled': True, 'outside_bounds_mm': [0, 1, 0, 2, 0, 3], 'inside_bounds_mm': []}]})
        processor.data_processor = Mock()
        processor.data_processor.start_process.return_value = BlockData(
            outside_data=[OutsideData(0, 1 if matching else 100, 0, 2, 0, 3)], inside_data=[])
        return reader, processor

    def process_txt(self, reader, processor):
        with contextlib.redirect_stdout(io.StringIO()):
            reader.run()
            while not self.raw.empty():
                processor._process_data(self.raw.get_nowait())

    def test_upper_layer_selects_complete_workpiece_without_changing_reader_default(self):
        from control.DataProcessWorker import DataProcessWorker
        reader, _ = self.pair()
        self.assertIsInstance(reader, DataProcessWorker)
        self.assertEqual(reader.strategy_name, 'complete_workpiece')

    def test_txt_pipeline_uses_same_geometry_and_actual_recognizer(self):
        reader, processor = self.pair()
        self.process_txt(reader, processor)
        result = self.results.get_nowait()
        self.assertEqual((result['identifier'], result['status'], result['sequence']), (9, 'matched', 1))
        preview = self.preview.get_nowait()
        self.assertEqual(preview['match_result'], result)
        self.assertIsInstance(preview['boxes'], BlockData)
        processor.data_processor.start_process.assert_called_once()

    def test_txt_pipeline_unmatched_result_matches_live_contract(self):
        reader, processor = self.pair(matching=False)
        self.process_txt(reader, processor)
        result = self.results.get_nowait()
        self.assertIsNone(result['identifier'])
        self.assertEqual(result['status'], 'unmatched')

    def test_cancelled_txt_reader_does_not_process_another_piece(self):
        reader, processor = self.pair()
        reader.stop_event.set()
        self.process_txt(reader, processor)
        self.assertTrue(self.results.empty())
        processor.data_processor.start_process.assert_not_called()

    def test_txt_reader_and_processor_run_as_processes_and_stop(self):
        raw, results, previews, pulses, logs = [multiprocessing.Queue() for _ in range(5)]
        stop = multiprocessing.Event()
        reader = TxtAcquisitionAdapter(raw, pulses, None, str(self.file), stop_event=stop, result_queue=results)
        processor = WorkpieceProcessingAdapter(raw, results, previews, stop_event=stop)
        for worker in (reader, processor):
            worker.stdout = io.StringIO()
            worker.stderr = io.StringIO()
        try:
            processor.start()
            reader.start()
            result = results.get(timeout=20)
            self.assertEqual((result['sequence'], result['status']), (1, 'unmatched'))
            self.assertEqual(previews.get(timeout=5)['match_result'], result)
        finally:
            stop.set()
            for worker in (reader, processor):
                if worker.pid is not None:
                    worker.join(timeout=5)
                    if worker.is_alive():
                        worker.terminate()
                        worker.join(timeout=2)
            for output in (raw, results, previews, pulses, logs):
                output.close()
                output.join_thread()
        self.assertEqual((reader.exitcode, processor.exitcode), (0, 0))

    def test_independent_origin_txt_files_share_original_recognition_logic(self):
        np.savetxt(Path(self.temp.name) / 'left_piece.txt', [[1,2,3], [4,5,6]])
        np.savetxt(Path(self.temp.name) / 'right_piece.txt', [[7,8,9], [10,11,12]])
        reader, processor = self.pair()
        reader.data_paths = self.temp.name
        reader.data_name = 'piece.txt'
        reader.translate_data_origin = 2
        reader.directions = ('left', 'right')
        processor.cabinet_type_recognizer = Mock()
        processor.cabinet_type_recognizer.recognize.side_effect = [9, 9]
        self.process_txt(reader, processor)
        self.assertEqual(self.results.get_nowait()['identifier'], 9)
        self.assertEqual(processor.data_processor.start_process.call_count, 2)
        np.testing.assert_array_equal(self.preview.get_nowait()['points'], [[1,2,3],[4,5,6]])
        np.testing.assert_array_equal(self.preview.get_nowait()['points'], [[7,8,9],[10,11,12]])

    def test_live_adapter_runs_as_process_and_stops_without_hardware(self):
        from control.WorkpieceProcessingAdapter import WorkpieceProcessingAdapter
        raw, results, previews, logs = [multiprocessing.Queue() for _ in range(4)]
        stop = multiprocessing.Event()
        worker = WorkpieceProcessingAdapter(raw, results, previews, stop_event=stop)
        worker.stdout = io.StringIO()
        worker.stderr = io.StringIO()
        try:
            worker.start()
            raw.put({'all_data': np.ones((2,3)), 'translate_data_origin': 1})
            result = results.get(timeout=20)
            self.assertEqual(result['status'], 'unmatched')
            self.assertEqual(previews.get(timeout=5)['match_result'], result)
        finally:
            stop.set()
            if worker.pid is not None:
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=2)
            for output in (raw, results, previews, logs):
                output.close()
                output.join_thread()
        self.assertEqual(worker.exitcode, 0)

    def test_reader_cancels_with_large_unconsumed_raw_cloud(self):
        import time
        np.savetxt(self.file, np.ones((20000, 3)))
        raw, pulses = multiprocessing.Queue(), multiprocessing.Queue()
        stop = multiprocessing.Event()
        reader = TxtAcquisitionAdapter(raw, pulses, None, str(self.file), stop_event=stop)
        reader.stdout, reader.stderr = io.StringIO(), io.StringIO()
        try:
            reader.start()
            deadline = time.monotonic() + 15
            while raw.qsize() == 0 and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(raw.qsize(), 1)
            stop.set()
            reader.join(timeout=3)
            self.assertFalse(reader.is_alive())
            self.assertEqual(reader.exitcode, 0)
        finally:
            stop.set()
            if reader.pid is not None and reader.is_alive():
                reader.terminate()
                reader.join(timeout=2)
            for output in (raw, pulses):
                output.close()
                output.join_thread()
