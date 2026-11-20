import hashlib
import json
import unittest
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

    def test_legacy_acquisition_processes_are_removed(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('LidarAcquisitionProcess', 'LidarAcquisitionStrategies',
                     'PointCloudSaveProcess', 'PointCloudFileProcess'):
            self.assertFalse((root / 'control' / f'{name}.py').exists())
