"""Keep the original LiDAR acquisition logic and preview skipped workpieces."""
from control.LidarAcquisitionProcess import LidarAcquisitionProcess


class AcquisitionPreviewAdapter(LidarAcquisitionProcess):
    def _save_workpiece_data(self, incomplete=False):
        skip = bool(getattr(self, 'complete_skip_current_workpiece', False)
                    or getattr(self, 'lidar_reconnected', False)
                    or getattr(self, 'plc_reconnected', False))
        if not skip and self.software_first_start and self.start_motion_pulse is not None:
            diff = self._get_forward_pulse_diff(self.start_motion_pulse, self.current_pulse)
            skip = diff / self.read_data_config['pulse_to_mm'] <= self.read_data_config['start_skip_mm']
        original = self.draw_type
        try:
            # The saver publishes only previews for skipped or incomplete captures.
            self.draw_type = 1 if skip or incomplete else 2
            return super()._save_workpiece_data(incomplete=incomplete)
        finally:
            self.draw_type = original
