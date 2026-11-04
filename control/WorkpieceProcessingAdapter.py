"""Upper-layer lifecycle/result adapter around the unchanged workpiece processor."""
import multiprocessing
import queue
import sys
import numpy as np
from control.DataProcessingProcess import DataProcessingProcess
from model.dataprocess.complete_workpiece.DataFindBlocks import DataFindBlocks
from model.formats.complete_workpiece.BlockDataFormat import BlockData
from model.utils.WorkpieceOriginUtil import transform_points_for_origin
from model.utils.LoggerUtil import logger, check_and_rotate_log
from control.DataProcessWorker import DataProcessWorker


class WorkpieceProcessingAdapter(DataProcessingProcess):
    def __init__(self, raw_data_queue, machine_data_queue, viz_queue=None, config_dir=None,
                 top_cover_enabled=None, heartbeat=None, heartbeat_interval_s=1.0, *, stop_event=None):
        # The original constructor emits its initial PLC state to this local queue.
        super().__init__(raw_data_queue, queue.Queue(), viz_queue, config_dir=config_dir,
                         top_cover_enabled=top_cover_enabled, heartbeat=heartbeat,
                         heartbeat_interval_s=heartbeat_interval_s)
        self.machine_data_queue = machine_data_queue
        self.result_queue = machine_data_queue
        self.sequence = 0
        self.stop_event = stop_event if stop_event is not None else multiprocessing.Event()

    def _process_data(self, raw_data):
        if not isinstance(raw_data, dict):
            return
        same_origin = int(raw_data.get('translate_data_origin', 1 if 'all_data' in raw_data else 2) or 2) == 1
        keys = ('all_data',) if same_origin else ('left_data', 'right_data')
        if not any(self._has_valid_points(raw_data.get(key)) for key in keys):
            return
        self.sequence += 1
        self._pending_previews = []
        original_queue = self.machine_data_queue
        legacy_output = queue.Queue()
        self.machine_data_queue = legacy_output
        try:
            # Preserve both origin branches, top-cover rule and recognition agreement rule.
            super()._process_data(raw_data)
        finally:
            self.machine_data_queue = original_queue
        legacy = legacy_output.get_nowait()
        identifier = legacy.get('type', 0) or None
        result = {'sequence': self.sequence, 'identifier': identifier,
                  'status': 'matched' if identifier is not None else 'unmatched',
                  'message': '' if identifier is not None else '未匹配到唯一序号'}
        previewed = {id(points) for points, _ in self._pending_previews}
        for key in keys:
            points = raw_data.get(key)
            if self._has_valid_points(points) and id(points) not in previewed:
                self._pending_previews.append((points, None))
        for points, blocks in self._pending_previews:
            self._publish_preview(points, blocks, same_origin=same_origin, result=result)
        self.result_queue.put(result)

    def _push_visualization_data(self, points, block_data):
        self._pending_previews.append((points, block_data))

    def run(self):
        self._heartbeat.touch(force=True)
        sys.stdout, sys.stderr = (self.stdout, self.stderr)
        try:
            self.data_processor = DataFindBlocks()
            while not self.shutdown_flag and (not self.stop_event.is_set()):
                self._heartbeat.touch()
                try:
                    raw_data = self.raw_data_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if raw_data is None:
                    break
                with self._heartbeat.keep_alive(max_duration_s=60):
                    self._process_data(raw_data)
                check_and_rotate_log()
        except Exception as exc:
            logger.exception('Workpiece processing failed')
            self.result_queue.put({'sequence': self.sequence, 'identifier': None, 'status': 'error', 'message': str(exc)})

    def _publish_preview(self, points, block_data, *, same_origin=True, result=None):
        if self.viz_queue is None:
            return
        points_array = np.asarray(points, dtype=float)
        if points_array.ndim == 1:
            points_array = points_array.reshape(1, -1)
        if points_array.shape[1] < 3:
            return
        display_points = points_array[:, :3]
        if same_origin:
            display_points = transform_points_for_origin(display_points, self.read_data_config)
        viz_data = {'points': display_points, 'boxes': block_data if isinstance(block_data, BlockData) else None, 'preview_processed': False, 'match_result': result}
        try:
            self.viz_queue.put_nowait(viz_data)
        except queue.Full:
            try:
                self.viz_queue.get_nowait()
                self.viz_queue.put_nowait(viz_data)
            except (queue.Empty, queue.Full):
                pass


class TxtAcquisitionAdapter(DataProcessWorker):
    """Lifecycle wrapper for the unchanged TXT reader; recognition stays downstream."""
    def __init__(self, machine_data_queue, pulse_queue, viz_queue, data_paths, data_name=None,
                 strategy_name='complete_workpiece', config_dir=None, heartbeat=None,
                 heartbeat_interval_s=1.0, *, stop_event=None, result_queue=None):
        if strategy_name != 'complete_workpiece':
            raise ValueError('Only strategy_name=2 (complete_workpiece) is supported')
        super().__init__(machine_data_queue, pulse_queue, viz_queue, data_paths,
                         data_name=data_name, strategy_name=strategy_name, config_dir=config_dir,
                         heartbeat=heartbeat, heartbeat_interval_s=heartbeat_interval_s)
        self.stop_event = stop_event if stop_event is not None else multiprocessing.Event()
        self.result_queue = result_queue
        # Only downstream processing publishes a preview paired with its recognition result.
        self.draw_type = 2

    def run(self):
        try:
            if not self.stop_event.is_set():
                super().run()
        except InterruptedError:
            if not self.stop_event.is_set():
                raise
        except Exception as exc:
            logger.exception('TXT loading failed')
            if self.result_queue is not None:
                self.result_queue.put({'sequence': 0, 'identifier': None,
                                       'status': 'error', 'message': str(exc)})
        finally:
            if self.stop_event.is_set():
                cancel = getattr(self.machine_data_queue, 'cancel_join_thread', None)
                if cancel is not None:
                    cancel()

    def _load_dataset_points(self, dataset):
        if self.stop_event.is_set():
            raise InterruptedError('TXT acquisition stopped')
        points = super()._load_dataset_points(dataset)
        if self.stop_event.is_set():
            raise InterruptedError('TXT acquisition stopped')
        return points

    def _heartbeat_sleep(self, seconds):
        # Replace only the reader's final indefinite wait with a cancellable wait.
        import time
        deadline = time.monotonic() + seconds
        while not self.stop_event.is_set():
            self._heartbeat_touch()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.stop_event.wait(min(.1, remaining))
