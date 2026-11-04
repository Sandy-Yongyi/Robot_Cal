from __future__ import annotations

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from control.UiState import UiState
from view.qt.pages import RealtimeControlPage
from view.qt.theme import CYAN, MUTED, build_industrial_stylesheet, ui_px
from view.qt.auth import authorize


class _StartupThread(QThread):
    failed = pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

    def run(self):
        try:
            self.controller.start()
        except Exception as exc:
            self.failed.emit(str(exc))


class IndustrialMainWindow(QMainWindow):
    ROUTES = ("realtime",)
    ROUTE_LABELS = ("实时控制",)

    def __init__(self, controller, bridge=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.bridge = bridge
        self._last_state = UiState.empty(getattr(controller, "strategy_name", "complete_workpiece"))
        self._close_pending = False
        self._stop_pending = False
        self._starter = None
        self._close_authorized = False
        self.setWindowTitle("JOIHEY · 智能喷涂控制中心")
        control_type = getattr(controller, "control_type", 2)
        if control_type in (1, 3):
            self.setWindowTitle(self.windowTitle() + (" · 开发调试：TXT 联调 PLC" if control_type == 1 else " · 开发调试：只画图"))
        self.setMinimumSize(1200, 760)
        self.setStyleSheet(build_industrial_stylesheet())
        self._build_ui()
        self.realtime_page.start_action = self._start_acquisition
        self.realtime_page.stop_action = self._stop_acquisition
        if bridge is not None and hasattr(bridge, "state_changed"):
            bridge.state_changed.connect(self.apply_state)
        if bridge is not None and hasattr(bridge, "error_raised"):
            bridge.error_raised.connect(self._show_bridge_error)

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(ui_px(12), ui_px(10), ui_px(12), ui_px(12))
        layout.setSpacing(ui_px(10))

        header = QHBoxLayout()
        brand = QLabel("◆  JOIHEY · 智能喷涂控制中心")
        brand.setStyleSheet(f"font-weight: 700; font-size: {ui_px(17)}px; color: {CYAN};")
        header.addWidget(brand)
        header.addStretch(1)
        self.system_status = QLabel("● 系统待机")
        self.system_status.setStyleSheet(f"color: {MUTED};")
        header.addWidget(self.system_status)
        layout.addLayout(header)
        self.alarm_banner = QLabel()
        self.alarm_banner.setTextFormat(Qt.TextFormat.PlainText)
        self.alarm_banner.setWordWrap(True)
        self.alarm_banner.setStyleSheet(f"background: #3b202b; color: #ffd8da; border: 1px solid #7d3645; border-radius: {ui_px(6)}px; padding: {ui_px(10)}px;")
        self.alarm_banner.hide()
        self.alarm_scroll = QScrollArea()
        self.alarm_scroll.setWidgetResizable(True)
        self.alarm_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.alarm_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.alarm_scroll.setMaximumHeight(ui_px(120))
        self.alarm_scroll.setWidget(self.alarm_banner)
        self.alarm_scroll.hide()
        layout.addWidget(self.alarm_scroll)

        content = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(ui_px(190))
        for label in self.ROUTE_LABELS:
            self.navigation.addItem(QListWidgetItem(label))
        self.navigation.currentRowChanged.connect(self._change_page)
        content.addWidget(self.navigation)

        self.workspace = QStackedWidget()
        self.realtime_page = RealtimeControlPage(self.controller)
        for page in (self.realtime_page,):
            self.workspace.addWidget(page)
        content.addWidget(self.workspace, 1)
        layout.addLayout(content, 1)
        self.navigation.setCurrentRow(0)

    def route_names(self) -> tuple[str, ...]:
        return self.ROUTES

    def _change_page(self, index: int) -> None:
        if index >= 0:
            self.workspace.setCurrentIndex(index)

    def apply_state(self, state: UiState) -> None:
        self._last_state = state
        self._set_alarm_text("\n".join(dict.fromkeys(state.alarms)))
        if state.stopping:
            self.system_status.setText("● 系统停止中")
            self.system_status.setStyleSheet("color: #ffb351;")
        elif state.running:
            self.system_status.setText(f"● {state.chain_status}")
            self.system_status.setStyleSheet("color: #2bd49d;")
        else:
            self.system_status.setText("● 系统待机")
            self.system_status.setStyleSheet(f"color: {MUTED};")
        self.realtime_page.apply_state(state)
        if self._starter is not None or self._close_pending or self._stop_pending:
            self.realtime_page.start_button.setEnabled(False)
        if self._stop_pending:
            self.realtime_page.stop_button.setEnabled(False)
        if state.match_status == 'matched':
            self.realtime_page.task_name.setText(f'匹配序号：{state.matched_id}')
            self.realtime_page.task_stage.setText(f'第 {state.workpiece_index} 件 · {state.task.stage}')
        elif state.match_status == 'unmatched':
            self.realtime_page.task_name.setText('未匹配到唯一序号')
        elif state.match_status == 'error':
            self.realtime_page.task_name.setText('匹配异常')
        if self._close_pending and self._starter is None and not state.running and not state.stopping:
            QTimer.singleShot(0, self.close)

    def _set_alarm_text(self, text: str) -> None:
        self.alarm_banner.setText(text)
        self.alarm_banner.setVisible(bool(text))
        self.alarm_scroll.setVisible(bool(text))

    def _show_bridge_error(self, title: str, detail: str) -> None:
        lines = tuple(self._last_state.alarms) + (f"{title}：{detail}",)
        self._set_alarm_text("\n".join(dict.fromkeys(lines)))

    def _start_acquisition(self):
        if self._starter is not None or self.controller.running or self.controller.stopping:
            return
        if not authorize(self, self.controller):
            return
        self.realtime_page.start_button.setEnabled(False)
        self._starter = _StartupThread(self.controller, self)
        self._starter.failed.connect(lambda message: self._show_bridge_error('启动失败', message))
        self._starter.finished.connect(self._startup_finished)
        self._starter.start()

    def _startup_finished(self):
        starter, self._starter = self._starter, None
        stop_pending, self._stop_pending = self._stop_pending, False
        if starter is not None:
            starter.deleteLater()
        self.apply_state(self.controller.build_ui_state())
        if self._close_pending:
            self.close()
        elif stop_pending:
            self._stop_acquisition()

    def _stop_acquisition(self):
        if not authorize(self, self.controller):
            return
        if self._starter is not None:
            self._stop_pending = True
            self.realtime_page.start_button.setEnabled(False)
            self.realtime_page.stop_button.setEnabled(False)
            self.system_status.setText('● 等待启动结束后停止采集')
            return
        try:
            self.controller.stop()
            self.apply_state(self.controller.build_ui_state())
        except Exception as exc:
            self._show_bridge_error('停止失败', str(exc))

    def closeEvent(self, event) -> None:
        if self._starter is not None:
            self._close_pending = True
            self.realtime_page.start_button.setEnabled(False)
            self.system_status.setText('● 等待启动结束后释放设备连接')
            event.ignore()
            return
        if not self._close_authorized:
            if not authorize(self, self.controller):
                event.ignore()
                return
            self._close_authorized = True
        state = self.controller.build_ui_state()
        if state.running or state.stopping:
            event.ignore()
            if not self._close_pending:
                self._close_pending = True
                self.system_status.setText("● 正在安全停止，完成后关闭窗口")
            if state.running and not state.stopping:
                try:
                    self.controller.stop()
                except Exception as exc:
                    self._close_pending = False
                    self._close_authorized = False
                    self.system_status.setText(f"● 停止失败：{exc}")
            return
        if self.bridge is not None:
            self.bridge.stop()
        self.realtime_page.point_cloud_view.release_gl_resources()
        event.accept()
