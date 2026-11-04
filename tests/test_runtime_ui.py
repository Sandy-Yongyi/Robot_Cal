import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import queue
import tempfile
import shutil
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QStackedWidget
from PyQt6.QtGui import QCloseEvent

from control.QtPipelineRuntime import QtPipelineRuntime
from control.ControlCenter import ControlCenter
from control.UiState import UiState, DeviceState
from view.qt.main_window import IndustrialMainWindow


class FakeRuntime:
    control_type = 2
    def __init__(self):
        self.started = 0
        self.stopped = 0
        self.snapshot = {}
    def start_pipeline(self):
        self.started += 1
    def stop_pipeline(self):
        self.stopped += 1
        return []
    def poll(self):
        return self.snapshot
    def has_live_workers(self):
        return False


class DummyCloud(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = np.empty((0, 3))
    def set_points(self, points):
        self.points = np.empty((0, 3)) if points is None else points
    def set_boxes(self, boxes):
        pass
    def release_gl_resources(self):
        pass
    def reset_camera(self):
        pass
    def set_layer_visible(self, layer, visible):
        pass


class RuntimeTests(unittest.TestCase):
    def test_wiring_preserves_unbounded_raw_queue_and_processor_owns_preview(self):
        with patch('control.QtPipelineRuntime.multiprocessing.Queue', side_effect=lambda *a, **kw: queue.Queue(*a, **kw)), \
             patch('control.QtPipelineRuntime.PointCloudSaveService') as saver, \
             patch('control.QtPipelineRuntime.DataProcessingProcess') as processor, \
             patch('control.QtPipelineRuntime.PlcCommunicationProcess'), \
             patch('control.QtPipelineRuntime.LidarAcquisitionProcess'):
            runtime = QtPipelineRuntime()
            runtime._register_and_start = Mock()
            runtime.start_pipeline()
            raw_queue = processor.call_args.args[0]
            self.assertEqual(raw_queue.maxsize, 0)
            self.assertIs(saver.from_config_file.call_args.args[2], runtime.collector._visualization_queue)

    def test_display_identifier_is_correlated_with_displayed_cloud(self):
        runtime = QtPipelineRuntime()
        runtime.result_queue = queue.Queue()
        runtime.ui_status_queue = queue.Queue()
        previews = queue.Queue()
        runtime.collector.set_visualization_queue(previews)
        points = np.array([[1., 2., 3.]])
        runtime.result_queue.put({'identifier': 99, 'sequence': 3, 'status': 'matched'})
        previews.put({'points': points, 'preview_processed': True,
                      'match_result': {'identifier': 42, 'sequence': 2, 'status': 'matched'}})
        snapshot = runtime.poll()
        self.assertIs(snapshot['points'], points)
        self.assertEqual(snapshot['matched_id'], 42)
        self.assertEqual(snapshot['workpiece_index'], 2)
        self.assertEqual(snapshot['results'][0]['identifier'], 99)

    def test_runtime_accepts_control_types_but_not_invalid_values(self):
        for code in (1, 2, 3):
            self.assertEqual(QtPipelineRuntime(control_type=code).control_type, code)
        for code in (0, 4, True):
            with self.assertRaises(ValueError):
                QtPipelineRuntime(control_type=code)

    def test_result_becomes_public_state_and_is_delivered_once(self):
        runtime = FakeRuntime()
        controller = ControlCenter(runtime, strategy_name='complete_workpiece')
        controller.start()
        runtime.snapshot = {'matched_id': 5, 'workpiece_index': 3, 'match_status': 'matched',
                            'results': [{'identifier': 5, 'sequence': 3, 'status': 'matched'}]}
        controller.poll_once()
        self.assertEqual(controller.build_ui_state().matched_id, 5)
        self.assertEqual(controller.take_results()[0]['identifier'], 5)
        self.assertEqual(controller.take_results(), [])

    def test_stop_retains_last_point_cloud_and_result(self):
        runtime = FakeRuntime()
        controller = ControlCenter(runtime, strategy_name='complete_workpiece')
        controller.start()
        points = np.ones((3, 3))
        runtime.snapshot = {'points': points, 'matched_id': 9, 'updated': True, 'points_updated': True}
        controller.poll_once()
        controller.stop()
        self.assertIs(controller.build_ui_state().points, points)
        self.assertEqual(controller.build_ui_state().matched_id, 9)


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        patcher = patch('view.qt.pages.QtPointCloudView', DummyCloud)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runtime = FakeRuntime()
        self.controller = ControlCenter(self.runtime, strategy_name='complete_workpiece')
        self.window = IndustrialMainWindow(self.controller)
        self.addCleanup(self.window.deleteLater)

    def test_only_main_view_start_and_exit(self):
        self.assertEqual(self.window.navigation.count(), 1)
        self.assertEqual(self.window.navigation.item(0).text(), '实时控制')
        self.assertEqual(self.window.workspace.count(), 1)
        self.assertEqual(self.window.route_names(), ('realtime',))
        self.assertTrue(hasattr(self.window.realtime_page, 'recent_events'))
        self.assertTrue(hasattr(self.window.realtime_page, 'layer_controls'))
        self.assertIn('适配视图', {button.text() for button in self.window.findChildren(QPushButton)})
        from view.qt.theme import build_industrial_stylesheet
        self.assertEqual(self.window.styleSheet(), build_industrial_stylesheet())

    def test_state_updates_preview_connection_and_identifier(self):
        points = np.ones((3, 3))
        state = replace(UiState.empty('complete_workpiece'), running=True, points=points,
                        matched_id=12, workpiece_index=4, match_status='matched',
                        devices=(DeviceState('PLC', True), DeviceState('激光', True)))
        self.window.apply_state(state)
        self.assertFalse(self.window.realtime_page.start_button.isEnabled())
        self.assertIn('12', self.window.realtime_page.task_name.text())
        self.assertIn('PLC', self.window.realtime_page.plc_badge.text())
        self.assertIs(self.window.realtime_page.point_cloud_view.points, points)

    def test_close_requested_during_startup_stops_after_startup_finishes(self):
        self.window._starter = object()
        during_start = QCloseEvent()
        self.window.closeEvent(during_start)
        self.assertFalse(during_start.isAccepted())
        self.window._starter = None
        self.controller.start()
        after_start = QCloseEvent()
        self.window.closeEvent(after_start)
        self.assertEqual(self.runtime.stopped, 1)
        self.assertFalse(self.controller.running)

    def test_close_checks_controller_even_before_first_bridge_update(self):
        self.controller.start()
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertEqual(self.runtime.stopped, 1)
        self.assertFalse(self.controller.running)

    def test_stop_button_keeps_window_cloud_and_result_for_restart(self):
        self.controller.start()
        points = np.ones((3, 3))
        self.runtime.snapshot = {'points': points, 'updated': True, 'points_updated': True,
                                 'matched_id': 8, 'match_status': 'matched'}
        self.controller.poll_once()
        self.window.apply_state(self.controller.build_ui_state())
        self.window.show()
        self.app.processEvents()
        self.window.realtime_page.stop_button.click()
        self.controller.poll_once()
        self.window.apply_state(self.controller.build_ui_state())
        self.app.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window._close_pending)
        self.assertEqual(self.runtime.stopped, 1)
        self.assertFalse(self.controller.running)
        self.assertIs(self.window.realtime_page.point_cloud_view.points, points)
        self.assertIn('8', self.window.realtime_page.task_name.text())
        self.assertTrue(self.window.realtime_page.start_button.isEnabled())

    def test_stop_during_startup_waits_then_stops_without_requesting_close(self):
        self.controller.start()
        self.window._starter = object()
        self.window.apply_state(self.controller.build_ui_state())
        self.window.realtime_page.stop_button.click()
        self.assertFalse(self.window._close_pending)
        self.window._starter = None
        self.window._startup_finished()
        self.assertEqual(self.runtime.stopped, 1)
        self.assertFalse(self.controller.running)
        self.assertFalse(self.window._close_pending)
