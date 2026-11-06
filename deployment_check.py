"""Read-only deployment preflight; never constructs the hardware runtime."""

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
import sys
import os

from app_bootstrap import application_directory


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_configurations(root: Path) -> tuple[CheckResult, ...]:
    results = []
    for name in (
        "ModeConfig.toml", "ReadDataConfig.toml", "SystemConfig.toml", "PlcConfig.toml",
        "SprayConfig.toml", "ProcessConfig.toml", "LidarConfig.toml", "CabinetTypeConfig.toml",
    ):
        try:
            from model.utils.TomlLoader import TomlLoader
            config = TomlLoader.load(str(root / "model" / "tomls" / name))
            if name == "ModeConfig.toml":
                if type(config.get("strategy_name")) is not int or config['strategy_name'] != 2:
                    raise ValueError('本版本只支持 strategy_name = 2')
        except (ImportError, OSError, ValueError) as exc:
            results.append(CheckResult(name, False, str(exc)))
        else:
            results.append(CheckResult(name, True, "配置可解析"))
    return tuple(results)


def check_windows_plugin(plugin_directory: Path) -> CheckResult:
    path = plugin_directory / "platforms" / "qwindows.dll"
    return CheckResult("Qt Windows 平台插件", path.is_file(), str(path))



def check_linux_plugin(plugin_directory: Path, platform: str = "xcb") -> CheckResult:
    names = {"xcb": "libqxcb.so", "wayland": "libqwayland-generic.so", "offscreen": "libqoffscreen.so"}
    name = names.get(platform)
    if name is None:
        return CheckResult("Qt Linux 平台插件", False, f"不支持的 Qt 平台: {platform}")
    path = plugin_directory / "platforms" / name
    return CheckResult("Qt Linux 平台插件", path.is_file(), str(path))

def run_checks(root: Path) -> tuple[CheckResult, ...]:
    results = list(check_configurations(root))
    # Import native libraries to catch missing Python modules and DLL loaders.
    # No QApplication, controller, socket, or multiprocessing worker is created.
    for module in (
        "PyQt6.QtCore", "PyQt6.QtWidgets", "PyQt6.QtOpenGLWidgets",
        "OpenGL.GL", "numpy", "scipy", "open3d", "tomlkit",
    ):
        try:
            import_module(module)
        except Exception as exc:
            results.append(CheckResult(module, False, str(exc)))
        else:
            results.append(CheckResult(module, True, "模块导入成功"))
    try:
        from PyQt6.QtCore import QLibraryInfo
        plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
        if sys.platform == "win32":
            result = check_windows_plugin(plugins)
        elif sys.platform.startswith("linux"):
            platform = os.environ.get("QT_QPA_PLATFORM", "xcb").split(":", 1)[0]
            result = check_linux_plugin(plugins, platform)
        else:
            result = CheckResult("Qt 平台插件", False, f"不支持的平台: {sys.platform}")
    except Exception as exc:
        result = CheckResult("Qt 平台插件", False, str(exc))
    results.append(result)
    return tuple(results)


def main() -> int:
    root = application_directory()
    print(f"只读部署自检：{root}")
    results = run_checks(root)
    for result in results:
        print(f"[{'OK' if result.ok else 'FAIL'}] {result.name}: {result.detail}")
    failures = sum(not result.ok for result in results)
    print(f"检查 {len(results)} 项，失败 {failures} 项。未启动界面或设备进程。")
    print("此检查不代替平台插件加载、OpenGL 渲染、设备联调或可执行文件验收。")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
