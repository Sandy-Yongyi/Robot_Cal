import queue
import unittest
from unittest.mock import Mock, patch
import numpy as np
from acquisition_sdk.AcquisitionPreviewAdapter import AcquisitionPreviewAdapter
from acquisition_sdk import LidarAcquisitionProcess
from control.PipelineRuntime import QtPipelineRuntime

class SkippedPreviewTests(unittest.TestCase):
    def test_skipped_capture_requests_preview_without_changing_lidar(self):
        worker = AcquisitionPreviewAdapter.__new__(AcquisitionPreviewAdapter)
        worker.complete_skip_current_workpiece = True
        worker.draw_type = 2
        worker.save_task_queue = Mock()
        observed = []
        def save(obj, incomplete=False): observed.append(obj.draw_type)
        with patch.object(LidarAcquisitionProcess, '_save_workpiece_data', save):
            worker._save_workpiece_data()
        self.assertEqual(observed, [1])
        self.assertEqual(worker.draw_type, 2)

    def test_normal_capture_does_not_publish_saver_preview(self):
        worker = AcquisitionPreviewAdapter.__new__(AcquisitionPreviewAdapter)
        worker.complete_skip_current_workpiece = False
        worker.software_first_start = False
        worker.draw_type = 1
        worker.save_task_queue = Mock()
        observed = []
        with patch.object(LidarAcquisitionProcess, '_save_workpiece_data', lambda obj, incomplete=False: observed.append(obj.draw_type)):
            worker._save_workpiece_data()
        self.assertEqual(observed, [2])
        self.assertEqual(worker.draw_type, 1)

    def test_save_job_keeps_internal_id_and_uses_seconds_for_point_files(self):
        worker = AcquisitionPreviewAdapter.__new__(AcquisitionPreviewAdapter)
        worker.complete_skip_current_workpiece = True
        worker.draw_type = 2
        worker.save_task_queue = queue.Queue()
        job_id = '20261104_104951_338138_57632_3'

        def save(obj, incomplete=False):
            obj.save_task_queue.put_nowait({'job_id': job_id, 'filename_suffix': job_id})

        with patch.object(LidarAcquisitionProcess, '_save_workpiece_data', save):
            worker._save_workpiece_data()
        self.assertEqual(worker.save_task_queue.get_nowait(),
                         {'job_id': job_id, 'filename_suffix': '20261104_104951'})

    def test_skipped_preview_clears_previous_identifier(self):
        runtime = QtPipelineRuntime()
        runtime.result_queue, runtime.ui_status_queue, previews = queue.Queue(), queue.Queue(), queue.Queue()
        runtime.collector.set_visualization_queue(previews)
        previews.put({'points': np.ones((2,3)), 'preview_processed': True, 'match_result': {'identifier': 4, 'sequence': 1, 'status':'matched'}})
        self.assertEqual(runtime.poll()['matched_id'], 4)
        previews.put({'points': np.ones((2,3)), 'boxes': None, 'preview_processed': True})
        snapshot = runtime.poll()
        self.assertIsNone(snapshot['matched_id'])
        self.assertEqual(snapshot['match_status'], 'waiting')
