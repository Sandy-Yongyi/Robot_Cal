import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from model.utils.PointCloudSaveBuffer import SharedPointCloudPool, PointCloudSaveBuffer
from control.PointCloudSaveProcess import save_job

class PointCloudNameTests(unittest.TestCase):
    def test_names_use_seconds_and_refuse_same_second_overwrite(self):
        pool = SharedPointCloudPool.create(1024, 4)
        writer = PointCloudSaveBuffer(pool.descriptor, queue.Queue())
        try:
            with tempfile.TemporaryDirectory() as folder:
                writer.append('left', np.array([[1.,2.,3.]]))
                job = writer.seal('20261104_104951_338138_57632_3', filename_suffix='20261104_104951_338138_57632_3', preview_enabled=False)
                save_job(job, pool.descriptor, folder)
                file = Path(folder) / 'left_20261104_104951.txt'
                self.assertTrue(file.is_file())
                original = file.read_bytes()
                writer.append('left', np.array([[4.,5.,6.]]))
                other = writer.seal('20261104_104951_999999_42_4', filename_suffix='20261104_104951_999999_42_4', preview_enabled=False)
                with self.assertRaises(FileExistsError):
                    save_job(other, pool.descriptor, folder)
                self.assertEqual(file.read_bytes(), original)
        finally:
            writer.close()
            pool.close()
