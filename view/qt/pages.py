from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QScrollArea, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from control.UiState import UiState
from view.qt.point_cloud_view import QtPointCloudView
from view.qt import theme
from view.qt.widgets import ControlButton, Panel, StatusBadge, RuntimeLogView
from view.qt.auth import authorize


def apply_task_progress(progress_bar: QProgressBar, progress: int | None) -> None:
    progress_bar.setRange(0, 100)
    progress_bar.setValue(0 if progress is None else max(0, min(100, progress)))
    progress_bar.setFormat("进度待反馈" if progress is None else "%p%")


class RealtimeControlPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._last_scene_points = object()
        self._last_scene_boxes = object()
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.ui_px(10))

        center = QVBoxLayout()
        self.point_cloud_view = QtPointCloudView()
        view_tools = QHBoxLayout()
        fit_button = ControlButton("适配视图")
        fit_button.clicked.connect(self.point_cloud_view.reset_camera)
        view_tools.addWidget(QLabel("三维工作区  ·  左键旋转 / 右键平移 / 滚轮缩放"))
        self.point_cloud_view.setToolTip("默认从 X 负方向观察，Z 轴水平、Y 轴竖直，网格位于 X–Z 地面。左键拖动旋转，右键拖动平移，滚轮缩放；双击点云设置旋转中心，适配视图恢复整体视角。")
        view_tools.addStretch(1)
        view_tools.addWidget(fit_button)
        center.addLayout(view_tools)
        layers = QHBoxLayout()
        self.layer_controls = {}
        for key, label in (("points", "点云"), ("outside", "外框"), ("inside", "内框"), ("jig", "挂具")):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.toggled.connect(lambda checked, layer=key: self.point_cloud_view.set_layer_visible(layer, checked))
            self.layer_controls[key] = checkbox
            layers.addWidget(checkbox)
        layers.addStretch(1)
        self.point_count = QLabel("0 点")
        layers.addWidget(self.point_count)
        center.addLayout(layers)
        center.addWidget(self.point_cloud_view, 1)
        task_panel = Panel("当前任务")
        self.task_name = QLabel("等待任务")
        self.task_progress = QProgressBar()
        self.task_stage = QLabel("待机")
        task_panel.layout.addWidget(self.task_name)
        task_panel.layout.addWidget(self.task_progress)
        task_panel.layout.addWidget(self.task_stage)
        bottom = QHBoxLayout()
        bottom.addWidget(task_panel, 1)
        event_panel = Panel("最近事件")
        self.recent_events = RuntimeLogView()
        self.recent_events.setMaximumHeight(theme.ui_px(110))
        event_panel.layout.addWidget(self.recent_events)
        bottom.addWidget(event_panel, 2)
        center.addLayout(bottom)
        root.addLayout(center, 1)

        side = QVBoxLayout()
        chain_panel = Panel("生产控制")
        chain_panel.setMinimumWidth(theme.ui_px(230))
        self.chain_position = QLabel("当前位置  0 pulse")
        self.chain_status = QLabel("待机")
        self.scan_speed = QLabel("扫描速度  25 mm/s")
        self.start_button = ControlButton("▶  启动自动喷涂", "primary")
        self.stop_button = ControlButton("■  安全停止", "danger")
        if getattr(controller, "control_type", 2) == 3:
            self.start_button.setText("▶  导入 TXT 点云")
            self.stop_button.setText("■  停止查看")
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)
        for widget in (self.chain_position, self.chain_status, self.scan_speed, self.start_button, self.stop_button):
            chain_panel.layout.addWidget(widget)
        side.addWidget(chain_panel)

        device_panel = Panel("设备联锁")
        self.plc_badge = StatusBadge("PLC 未连接")
        self.lidar_badge = StatusBadge("激光未就绪")
        self.servo_badge = StatusBadge("伺服未就绪")
        for widget in (self.plc_badge, self.lidar_badge, self.servo_badge):
            device_panel.layout.addWidget(widget)
        side.addWidget(device_panel)
        side.addStretch(1)
        root.addLayout(side)

    def _start(self) -> None:
        if callable(getattr(self, "start_action", None)):
            self.start_action()
            return
        try:
            if authorize(self, self.controller) and hasattr(self.controller, "start"):
                self.controller.start()
        except Exception as exc:
            self.chain_status.setText(f"启动失败：{exc}")

    def _stop(self) -> None:
        if callable(getattr(self, "stop_action", None)):
            self.stop_action()
            return
        try:
            if authorize(self, self.controller) and hasattr(self.controller, "stop"):
                self.controller.stop()
        except Exception as exc:
            self.chain_status.setText(f"停止失败：{exc}")

    def apply_state(self, state: UiState) -> None:
        self.chain_position.setText(f"当前位置  {state.chain_position} pulse")
        self.chain_status.setText(state.chain_status)
        self.scan_speed.setText(f"扫描速度  {state.chain_speed} mm/s")
        self.start_button.setEnabled(not state.running and not state.stopping)
        self.stop_button.setEnabled(state.running and not state.stopping)
        self.task_name.setText(state.task.name)
        self.task_stage.setText(state.task.stage)
        self.recent_events.apply_events(tuple(event for event in state.logs if event.source == "stdout")[-5:])
        apply_task_progress(self.task_progress, state.task.progress)
        if state.points is not self._last_scene_points:
            self.point_cloud_view.set_points(state.points)
            self.point_count.setText(f"{len(self.point_cloud_view.points):,} 点")
            self._last_scene_points = state.points
            if state.points is None:
                self._last_scene_boxes = object()
        if state.boxes is not self._last_scene_boxes:
            self.point_cloud_view.set_boxes(state.boxes)
            self._last_scene_boxes = state.boxes
        devices = {device.name: device for device in state.devices}
        for name, badge in (("PLC", self.plc_badge), ("激光", self.lidar_badge), ("伺服", self.servo_badge)):
            device = devices.get(name)
            badge.set_status(f"{name} · {device.detail if device else '未连接'}", bool(device and device.online))
