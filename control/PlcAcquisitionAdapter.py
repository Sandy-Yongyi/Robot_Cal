"""Upper lifecycle/telemetry wrapper around the original PLC communication process."""
import multiprocessing
import os
import queue
import time
from control.PlcCommunicationProcess import PlcCommunicationProcess
from model.utils.MachineConfigUtil import get_machine_config_path


class _StopHeartbeat:
    def __init__(self, heartbeat, stop_event):
        self.heartbeat, self.stop_event = heartbeat, stop_event

    def touch(self, *args, **kwargs):
        return self.heartbeat.touch(*args, **kwargs)

    def sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stop_event.is_set():
                raise SystemExit(0)
            self.touch()
            self.stop_event.wait(min(.1, max(0, deadline-time.monotonic())))


class _PulseSnapshots:
    def __init__(self, output):
        self.output = output

    def put(self, message, block=True, timeout=None):
        try:
            self.output.put_nowait(message)
        except queue.Full:
            try:
                self.output.get_nowait()
                self.output.put_nowait(message)
            except (queue.Empty, queue.Full):
                pass

    def cancel_join_thread(self):
        cancel = getattr(self.output, 'cancel_join_thread', None)
        if cancel is not None:
            cancel()


class PlcAcquisitionAdapter(PlcCommunicationProcess):
    def __init__(self, raw_data_queue, pulse_queue, control_queue=None, machine_data_queue=None,
                 strategy_name='complete_workpiece', heartbeat=None, heartbeat_interval_s=1.0,
                 config_dir=None, stop_event=None):
        if strategy_name != 'complete_workpiece':
            raise ValueError('Only strategy_name=2 (complete_workpiece) is supported')
        super().__init__(raw_data_queue, pulse_queue, control_queue, machine_data_queue,
                         strategy_name, heartbeat, heartbeat_interval_s)
        self.stop_event = stop_event if stop_event is not None else multiprocessing.Event()
        self._heartbeat = _StopHeartbeat(self._heartbeat, self.stop_event)
        self.pulse_queue = _PulseSnapshots(pulse_queue)
        if config_dir is not None:
            self.config_dir = config_dir
            for attr, name in (('plc_config_path', 'PlcConfig.toml'), ('read_data_config_path', 'ReadDataConfig.toml'),
                               ('spray_config_path', 'SprayConfig.toml'), ('system_config_path', 'SystemConfig.toml'),
                               ('mode_config_path', 'ModeConfig.toml')):
                setattr(self, attr, os.path.join(config_dir, name))
            self.machine_config_path = get_machine_config_path(config_dir, self.strategy_name)

    @staticmethod
    def create(strategy_name, raw_data_queue, pulse_queue, control_queue=None,
               machine_data_queue=None, heartbeat=None, heartbeat_interval_s=1.0, **kwargs):
        return PlcAcquisitionAdapter(raw_data_queue, pulse_queue, control_queue, machine_data_queue,
                                     strategy_name, heartbeat, heartbeat_interval_s, **kwargs)

    def run(self):
        try:
            if not self.stop_event.is_set():
                super().run()
        finally:
            plc = getattr(self, 'plc', None)
            if plc is not None:
                try:
                    plc.disconnect(self.connection_type)
                except Exception:
                    pass
            self.ui_status.publish(force=True, connected=False, state='stopped')
            self.pulse_queue.cancel_join_thread()

    def _update_plc_data(self):
        if self.stop_event.is_set():
            raise SystemExit(0)
        return super()._update_plc_data()

    def _publish_ui_status(self, connected, force=False):
        data = getattr(self, 'plc_data', None)
        self.ui_status.publish(force=force, connected=connected and not self.simulation_mode,
                               simulated=self.simulation_mode, pulse=int(getattr(data, 'ChainPulse', 0) or 0),
                               motion=self.chain_motion_status,
                               state='connected' if connected else 'error')
