import tempfile
import json
import re
import unittest
from pathlib import Path

from tools.export_developer_package import export_package, protected_modules


class DistributionTests(unittest.TestCase):
    def test_missing_binary_refuses_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                export_package(Path(tmp) / 'binaries', Path(tmp) / 'developer')
            self.assertFalse((Path(tmp) / 'developer').exists())

    def test_export_includes_public_code_and_binary_but_no_private_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binaries = root / 'binaries'
            for module, _ in protected_modules():
                file = binaries / (module.replace('.', '/') + '.cp311-win_amd64.pyd')
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'unit-test binary placeholder; not an executable')
            output = root / 'developer'
            export_package(binaries, output)
            self.assertTrue((output / 'view/qt/main_window.py').is_file())
            self.assertTrue((output / 'acquisition_api.py').is_file())
            self.assertTrue((output / 'model/tomls/CabinetTypeConfig.toml').is_file())
            self.assertFalse((output / 'model/lidar/LidarCommon.py').exists())
            self.assertFalse((output / 'control/LidarAcquisitionProcess.py').exists())
            self.assertFalse(list(output.rglob('*.c')))
            self.assertFalse(list(output.rglob('*.pdb')))
            self.assertTrue((output / 'package-manifest.json').exists())
            info = json.loads((output / 'package-info.json').read_text(encoding='utf-8'))
            self.assertRegex(info['built_at'], r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\+08:00$')
            self.assertIn(info['built_at'], (output / 'README.md').read_text(encoding='utf-8'))
            self.assertIn(info['package_version'], (output / 'README.md').read_text(encoding='utf-8'))
            self.assertIn('package-info.json', json.loads((output / 'package-manifest.json').read_text(encoding='utf-8'))) 
            self.assertEqual([p.relative_to(output).as_posix() for p in output.rglob('*.md')], ['README.md'])
