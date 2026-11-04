"""Public secondary-development facade for the existing control/model/view framework."""

from __future__ import annotations

import argparse
from collections import deque
import contextlib
import math
from pathlib import Path
import sys
import time

from app_bootstrap import application_directory


class NoMatchError(RuntimeError):
    """A complete workpiece did not produce a unique identifier."""


class AcquisitionClient:
    """Own one existing multiprocessing pipeline; poll from one controlling thread.

    Start runs continuously. Each round processes one complete workpiece.
    Run from the application directory, as required by the unchanged model loaders.
    This interface and the GUI must not start separate pipelines for the same hardware.
    """

    def __init__(self):
        self._runtime = None
        self._results = deque()

    def start(self):
        if Path.cwd().resolve() != application_directory():
            raise RuntimeError('请先将工作目录切换到软件根目录，再启动原有采集框架')
        if self._runtime is None:
            from control.QtPipelineRuntime import QtPipelineRuntime
            self._runtime = QtPipelineRuntime(control_type=2)
        try:
            self._runtime.start_pipeline()
        except BaseException:
            self.stop()
            raise

    def poll(self):
        if self._runtime is None:
            return {}
        snapshot = self._runtime.poll()
        self._results.extend(snapshot.get('results', ()))
        return snapshot

    def take_results(self):
        results = list(self._results)
        self._results.clear()
        return results

    def stop(self):
        if self._runtime is not None:
            errors = self._runtime.stop_pipeline() or []
            if errors:
                raise RuntimeError('；'.join(map(str, errors)))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def acquire_and_match(*, timeout_s=120, stop_event=None):
    """Wait for one result and return its ID; always stop and release this pipeline.

    timeout_s bounds result polling after startup. Original connection/start/save-drain
    timeouts remain unchanged; final shutdown can take additional time.
    """
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError('timeout_s 必须为正有限数')
    client = AcquisitionClient()
    try:
        client.start()
        deadline = time.monotonic() + timeout_s
        while True:
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError('采集已取消')
            snapshot = client.poll()
            if snapshot.get('fault'):
                raise RuntimeError(snapshot['fault'])
            for result in client.take_results():
                if result.get('status') == 'matched' and result.get('identifier') is not None:
                    return result['identifier']
                if result.get('status') == 'error':
                    raise RuntimeError(result.get('message', '匹配异常'))
                raise NoMatchError(result.get('message') or '未匹配到唯一序号')
            if time.monotonic() >= deadline:
                raise TimeoutError('等待工件采集匹配结果超时')
            time.sleep(.02)
    finally:
        client.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description='采集一个完整工件并只输出匹配序号')
    parser.add_argument('--timeout', type=float, default=120, help='启动后等待首件结果的秒数，默认 120')
    args = parser.parse_args(argv)
    from app_bootstrap import prepare_environment
    prepare_environment()
    try:
        # Original model/control diagnostics are kept, redirected away from the ID protocol.
        with contextlib.redirect_stdout(sys.stderr):
            identifier = acquire_and_match(timeout_s=args.timeout)
    except (Exception, KeyboardInterrupt) as exc:
        print(str(exc) or '已取消', file=sys.stderr)
        return 1
    print(identifier)
    return 0


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
