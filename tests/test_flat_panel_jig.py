import unittest
from unittest.mock import patch

import numpy as np

from acquisition_sdk import DataFindBlocks
from model.utils.TomlLoader import TomlLoader


class FlatPanelJigTests(unittest.TestCase):
    def setUp(self):
        config = dict(
            x_range=300, y_range=300, z_range=300,
            y_threshold=10, z_threshold=10, jig_threshold=30,
            inside_x_use_middle=1, find_y_plane=0.5,
        )
        with patch.object(TomlLoader, "load", return_value=config):
            self.processor = DataFindBlocks()
        panel = [
            (x, y, z)
            for z in range(0, 110, 2)
            for y in range(0, 101, 5)
            for x in range(0, 21, 2)
        ]
        jig = [
            (x, y, z)
            for z in range(40, 61, 2)
            for y in range(110, 151, 2)
            for x in range(0, 21, 2)
        ]
        self.points = np.array(panel + jig, dtype=float)

    def test_flat_panel_block_reports_jig_separately(self):
        self.processor.process_config["send_data_type"] = 2

        result = self.processor.start_process(self.points, lidar_status=0, data_dir=2)

        self.assertEqual(result.outside_data[0].outside_y_max, 100)
        self.assertEqual(len(result.jig_data), 1)
        self.assertEqual(result.jig_data[0].jig_y_min, 100)
        self.assertEqual(result.jig_data[0].jig_y_max, 150)
        self.assertIsNone(result.inside_data)

    def test_narrow_flat_panel_frames_report_jig_without_partitions(self):
        self.processor.process_config.update(
            send_data_type=1, inside_x_use_middle=0, inside_x_min_offset=150,
        )

        frames = self.processor.start_process(self.points, lidar_status=0, data_dir=2)

        self.assertEqual(len(frames), 11)
        self.assertTrue(all(frame.work_type == 1 for frame in frames))
        self.assertEqual(max(frame.jig_dat for frame in frames), 150)
        self.assertTrue(all(frame.partitions is None for frame in frames))
        self.assertTrue(all(frame.merge_partitions is None for frame in frames))
