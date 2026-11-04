# Preserve-model upper-layer implementation

User's latest constraint supersedes previous package restructuring: keep existing `control/model/view` and multiprocessing framework. Never edit a used `model` file or either LiDAR control file. Preserve the current 48-axis PLC frame and supplied recognizer/config. A SHA-256 content snapshot (LF-normalized to tolerate Git's CRLF checkout) is in `.scratch/headless-acquisition/model-baseline.json`.

## Tasks and interfaces

- [x] Add regression tests first for model SHA equality, only complete-workpiece strategy, read-only PLC, ID-only matching, existing ControlCenter/Qt bridge lifecycle and simple one-page UI.
- [x] Simplify existing `control/PlcCommunicationProcess.py` to read PLC position/status and send pulse queue entries only; preserve BasePlc/PlcManager interfaces unchanged. Shared stop_event and heartbeat remain in the existing multiprocessing pipeline.
- [x] Keep `control/LidarAcquisitionProcess.py` and strategy interfaces; remove mode 1/3 branches at the control layer, retain mode 2 data collection/save pipeline and model calls verbatim.
- [x] Adapt existing `control/DataProcessingProcess.py`: use unchanged DataFindBlocks and CabinetTypeRecognizer; send one result dictionary per workpiece to result queue; always publish latest point-cloud preview. Model algorithms and configuration remain unchanged.
- [x] Simplify existing QtPipelineRuntime to wire the same PLC/acquisition/processing/save processes, expose result queue and control snapshots, retain async shutdown. MainWindow uses existing ControlCenter and QtUiBridge, only point cloud, PLC/laser connection states, latest matching ID, Start and Exit.
- [x] Add `acquisition_api.py` as an upper-level facade using the existing runtime, plus CLI; continuous Start reuses processes until Exit, each round handles one complete piece.
- [x] Keep `setup.py` Cython framework, compile protected model modules from unchanged source, create allowlisted developer bundle with open view/public interface plus compiled protected control/model dependencies. Report compiler/platform limitations honestly.
- [x] Run targeted and full tests, static imports, model hash verification and GUI rendering check; independent review before completion.

## Verification

`python -m unittest discover -s tests -v`; `python -m compileall -q control view acquisition_api.py main.py qt_main.py`; compare all retained model file hashes with snapshot. No model deletion until import/call dependencies prove it is unused; conservative retention is allowed.

## Scope rulings

Keep model configurations unchanged too, including ModeConfig (runtime rejects values other than 2). Do not rewrite algorithms into another package or change the MVC/multiprocessing framework. Original prototype under `.superpowers/superseded-sdk-prototype` is shelved and not a deliverable.
