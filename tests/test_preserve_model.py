import hashlib
import json
import unittest
import subprocess
from pathlib import Path


class ModelPreservationTests(unittest.TestCase):
    def test_every_retained_model_file_is_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / '.scratch/headless-acquisition/model-baseline.json').read_text(encoding='utf-8'))
        for filename, digest in baseline.items():
            file = root / filename
            if file.exists():
                with self.subTest(filename=filename):
                    self.assertEqual(hashlib.sha256(file.read_bytes().replace(b'\r\n', b'\n')).hexdigest(), digest)

    def test_two_lidar_control_files_are_original(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('control/LidarAcquisitionProcess.py', 'control/LidarAcquisitionStrategies.py'):
            original = subprocess.check_output(['git', '-c', 'safe.directory=D:/Code/Robot_Cal', 'show', 'HEAD:' + name], cwd=root)
            self.assertEqual((root / name).read_text(encoding='utf-8-sig'), original.decode('utf-8-sig').replace('\r\n', '\n'))
