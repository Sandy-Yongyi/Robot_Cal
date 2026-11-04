# 框架和数据流程

本次仅调整上层编排与展示，保留 `control/model/view`、原队列、共享内存块和独立保存进程。
`model` 所有保留文件、两个 LiDAR 控制文件原样使用。以 README 的当前约束为准，早期设计文档中的新包重构已作废。

界面沿用原 `IndustrialMainWindow` 和 `RealtimeControlPage` 视觉结构，原 `theme.py`、`widgets.py`、`auth.py` 恢复原文；
左侧导航仅保留第一个“实时控制”及对应页面，其他页面移除。点云工具栏、图层、生产控制、设备联锁、任务和事件区保留。
序号显示在原任务区，模型生成的 BlockData 同时供原外框/内框/挂具图层展示。

## 启动和循环

`CONTROL_TYPE` 是独立的运行方式：1=TXT 联调 PLC，2=实时采数，3=只导入 TXT 画图；全部保留。
`strategy_name` 是采集策略，仅支持2；不要将运行方式1/3视为第一/第三种采集策略。
下述四进程流程对应实时方式2；方式1使用原版DataProcessWorker读取TXT，将原始点云送入独立处理进程识别，与PLC进程并行；方式3只启动文件显示进程。
原版DataProcessWorker由上层TxtAcquisitionAdapter管理策略选择及停止；处理进程通过WorkpieceProcessingAdapter调用原版DataProcessingProcess。TXT与实时方式共用DataFindBlocks和CabinetTypeRecognizer，每份点云识别一次。

1. `main.py` 准备运行目录、单实例检查和 multiprocessing，进入 `qt_main.py`。
2. `qt_main.build_controller()` 创建原 `QtPipelineRuntime`、`ControlCenter`、`QtUiBridge`，不连接设备。
3. 点击开始，主窗口启动线程调用 `controller.start()`，避免原保存进程的启动等待阻塞 Qt。
4. runtime 按原框架创建保存服务、数据处理、PLC 通信、LiDAR 采集四个进程。上层固定 `complete_workpiece`。
5. PLC 进程调用原 `PlcManager` / `BasePlc.scan()`，读取 `ChainPulse` 并发布最新脉冲和运动状态；不调用 `send_frame()`。
6. 原 LiDAR 进程使用原策略与原模型解析/滤波/坐标转换；依脉冲、有效点阈值和原结束规则累积整件。
7. 完整工件交给数据处理进程；该进程用原 `DataFindBlocks` 和 `CabinetTypeRecognizer` 生成序号。
8. 同时原保存服务通过共享内存池持有点云块，独立保存；只由数据处理进程向原展示队列发布点云及同件匹配结果，防止较慢保存的旧预览覆盖新工件。
9. 不退出进程、不重新连接设备，继续采下一件，直到结束软件或发生需要停机的进程故障。

## 通道

| 通道 | 生产者 → 消费者 | 数据 |
| --- | --- | --- |
| `pulse_queue` | PLC → 原 LiDAR 进程 | pulse、fifo、status、plc_generation |
| `raw_data_queue` | 原 LiDAR → 数据处理 | 整件 XYZ、方向、停止位置；亦含激光状态通知 |
| `result_queue` | 数据处理 → runtime | sequence、identifier、status、message |
| `viz_queue` | 数据处理 → RuntimeStateCollector | 点云和同件 match_result 一起发布，最多保留少量显示消息 |
| 保存共享内存及任务/ACK 队列 | 原 LiDAR ↔ 保存进程 | 块描述、保存任务、完成 ACK |
| `ui_status_queue` | PLC / LiDAR → runtime | 真实连接反馈和时间戳，不能用“进程存在”冒充连接成功 |
| `log_queue` | 工作进程 → 上层 | 原 stdout/stderr 诊断日志 |

`QtUiBridge` 每 100 ms 轮询 `ControlCenter.poll_once()`。runtime 返回最新预览、设备状态和本轮结果；
controller 保存最新 ID、工件序号，并通过 `take_results()` 提供一次性结果读取。
没有新数据时保留已有点云，不因为空轮询清空显示。结果 `unmatched` 显式展示，不把识别器的 0 当作成功序号。
`raw_data_queue` 维持原无界队列，避免匹配耗时期间激光状态包占满队列、阻塞受保护的原采集线程。
界面序号与点云由同一预览消息更新；独立的 result_queue 继续向调用方完整传递每件结果。

## 结束软件

点击安全停止 → 暂时禁止再次开始 → 请求原 ControlCenter 异步停止 → 原保存服务 stop_event →
等待采集退出/提交已采部分 → 排空保存任务 → 关闭或按原超时机制终止其他工作进程 →
释放共享内存 → 回到待机，保留界面、点云和结果，可再次启动。
点击窗口关闭按钮时，才在完成上述清理后停止Qt bridge并关闭窗口。

启动尚未完成时关闭窗口，会先等待启动线程返回，再请求释放资源；不会在后台线程仍运行时销毁窗口。
如果原停止流程报告工作进程未退出，窗口保持“停止中”，避免留下设备进程后直接关闭。
停止时限、强制终止和残件保存语义保持原实现，不承诺强制中断时的残件可用于有效匹配。

## 不再执行的链路

上层不再实例化运动规划器、分枪器、运动队列或设备控制页面。
第一/第三种采集策略不由上层启动；保护的 LiDAR 文件内部原有定义不改，仍有静态/懒导入的依赖保守保留。
`DataProcessWorker` 和 `PointCloudFileProcess` 服务于运行方式1/3，正常保留并执行，不是采集策略1/3的空壳。
删除清单由 `tools/audit_model_dependencies.py` 保守遍历所有分支的导入闭包产生；清单保存在 `model-dependency-audit.json`。
