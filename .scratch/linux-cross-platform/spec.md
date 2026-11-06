# Windows / Ubuntu 24.04 compatibility

目标：Ubuntu 24.04.4 x86_64 Python 3.11 与现有 Windows 同一架构；核心源码不修改，Linux 构建生成路径适配副本，交付 .so 和上层源码。保持策略2、原界面及读取流程。Linux 编译与现场联调需在用户提供的 Ubuntu 环境验证。
