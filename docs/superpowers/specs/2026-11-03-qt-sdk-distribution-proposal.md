# 精简 Qt 主界面与受保护 SDK 交付方案

状态：用户选择每次开始只处理一个工件；继续实施该调整。替代上一版删除全部 Qt 的要求。

## 最新用户约束（优先于下文历史提案）

点击开始后，按原软件流程循环运行，每轮处理一个完整工件，保留点云并显示序号，直到结束软件。
保留现有 control/model/view 和多进程框架，只改上层调用；所有用到的 model 文件保持原文，不改算法、不搬迁底层源码。
只允许删除证明未被调用的 model `.py`；优先保守保留。下文新 SDK/核心目录建议不再实施，改为 acquisition_api.py 封装现有 QtPipelineRuntime。
当前现场报文以用户更新的 model/plc/MovingFrameData.py 为准：48 轴、302 字节载荷、ChainPulse；不是旧 README 的 206 字节。

## 保留与调整

保持只支持 `strategy_name = 2`、移除运动控制/路径规划/模式 1 与 3 的目标。
保留一个主窗口：点云显示、PLC 和各激光连接状态、开始、结束软件。
Qt 展示与采集核心解耦；核心通过状态、预览、工件结果和错误事件供 Qt 或其他调用方订阅。
接口本身也可以输出预览数据，点云展示不要求把采集实现暴露给二开开发者。

## 推荐交付方式

**开放 UI 和 SDK 源码，底层以 Cython 扩展 wheel 交付。** 与既有 Python/Qt 和 Cython 构建基础一致。
核心无需 Qt；Qt 使用后台执行和排队信号接收事件，主线程更新 OpenGL 点云与状态。
预览可以降采样和合并过期显示帧；用于匹配的原始整件数据不能因预览限流而丢失。

另一种方式是独立核心进程 + 本地进程通信：更适合 C#/C++ 等语言集成和独立核心部署，
但增加进程生命周期、点云传输与版本兼容工作。本次先作为备选，由用户选定后实施。

## 二开交付包拟定布局（新路径，尚未创建）

| 路径 | 交付内容 | 二开职责 |
| --- | --- | --- |
| ui/main_window.py | 源码 | 修改单一主窗口、状态与按钮 |
| ui/point_cloud_view.py | 源码 | 修改点云展示；复用现有 QtPointCloudView |
| ui/worker.py | 源码 | 只做 SDK 事件到 Qt 信号的适配 |
| robot_cal_sdk/client.py | 源码 | 稳定调用封装、参数和错误转换 |
| robot_cal_sdk/types.py | 源码 | 状态/结果/预览数据结构 |
| robot_cal_sdk/core.pyi | 类型声明 | 文档化公共接口，不包含算法实现 |
| examples/、docs/sdk.md | 源码与文档 | 集成示例、生命周期、线程和版本约定 |
| config/ | 经过筛选的 TOML 和字段说明 | 现场 IP、端口、坐标标定和采集阈值 |
| robot_cal_core/*.pyd | 仅编译产物 | PLC/激光通信、完整工件状态机、点云处理、识别 |

路径是建议，不代表已确认实现。保护由交付清单和构建检查保证，不能靠下划线命名或让人约定不打开文件。

## 按当前代码的保护清单

底层私有实现包括：`model/lidar/LidarCommon.py`、`model/plc/PlcCommon.py`、
PLC 报文解析实现、原 `control/LidarAcquisitionProcess.py` / `LidarAcquisitionStrategies.py` 中保留的模式 2 逻辑、
`model/dataprocess/DataFilter.py`、`DataSplitting.py`、`complete_workpiece/DataFindBlocks.py`、
`DataPartitionAuto.py`、`DataPartitionStatic.py`、`CabinetTypeRecognizer.py`。
这些实现可在重构后搬入私有核心包，开发者包不附 `.py` / `.pyx` / `.c` / `.cpp` / `.pdb`、私有测试、构建脚本或 Git 历史。
编译某个上层模块不自动保护它导入的其他 Python 模块，必须检查核心依赖的完整交付清单。

公共 DTO 取代直接暴露内部 BlockData 等可变算法对象。保留公共错误类型、配置字段说明和接口类型声明。
源文件按职责拆分；界面不能继续直接导入 PLC 状态机或内部识别类。

`CabinetTypeConfig.toml` 含标准型号特征。需要二开者调整型号时就必须提供可编辑数据；
如这些特征也保密，则由用户维护私有型号包，外部只开放型号标识和更新入口。
本地运行且可读取的数据始终可能被提取，不能承诺配置加密等同于不可获取。

## 推荐生命周期（待确认）

`start()` 自动连接 PLC 和激光，只采集一个完整工件，匹配并发出一个序号结果后释放连接，回到待机。
`stop()` 请求结束采集、释放设备，不阻塞 Qt 主线程；残件不触发匹配成功事件。
`close()` 完成资源释放；“结束软件”先停止核心，确认退出后关闭窗口。
状态事件区分设备已连接、准备就绪、正在采集、正在匹配、失败，连接成功不等于整条链可用。
点击开始时立即进入 connecting 状态，设备连接和采集在后台运行；停止期间禁用再次开始。
同一运行实例由核心唯一持有设备连接，GUI 和 SDK 不各自创建一条设备采集链。
纯函数/命令行单件调用仍可作为另一种使用方式，不能与当前占用设备的 GUI 会话重复采集。

用户已确定：每次开始只处理一个工件；完成后保留点云和结果，恢复开始按钮，再次点击重新连接并采集下一件。

## 保护与部署限制

Cython 可编译 Windows `.pyd` 供 Python 导入；交付 wheel 需匹配 Python 版本、操作系统和架构。
PyInstaller 可用于应用部署，但其中 Python 字节码原则上可被反编译，不作为底层算法保护手段。
本地二进制仍可能被逆向；强保密算法若必须不落地，应考虑由用户控制的计算服务，需另外评估现场网络和点云传输。
二开者仍可修改公开 UI/业务流程并调用已编译核心；核心算法维护、修复和平台版本编译由用户负责。

## 当前实施状态

原 Qt 文件尚未删除；前版通信/配置重构处于中间状态，不能把当前工作区当作已验证交付版本。
停止原计划的“删除全部 Qt”步骤；新方案确定后重新规划测试、构建和开发者交付包检查。

## 参考

- Cython compilation: https://cython.readthedocs.io/en/3.1.x/src/userguide/source_files_and_compilation.html
- PyInstaller operating mode: https://pyinstaller.org/en/stable/operating-mode.html
