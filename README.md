# 工件采集与序号匹配 · 二次开发接入说明

本组件用于连接 PLC 和激光雷达，采集完整工件点云，完成几何分区与型号识别，并向业务程序提供匹配序号。
你可以直接运行配套 Qt 界面，也可以通过 Python 接口将采集与匹配功能接入自己的软件。
本文件包含开发包的运行、配置、接口、框架流程及扩展说明，无需其他说明文档。

## 1. 开发包与运行环境

开发包采用 `control / model / view` 分层结构，由可编辑的上层 Python 文件和编译后的底层模块组成。

```text
安装目录/
├─ README.md                     本接入说明
├─ requirements.txt              依赖列表
├─ main.py                       Qt 程序入口
├─ qt_main.py                    界面与控制器组装
├─ app_bootstrap.py              运行目录准备
├─ acquisition_api.py            Python 接口及命令行入口
├─ deployment_check.py           环境与配置自检
├─ view/qt/                      界面、主题、点云展示源码
├─ control/                      上层编排源码及核心进程扩展模块
├─ model/                        底层扩展模块
│  └─ tomls/                     现场参数及型号配置
└─ package-manifest.json          交付文件及 SHA-256 摘要
```

运行环境为 **Windows x64、CPython 3.11（64 位）**。包内 `.pyd` 必须与 Python 版本和系统架构匹配。
底层模块已编译，可直接导入使用；修改界面和公开调用代码无需重新编译底层。
安装目录需要具备写入权限，运行时会在其中创建 `data/` 目录存放日志和点云。

下面以 `C:\Apps\RobotCal` 为安装目录，实际使用时替换成你的解压路径。

```powershell
cd C:\Apps\RobotCal
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --check-deployment
.\.venv\Scripts\python.exe main.py --control-type 2
```

自检会检查配置、依赖和 Qt 平台插件，不启动设备通信。完成环境自检后，还需要验证现场设备连接、坐标标定、识别准确率和退出流程。

### 运行方式与采集策略

`main.py` 的 `CONTROL_TYPE` 选择运行/调试方式，`ModeConfig.toml` 的 `strategy_name` 选择采集策略，两者相互独立。

| `CONTROL_TYPE` | 运行方式 | 数据和设备 |
| --- | --- | --- |
| `1` | TXT 显示并联调 PLC | 导入 TXT，运行完整工件分区和序号匹配，并连接 PLC；不启用激光采集或运动控制 |
| `2` | 实时采数 | 连接 PLC 和激光，持续采集、匹配并保存工件 |
| `3` | 只导入 TXT 画图 | 只显示 TXT 点云，不连接 PLC/激光，不运行序号匹配 |

三种运行方式均保留，**只将采集策略限制为整数 `strategy_name = 2`**。
`CONTROL_TYPE` 的值为 `1` 或 `3` 不表示使用第一或第三种采集策略。
直接运行 `python main.py` 时使用 `main.py` 中的 `CONTROL_TYPE`、`DATA_PATH`、`DATA_NAME`；命令行参数可覆盖它们。

```powershell
# 实时完整工件采集
.\.venv\Scripts\python.exe main.py --control-type 2

# TXT 联调 PLC，并执行完整工件匹配
.\.venv\Scripts\python.exe main.py --control-type 1 --data-path C:\PointClouds --data-name sample.txt

# 仅显示 TXT 点云，不启动设备通信
.\.venv\Scripts\python.exe main.py --control-type 3 --data-path C:\PointClouds\combined_sample.txt
```

方式 1/3 必须指定文件或目录，可通过 `main.py` 的 `DATA_PATH` 或 `--data-path` 设置。
目录数据可用 `DATA_NAME` 或 `--data-name` 筛选。独立原点的数据文件应使用对应方向前缀，例如 `left_`、`right_`。
方式 2 不使用 TXT 参数。

## 2. 界面操作

左侧“实时控制”是主页面，包含点云展示、图层开关、生产控制、设备联锁、当前任务和最近事件。

| 控件/区域 | 功能 |
| --- | --- |
| “启动自动喷涂”按钮 | 启动设备连接和循环采集匹配；本组件实际执行的是采集与识别 |
| “安全停止”按钮 | 停止采集并释放设备连接，保留界面、点云和最新匹配结果，完成后可再次启动 |
| 窗口关闭按钮 | 停止采集、完成资源清理后退出软件 |
| 设备联锁 | 显示 PLC、激光等状态反馈；连接成功与否以通信反馈为准 |
| 三维工作区 | 每个工件处理完成后更新点云，支持旋转、平移、缩放和适配视图 |
| 点云/外框/内框/挂具 | 控制对应显示图层的可见性 |
| 当前任务 | 显示匹配序号、工件计数和处理状态 |
| 最近事件/告警区域 | 显示运行事件和错误信息 |

实时采数方式下点击一次启动后，程序持续循环：**采集一件完整工件 → 匹配序号 → 更新点云和结果 → 继续下一件**。
处理完成的点云会保留到下一次更新，不需要每件重新点击启动。TXT 联调按选定数据集顺序处理；只画图方式导入后保留画面。
停止期间应等待保存和资源释放完成，完成后恢复启动按钮。启动尚未完成时点击停止，会等待启动结束后停止采集，界面保持打开。
点击窗口关闭按钮时才退出软件；关闭期间会先完成启动/停止和资源清理。

本组件仅支持 `strategy_name = 2`（完整工件采集），不向 PLC 发送轴运动、喷涂或链条启停命令。
工件运动和现场联锁由 PLC 或宿主系统负责。

## 3. 现场配置

配置文件位于安装目录的 `model/tomls/`。修改后停止程序并重新启动，使设备进程加载新参数。

| 文件 | 用途 |
| --- | --- |
| `ModeConfig.toml` | `strategy_name` 必须为整数 `2` |
| `SystemConfig.toml` | 设置各方向启用的激光 ID 列表 |
| `PlcConfig.toml` | PLC IP、端口及 TCP/UDP 方式；当前使用 ID `1` |
| `LidarConfig.toml` | 激光型号、地址、安装方向和坐标偏移 |
| `ReadDataConfig.toml` | 滤波范围、脉冲比例、采集起止阈值、首启跳过及点云保存参数 |
| `ProcessConfig.toml` | 点云几何分区参数 |
| `CabinetTypeConfig.toml` | 型号序号、外框/内部分区坐标和 XYZ 匹配容差 |
| `SprayConfig.toml` | 采集模块初始化所需的兼容参数，应保留该文件 |

包内可能包含供兼容使用的其他配置和模块；请保持目录完整。上层只启用完整工件采集管线。

接入前重点确认：

- PLC、激光 IP/端口可达，激光 ID 与方向配置一致。
- `pulse_to_mm`、`max_pulse` 与现场计数规则一致。
- 滤波范围、各方向点数阈值、`max_scan_length` 和 `linked_stop_distance_mm` 能正确划分工件。
- 坐标原点、标定偏移与型号配置中的标准坐标一致。
- `start_skip_mm` 符合首件处理要求：启动时已处于扫描区的半件可能被跳过。

当前 PLC 接收载荷为大端序、**302 字节、48 组轴状态**，帧头为 `02 02 02 02`，帧尾为 `03 03 03 03`。

| 接收字段 | 类型 | 载荷内偏移 |
| --- | --- | --- |
| `ChainPulse` | Int32 | 0 |
| `ChainSpeed` | Int32 | 4 |
| `HeartBeat` | Int16 | 8 |
| `Status` | Int16 | 10 |
| `Operate` | Int16 | 12 |
| `AxisList` | 48 × 6 字节 | 14 |

现场 PLC 报文需要与该版本一致。通信协议或底层算法需要调整时，请使用组件提供方交付的兼容版本。

## 4. Python 单件调用

使用 `acquire_and_match()` 等待一个完整工件的处理结果。匹配成功返回序号；未匹配、超时或运行异常时抛出异常。
无论成功还是失败，本次调用结束前都会请求停止其启动的采集管线。
该函数和 `AcquisitionClient` 使用实时采数方式 `control_type=2`，不受 GUI 入口 `main.py` 中 `CONTROL_TYPE` 的调试设置影响。

将下面示例保存为开发包根目录下的 `demo_single.py`：

```python
import multiprocessing
import os
from pathlib import Path

from acquisition_api import acquire_and_match, NoMatchError


if __name__ == '__main__':
    multiprocessing.freeze_support()
    os.chdir(Path(__file__).resolve().parent)

    try:
        identifier = acquire_and_match(timeout_s=120)
        print(f'匹配序号：{identifier}')
    except NoMatchError as exc:
        print(f'该工件未匹配：{exc}')
    except TimeoutError as exc:
        print(f'等待超时：{exc}')
    except InterruptedError:
        print('采集已取消')
    except RuntimeError as exc:
        print(f'采集或退出失败：{exc}')
```

| 参数 | 说明 |
| --- | --- |
| `timeout_s` | 正有限数，默认 120；从管线启动完成后开始计算等待首个结果的时间 |
| `stop_event` | 可选；提供 `is_set()` 方法的事件对象，用于请求取消等待 |

设备启动和关闭时的保存排空等待还可能额外耗时，`timeout_s` 不是整个函数的强制执行时限。
该函数处理首个工件结果：首件未匹配时抛出 `NoMatchError`，不会自动等待后续工件直到匹配成功。

**Windows 多进程入口必须放在 `if __name__ == '__main__'` 内。**
将接口嵌入其他目录的项目时，确保安装目录可被 Python 导入，并在启动前明确将工作目录切换到该安装目录。
底层配置、日志和点云路径均依赖这个工作目录。

## 5. Python 连续调用

需要连续处理多个工件时，使用 `AcquisitionClient`。一次启动持有一组设备连接，持续逐件处理，退出上下文时清理资源。

将下面示例保存为开发包根目录下的 `demo_continuous.py`：

```python
import multiprocessing
import os
import time
from pathlib import Path

from acquisition_api import AcquisitionClient


if __name__ == '__main__':
    multiprocessing.freeze_support()
    os.chdir(Path(__file__).resolve().parent)

    try:
        with AcquisitionClient() as client:
            while True:
                snapshot = client.poll()
                for result in client.take_results():
                    if result['status'] == 'matched':
                        print(result['sequence'], result['identifier'])
                    elif result['status'] == 'unmatched':
                        print(result['sequence'], '未匹配')
                    else:
                        raise RuntimeError(result['message'])

                if snapshot.get('fault'):
                    raise RuntimeError(snapshot['fault'])
                time.sleep(.1)
    except KeyboardInterrupt:
        print('已停止')
```

| 方法 | 行为 |
| --- | --- |
| `start()` | 启动持续运行的设备管线；同步方法，可能等待进程就绪 |
| `poll()` | 收集最新预览、设备状态、结果和故障快照；建议每 100 ms 调用 |
| `take_results()` | 读取自上次读取以来积累的结果，读取后清空 |
| `stop()` | 停止管线并释放资源；清理失败时抛出 `RuntimeError` |
| `with AcquisitionClient()` | 自动执行启动和退出清理 |

`poll()` 会将结果收集到客户端结果缓冲；请持续调用 `take_results()` 消费这些结果。
单次读取可能包含多个工件，应逐项处理。不要将 `snapshot['results']` 和 `take_results()` 作为两个独立来源重复执行业务。

### 结果结构

```python
{
    'sequence': 1,
    'identifier': 3,
    'status': 'matched',
    'message': '',
}
```

| 字段 | 含义 |
| --- | --- |
| `sequence` | 本轮启动后的工件计数，从 1 开始；不是工件型号序号 |
| `identifier` | 匹配成功时的正整数型号序号，未匹配或异常时为 `None` |
| `status` | `matched`、`unmatched` 或 `error` |
| `message` | 未匹配或异常的说明 |

序号由 `CabinetTypeRecognizer.recognize()` 根据几何分区结果和 `CabinetTypeConfig.toml` 识别，调用链直接使用识别器返回的序号。
识别器返回 `0` 时，对外结果为 `unmatched` 和 `identifier=None`。
独立原点的多个方向分别识别时，若得到不同的非零序号，该工件按未匹配到唯一序号处理。

### 快照与点云

`poll()` 返回字典，常用字段如下。部分字段只在有新数据时提供。

| 字段 | 使用方式 |
| --- | --- |
| `points` | 用于展示的 NumPy XYZ 点云，坐标单位 mm；无新预览时可能为 `None` |
| `boxes` | 外框/内部分区/挂具等展示数据 |
| `updated`、`points_updated` | 判断本次是否需要刷新显示；没有更新时保留已有画面 |
| `devices` | 设备状态对象列表，每项包含 `name`、`online`、`detail` |
| `matched_id`、`workpiece_index`、`match_status` | 与当前展示点云对应的识别信息 |
| `results` | 本次轮询收集到的业务结果；业务代码可统一通过 `take_results()` 获取 |
| `fault` | 存在时表示需由宿主处理的管线故障 |
| `logs`、`alarms` | 日志与告警信息 |

展示点云可能经过预览降采样，识别使用的是完整采集数据。
点云及对应展示序号一起更新；业务结果通过结果通道独立传递，二者到达时间可能不同。

## 6. 命令行调用

其他程序也可以启动命令行并读取标准输出：

```powershell
.\.venv\Scripts\python.exe acquisition_api.py --timeout 120
```

成功时，stdout 只输出一行序号，退出码为 `0`。诊断与错误写入 stderr；未匹配、超时或异常时退出码非零。
命令执行完毕会停止它启动的管线。需要连续运行时，使用 Python 客户端接口。

## 7. 框架与数据流程

### 界面与控制层

```text
main.py → qt_main.py
             ├─ view/qt/main_window.py + pages.py   主窗口和实时控制页面
             ├─ control/QtUiBridge.py              Qt 定时轮询和状态信号
             └─ control/ControlCenter.py           启动、停止、状态和结果读取
                          ↓
                 control/QtPipelineRuntime.py      工作进程与资源编排
```

界面显示期间不会自动连接设备。点击启动后，后台启动线程调用控制器，控制器启动工作进程。
`QtUiBridge` 每 100 ms 收集状态并更新界面。Python 接口通过同一运行时使用设备管线。
运行时依据 `control_type` 组装进程：方式 1 由 `DataProcessWorker` 读取 TXT 并直接处理，与 PLC 进程并行；方式 2 使用下述实时采数管线；方式 3 只使用 TXT 显示进程。

TXT 和实时数据复用相同处理实现：

```text
方式1：TXT → DataProcessWorker → 几何分区 → CabinetTypeRecognizer → 结果/预览
方式2：激光 → 整件点云 → WorkpieceProcessingAdapter → DataProcessingProcess → 结果/预览
方式3：TXT → PointCloudFileProcess → 仅显示
```

`DataProcessWorker` 和实时处理进程通过 `WorkpieceProcessingAdapter` 复用 `DataProcessingProcess` 的整件处理方法，TXT 与实时方式调用相同的 `DataFindBlocks` 和 `CabinetTypeRecognizer`，
输出相同的 `sequence / identifier / status / message` 结果及配对点云/分区预览。
TXT 方式不会将已处理的数据再送入一个额外识别进程，避免重复分区或重复识别。

`DataProcessingProcess` 保留原有结果与处理规则：同一原点使用 `all_data`，不同原点分别处理 `left_data`、`right_data`，各有效分区识别的柜型一致才返回对应 `type`，否则为 0。
上层适配器将 `type` 转成接口的 `identifier`（0 对应 `None`），添加工件序号、停止控制和配对预览，不修改底层识别方法。原有顶盖开关规则也保留。
`PlcCommunicationProcess`、`DataProcessWorker` 中采集策略 1、3 及停用运动的原方法入口保留为 `pass`；二开代码不能依赖这些入口执行采集或运动。此处采集策略与 `CONTROL_TYPE=1/2/3` 的调用方式相互独立。

### 工作进程

```text
PLC 通信进程 ── pulse_queue ──→ LiDAR 采集进程
                                    │
                     ┌──────────────┴────────────────┐
                     ↓                               ↓
              raw_data_queue                共享内存块 + 保存任务
                     ↓                               ↓
              数据处理进程                      点云保存进程
       几何分区 → CabinetTypeRecognizer        文件写入、ACK 归还块
                     │
              ┌──────┴──────┐
              ↓             ↓
         result_queue    viz_queue
              ↓             ↓
          业务结果       点云 + 同件识别信息
```

| 通道 | 数据内容 |
| --- | --- |
| `pulse_queue` | PLC 位置、运动状态和连接代数 |
| `raw_data_queue` | 整件点云、方向、停止位置及激光状态通知 |
| `result_queue` | 每个工件的序号匹配结果 |
| `viz_queue` | 点云、分区显示数据及同件匹配信息；可合并过期显示消息 |
| 保存任务/ACK 队列 | 共享内存块描述、保存任务和完成确认 |
| `ui_status_queue` | PLC/激光实际通信反馈及时间戳 |
| `log_queue` | 工作进程的诊断输出 |

设备读取、点云采集、几何处理和文件保存分别在工作进程中执行。
一轮工件处理结束后继续采集下一件，进程和连接保持运行。
保存进程独立写文件；只有数据处理进程发布匹配预览，确保显示的序号与点云属于同一工件。

### 停止与关闭流程

```text
点击安全停止 → 暂时禁止再次启动 → 发出停止请求
        → 等待采集退出并提交已采数据
        → 按停止流程结束其他工作进程、排空保存任务
        → 释放共享内存和连接资源 → 回到待机，保留点云与结果

点击窗口关闭按钮 → 完成上述资源清理 → 停止界面轮询 → 关闭窗口
```

关闭可能需要等待磁盘写入或进程退出。出现停止超时或工作进程未退出告警时，应检查日志和设备状态。
中断工件可能以不完整状态保存，不能当作成功识别结果使用。

## 8. 二次开发范围

你可以在以下源码中接入业务、调整展示和封装调用：

| 文件/目录 | 扩展位置 |
| --- | --- |
| `view/qt/main_window.py` | 主窗口、导航、启动与关闭交互 |
| `view/qt/pages.py` | 实时控制页面、任务结果和事件展示 |
| `view/qt/point_cloud_view.py` | 点云视角、交互和展示 |
| `view/qt/theme.py`、`widgets.py` | 主题和公共控件样式 |
| `qt_main.py` | 界面、控制器及 bridge 的组装 |
| `acquisition_api.py` | 面向宿主系统的调用封装 |
| `control/ControlCenter.py`、`UiState.py` | 控制状态与业务结果读取 |
| `control/QtUiBridge.py`、`RuntimeStateCollector.py` | 界面信号和状态采集 |
| `control/QtPipelineRuntime.py` | 进程、队列和资源生命周期编排 |
| `control/WorkpieceProcessingAdapter.py` | 对接原处理结果、停止信号及点云预览；保持原处理类不变 |
| `control/DataProcessWorker.py`、`PointCloudFileProcess.py` | TXT 整件读取/识别和只画图加载 |
| `control/ShutdownCoordinator.py`、`ProcessHealthMonitor.py` | 异步停止和进程健康监测 |

`model` 及采集、PLC 通信、处理、保存等核心进程以编译模块提供，按现有模块路径导入使用。
需要改变底层协议或识别算法时，应取得与当前接口兼容的组件更新。

### 在现有 Qt 界面中接业务结果

复用已经运行的 `controller` 和 `bridge`。例如，在 `qt_main.py` 创建它们后，连接一个轻量回调：

```python
def on_state_changed(state):
    for result in controller.take_results():
        if result['status'] == 'matched':
            print('业务收到序号：', result['identifier'])

bridge.state_changed.connect(on_state_changed)
```

结果读取后会从缓冲移除，应安排一个统一的业务消费者，避免多个模块竞争读取。
结果历史未设置容量上限，持续运行时应定期读取并按业务要求归档。

### 接入约束

- 同一套 PLC/激光由一条管线持有连接。已有界面运行时，从其控制器取结果，不再启动第二个客户端占用相同设备。
- `start()` 和 `stop()` 是同步接口。自定义 GUI 应在后台启动/停止，在 UI 线程中更新控件。
- 保持主程序入口保护，防止 Windows spawn 在子进程中重复执行宿主启动代码。
- 保持安装目录、模块路径和配置结构完整，不要删除看似未使用的兼容模块。
- 标定和型号配置变更后，应使用代表性工件重新验证坐标和匹配结果。

## 9. 日志、保存和常见问题

日志位于安装目录的 `data/logs/`，点云保存在 `data/points/`。
保存格式、块池和退出等待参数见 `ReadDataConfig.toml`。
成功落盘的工件文件清单使用 `.complete.json`；带 `incomplete` 标记或缺少完成清单的数据不能视为完整保存的工件。

| 现象 | 检查项 |
| --- | --- |
| `.pyd` 无法导入/DLL 加载失败 | Python 是否为 CPython 3.11 x64，依赖和运行库是否完整，是否混用了不同版本的组件 |
| 提示工作目录不正确 | 启动前切换到开发包安装根目录，确认 `model/tomls/` 可访问 |
| PLC/激光一直未连接 | IP、端口、网卡、防火墙、设备供电、协议版本及其他程序的连接占用 |
| 启动后首件没有结果 | 首件是否已在扫描区内而触发半件跳过；正向位置和起止阈值是否正确 |
| 一直未匹配 | 坐标原点、滤波、几何分区、型号标准坐标、各轴容差及是否存在多个候选匹配 |
| 界面暂时没有新点云 | 工件是否已完整通过并处理完成；检查设备反馈和日志 |
| 宿主长时间运行后内存增长 | 是否持续轮询并消费结果，业务是否保留大量点云副本，处理/磁盘速度是否跟得上采集 |
| 退出较慢 | 是否仍有保存任务、磁盘写入或工作进程退出等待；查看停止告警 |

提交集成问题时，请提供 Python/系统版本、使用的组件版本或文件摘要、复现步骤、相关日志与配置差异。
