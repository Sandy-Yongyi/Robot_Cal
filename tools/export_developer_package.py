"""Allowlisted developer export: public UI/callers + compiled protected modules.

Does not compile, delete, or modify model source. Missing any binary fails before export.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import platform
try:
    from tools.linux_compat import linux_source_text
except ModuleNotFoundError:
    from linux_compat import linux_source_text


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_CONTROL = ('LidarAcquisitionProcess', 'LidarAcquisitionStrategies', 'PlcCommunicationProcess',
                   'DataProcessingProcess', 'PointCloudSaveProcess')


def protected_modules(root=ROOT):
    result = []
    for file in sorted((root / 'model').rglob('*.py')):
        if file.name != '__init__.py' and '__pycache__' not in file.parts:
            result.append(('.'.join(file.relative_to(root).with_suffix('').parts), file))
    for name in PRIVATE_CONTROL:
        result.append(('control.' + name, root / 'control' / (name + '.py')))
    return result


def export_package(binary_dir, output_dir, root=ROOT):
    binary_dir, output_dir = Path(binary_dir).resolve(), Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(f'Refusing to overwrite existing output: {output_dir}')
    binaries = []
    protected_sources = set()
    for module, source in protected_modules(root):
        relative = Path(*module.split('.'))
        candidates = list((binary_dir / relative.parent).glob(relative.name + '.*.pyd'))
        candidates += list((binary_dir / relative.parent).glob(relative.name + '.*.so'))
        candidates += [p for p in (binary_dir / relative.with_suffix('.pyd'),) if p.exists()]
        if len(candidates) != 1:
            raise FileNotFoundError(f'Expected exactly one compiled extension for {module}, found {len(candidates)} in {binary_dir}')
        binaries.append((candidates[0], relative.parent / candidates[0].name))
        protected_sources.add(source.resolve())
    open_files = [root / name for name in ('main.py', 'qt_main.py', 'app_bootstrap.py', 'deployment_check.py',
                                           'acquisition_api.py', 'README.md', 'requirements.txt')]
    open_files += [p for p in (root / 'view').rglob('*.py') if '__pycache__' not in p.parts]
    open_files += [p for p in (root / 'control').glob('*.py') if p.resolve() not in protected_sources]
    open_files += list((root / 'model/tomls').glob('*.toml'))
    # Model package initializers are empty in this project. Never accidentally export new private code in them.
    for init in (root / 'model').rglob('__init__.py'):
        if init.read_text(encoding='utf-8-sig').strip():
            raise ValueError(f'Nonempty private package initializer requires an explicit build rule: {init}')
        open_files.append(init)
    if any(not file.is_file() for file in open_files):
        raise FileNotFoundError('A required public source/config/document file is missing')
    output_dir.mkdir(parents=True)
    for file in open_files:
        destination = output_dir / file.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith('linux') and file.relative_to(root).as_posix() == 'control/DataProcessWorker.py':
            destination.write_text(linux_source_text(file.read_text(encoding='utf-8-sig')), encoding='utf-8')
        else:
            shutil.copy2(file, destination)
    for source, relative in binaries:
        destination = output_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    built = datetime.now(timezone(timedelta(hours=8)))
    info = {"package_version": built.strftime("%Y%m%d.%H%M%S.%f"),
            "built_at": built.strftime("%Y-%m-%d %H:%M:%S UTC+08:00"),
            "platform": sys.platform, "architecture": platform.machine(),
            "python_version": platform.python_version()}
    (output_dir / 'package-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    readme = output_dir / 'README.md'
    content = readme.read_text(encoding='utf-8-sig')
    marker = '<!-- PACKAGE_BUILD_INFO -->'
    if marker not in content:
        raise ValueError('README is missing the package build information marker')
    readme.write_text(content.replace(marker, f"打包时间：{info['built_at']}  \n打包版本：`{info['package_version']}`", 1), encoding='utf-8')
    manifest = {str(p.relative_to(output_dir)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output_dir.rglob('*')) if p.is_file()}
    (output_dir / 'package-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return output_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(export_package(args.binary_dir, args.output))


if __name__ == '__main__':
    main()
