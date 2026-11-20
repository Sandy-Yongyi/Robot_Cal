"""Keep the original LiDAR acquisition logic and preview skipped workpieces."""
from acquisition_sdk import LidarAcquisitionProcess


class _SaveJobs:
    def __init__(self, queue):
        self.queue = queue

    def put_nowait(self, job):
        job["filename_suffix"] = "_".join(job["job_id"].split("_", 2)[:2])
        return self.queue.put_nowait(job)


class _CaptureResults:
    def __init__(self, worker, output):
        self.worker = worker
        self.output = output

    def put(self, packet):
        if any(key in packet for key in ('all_data', 'left_data', 'right_data')):
            packet['capture_end_pulse'] = self.worker.current_pulse
            packet['capture_plc_generation'] = self.worker.plc_connection_generation
        self.output.put(packet)

    def cancel_join_thread(self):
        self.output.cancel_join_thread()


class AcquisitionPreviewAdapter(LidarAcquisitionProcess):
    def run(self):
        self.raw_data_queue = _CaptureResults(self, self.raw_data_queue)
        return super().run()

    def _save_workpiece_data(self, incomplete=False):
        skip = bool(getattr(self, 'complete_skip_current_workpiece', False)
                    or getattr(self, 'lidar_reconnected', False)
                    or getattr(self, 'plc_reconnected', False))
        if not skip and self.software_first_start and self.start_motion_pulse is not None:
            diff = self._get_forward_pulse_diff(self.start_motion_pulse, self.current_pulse)
            skip = diff / self.read_data_config['pulse_to_mm'] <= self.read_data_config['start_skip_mm']
        original = self.draw_type
        save_queue = self.save_task_queue
        if save_queue is not None:
            self.save_task_queue = _SaveJobs(save_queue)
        try:
            # The saver publishes only previews for skipped or incomplete captures.
            self.draw_type = 1 if skip or incomplete else 2
            return super()._save_workpiece_data(incomplete=incomplete)
        finally:
            self.draw_type = original
            self.save_task_queue = save_queue
