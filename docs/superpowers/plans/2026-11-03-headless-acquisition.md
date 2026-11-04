# Headless Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Replace the Qt/motion application with a complete-workpiece acquisition library and CLI returning matched IDs.

**Architecture:** A synchronous device session reads PLC position and all configured lasers. A pure collector handles complete-workpiece state. Public APIs own resource cleanup and call a pluggable matcher only after a complete capture.

**Tech Stack:** Python 3.11+, NumPy, standard-library sockets/unittest; optional Open3D for existing geometry extraction.

**Spec:** `docs/superpowers/specs/2026-11-03-headless-acquisition-design.md`

**2026-11-03 调整：** 用户要求保留精简 Qt 主窗口和底层保护；暂停原实施计划，尤其不执行删除全部 Qt 的步骤。新方案见 `docs/superpowers/specs/2026-11-03-qt-sdk-distribution-proposal.md`，待确认后更新实施计划。

## Global Constraints

- Only integer `strategy_name = 2` is supported.
- Read `ChainPulse`; big-endian legacy 206-byte payload with 32 axis states.
- Send read requests only; no motion/spray/enable commands.
- Matchers return `str | int | None`; successful CLI stdout is exactly one ID line.
- User-supplied recognizer and cabinet configuration remain intact.
- Paths do not depend on or change caller cwd.

## Review Focus

- TCP boundaries within binary payload must not truncate position data.
- Stationary or reversed movement must not be treated as workpiece completion.
- Late-starting directions and five-frame start confirmation must not lose leading points.
- Timeout, cancellation and partial connection failures must release every socket.
- Distinct coordinate origins must not be merged into a misleading combined cloud.

### Task 1: Configuration and device transport

**Files:** create `robot_cal/config.py`, `errors.py`, `devices.py`; update `model/plc/MovingFrameData.py`, `PlcCommon.py`, `model/lidar/LidarCommon.py`; tests `tests/test_transport.py`, `tests/test_config.py`.

**Interfaces:** `load_config(config_dir=None) -> AcquisitionConfig`; `DeviceSession(config)` context manager with `read(timeout_s) -> (pulse, direction_xy)`; bounded socket operations.

- [ ] Write failing tests for exact legacy offsets, split/coalesced PLC frames including embedded markers, invalid lengths, explicit config paths and invalid modes.
- [ ] Run `python -m unittest tests.test_transport tests.test_config -v`; verify expected failure.
- [ ] Implement protocol, settings validation, explicit paths and bounded connection/session cleanup. Reuse lidar parser/cartesian conversions.
- [ ] Run the same tests; expect all pass.

### Task 2: Whole-workpiece collection

**Files:** create `robot_cal/collector.py`, `types.py`; tests `tests/test_collector.py`.

**Interfaces:** `Workpiece` contains direction XYZ, optional combined XYZ, start/stop pulses and origin metadata; `WholeWorkpieceCollector(config).feed(pulse, direction_xy) -> Workpiece | None`.

- [ ] Write failing tests for normal single/multiple directions, independent origins, five-frame leading buffers, startup half-piece skipping, stopped/reversed chain, wraparound, max length and point budget failure.
- [ ] Run `python -m unittest tests.test_collector -v`; verify expected failure.
- [ ] Implement five-frame thresholds, first-start skip, linked-stop safety, monotonic distance, per-workpiece bounded chunks and normalization. A linked stop with continuing valid points is incomplete and raises an error rather than matching a truncated piece.
- [ ] Run collector and prior tests; expect all pass.

### Task 3: Callable API, matcher and CLI

**Files:** create `robot_cal/api.py`, `matching.py`, `cli.py`, `__init__.py`, `__main__.py`; replace `main.py`; tests `tests/test_api.py`.

**Interfaces:** `scan_workpiece(config_dir=None, *, timeout_s=120, stop_event=None) -> Workpiece`; `acquire_and_match(config_dir=None, *, matcher=None, timeout_s=120, stop_event=None) -> str | int`; CLI `python -m robot_cal --matcher module:function`.

- [ ] Write failing tests for missing/invalid matchers before device connection, None/invalid/success IDs, matcher exceptions, timeouts/cancellation and device busy errors, stdout-only ID and stderr errors.
- [ ] Run `python -m unittest tests.test_api -v`; verify expected failure.
- [ ] Implement session ownership, process-local acquisition lock, lazy imports, optional `MatchingConfig.toml` entrypoint, synchronous matching after connections close, and diagnostic routing.
- [ ] Run API and prior tests; expect all pass.

### Task 4: Cleanup, cabinet adapter and delivery

**Files:** remove old `control/`, `view/`, `model/motionplan/`, `model/plot/`, mode 1 formats/processing, UI/queue/save utility files, Qt entrypoints and machine/spray configurations; simplify remaining configuration; replace packaging/deployment docs. Preserve generic geometry extraction and supplied recognizer.

**Interfaces:** optional `robot_cal.cabinet.CabinetMatcher(config_dir=None)` callable for supplied recognizer. `robot-cal` installed CLI, TOML package data, NumPy core dependency and optional geometry extras.

- [ ] Write failing tests for cabinet adapter forwarding BlockData and treating recognizer 0 as no-match, dependency-free import/help without Qt/Open3D, foreign cwd and package config data.
- [ ] Run targeted tests; verify expected failures.
- [ ] Implement explicit cabinet adapter, decouple geometry config/logger paths, remove dead modules/dependencies, document actual interfaces and hardware limitations.
- [ ] Run `python -m unittest discover -s tests -v`, `python -m compileall -q robot_cal model main.py deployment_check.py`, CLI help/deployment check, build wheel without network and inspect wheel data; expect success.
- [ ] Perform a fresh independent review against design and fix substantive findings with regression tests.

## Execution notes

User explicitly approved design and requested implementation in current project. Execute inline without another approval round. Preserve unrelated working-tree additions. No commits or shared-branch actions are part of delivery; report the working-tree result for review.
