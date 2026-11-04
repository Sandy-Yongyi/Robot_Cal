# 二开文件边界

保留原 MVC 与多进程框架。二开者主要修改 `view/qt/main_window.py`、点云展示组件、
`acquisition_api.py`，以及公开的 `ControlCenter` / `QtUiBridge` / `QtPipelineRuntime` 上层编排。
不需要查看或改动底层算法。

## 可开放的内容

- `main.py`、`qt_main.py`、`app_bootstrap.py`：程序入口。
- `view/qt/`：单一主窗口和 OpenGL 点云展示。
- `acquisition_api.py`：同步单件调用与连续客户端。
- `control/ControlCenter.py`、`QtUiBridge.py`、`QtPipelineRuntime.py`、`UiState.py`、
  `RuntimeStateCollector.py`、`ShutdownCoordinator.py`、`ProcessHealthMonitor.py`：框架调用与状态。
- README、框架文档、字段说明、必要 TOML 配置。

## 私有内容只交付编译产物

- 所有保留的 `model` 实现（空的包初始化文件除外）。
- `control/LidarAcquisitionProcess.py` 和 `LidarAcquisitionStrategies.py`。
- `control/PlcCommunicationProcess.py`、`DataProcessingProcess.py`、`PointCloudSaveProcess.py`。

这些源文件留在你的维护仓库，不提供给外部二开者。使用原 Cython 构建机制编译，模块路径与原框架一致，
二开程序仍按 `from model...` / `from control...` 导入，无需改成另一套框架。
任何一个私有依赖若继续以 Python 源码交付，都可能暴露该部分逻辑；仅编译入口文件不够。

`tools/export_developer_package.py` 检查全部私有模块已构建再导出；只复制允许公开的 `.py` 和编译产物，
不复制 `.git`、私有算法测试、Cython 生成 C、调试符号或维护用 setup.py。
请按 README 的命令从新目录构建，并在目标 Python/Windows 版本上测试整个开发包。

## 稳定接口

`AcquisitionClient.start()`：启动原循环管线。
`poll()`：返回点云、连接、最新结果及故障的快照；建议每 100 ms 轮询。
`take_results()`：取出从上次调用后积累的结果，取后清空。
`stop()`：按原流程停止并释放资源；关闭异常会抛出 RuntimeError。
`acquire_and_match(timeout_s=120, stop_event=None)`：启动一套管线，取得第一件结果后停止，成功只返回 ID。

结果字典：`sequence: int`、`identifier: int | None`、`status: matched | unmatched | error`、`message: str`。
无匹配不等于设备故障；硬件进程崩溃、心跳超时、保存错误通过 `fault` 报告，上层需要停止并处理。
对同一套 PLC/激光，只能由一条运行管线拥有设备连接；本版没有跨应用的多客户端硬件调度。

## 工作目录和线程

底层路径与算法不改，仍使用工作目录。嵌入前由宿主切换到安装根目录；不要让不同项目共用不明确的 cwd。
Windows 多进程调用放在 `if __name__ == '__main__'` 内，并调用 `multiprocessing.freeze_support()`。
API 无 Qt 依赖；自定义界面应将启动和停止放后台，将快照转换为自己的 UI 线程事件。
不要直接从工作进程更新 Qt 控件，也不要在 GUI 正常运行时另启动一个客户端连接同一组设备。

本地二进制是提高逆向成本的交付手段，不是绝对保密机制；TOML 中的标定和型号特征同样属于对方可见数据。

维护提示：`ControlCenter.take_results()` 的结果历史未设置容量上限；需要长期连续运行的二开宿主应定期读取并归档。
自带界面保留这份历史供业务扩展读取，本次未增加历史存储/容量管理功能。
