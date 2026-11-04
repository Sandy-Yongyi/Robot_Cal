import io
import multiprocessing
import queue
import unittest
from control.PlcAcquisitionAdapter import PlcAcquisitionAdapter, _StopHeartbeat
from model.utils.ProcessHeartbeat import ProcessHeartbeat


class SimulatedPlcAdapter(PlcAcquisitionAdapter):
    def __init__(self, raw, pulse, stop):
        super().__init__(raw, pulse, multiprocessing.Queue(), stop_event=stop)
        self.simulation_mode = True
        self.stdout, self.stderr = io.StringIO(), io.StringIO()


class PlcAdapterTests(unittest.TestCase):
    def test_original_simulated_read_loop_can_stop_as_process(self):
        raw, pulses = multiprocessing.Queue(), multiprocessing.Queue(maxsize=2)
        stop = multiprocessing.Event()
        worker = SimulatedPlcAdapter(raw, pulses, stop)
        try:
            worker.start()
            self.assertIn('pulse', pulses.get(timeout=15))
            stop.set()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 0)
        finally:
            stop.set()
            if worker.pid is not None and worker.is_alive():
                worker.terminate()
                worker.join(timeout=2)
            for output in (raw, pulses):
                output.close()
                output.join_thread()

    def test_reconnect_wait_can_be_cancelled(self):
        stop = multiprocessing.Event()
        stop.set()
        with self.assertRaises(SystemExit):
            _StopHeartbeat(ProcessHeartbeat(None,1), stop).sleep(10)
