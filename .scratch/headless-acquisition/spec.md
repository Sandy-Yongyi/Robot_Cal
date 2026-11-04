# Headless acquisition

Status: resolved

Final user requirements on 2026-11-03: retain control/model/view and original multiprocessing pipeline; preserve retained model contents and both LiDAR control files; delete only unused model Python implementations; pass-only compatibility shells for retired upper-layer entries; one Qt main window, continuous mode-2 capture/matching, Start/Exit; README usage/framework and secondary-development distribution.

Final implementation plan: `docs/superpowers/plans/2026-11-03-preserve-model.md`.
Delivery documentation: `README.md`, `docs/framework.md`, `docs/developer-integration.md`.
Earlier headless/new-package proposals are superseded by the user's latest requirements.

Latest UI correction: restore the original theme and first-page layout. Keep only the first left-navigation entry, remove remaining pages; show IDs in the original current-task panel. Match using CabinetTypeRecognizer directly without changing its model file.

Latest control correction: CONTROL_TYPE is a runtime/input selector and retains all original values 1 (TXT+PLC), 2 (live), 3 (TXT view only), including DATA_PATH/DATA_NAME and CLI overrides. Only strategy_name is restricted to 2. Replay/file-view loaders restored; these are NOT the removed first/third acquisition strategies. Motion execution remains disabled. SDK functions continue to select live control_type=2 explicitly via runtime default.

Latest Stop correction: Stop must stop/release acquisition and leave GUI/cloud/result available for restart; only window close exits. Pending startup-stop is separate from pending window-close.
Latest TXT matching requirement: DataProcessWorker directly performs the same processing as DataProcessingProcess. It inherits the shared processing methods, initializes the same DataFindBlocks/CabinetTypeRecognizer and emits identifier results plus paired overlays. Runtime mode1 routes it directly to result/preview queues and does not also start a duplicate DataProcessingProcess. Live mode2 stays unchanged.

## Comments

User chose local Markdown tracking, default triage labels, AGENTS.md, Python + CLI and PLC ChainPulse. Matching code will be supplied separately; preserve newly added recognizer/configuration.

2026-11-04: User requires original supplied DataProcessingProcess unchanged, retaining same/independent-origin recognition and top-cover rule. Restored exact saved user source; upper WorkpieceProcessingAdapter handles stop/public results/paired preview. DataProcessWorker shares this processor; PlcCommunicationProcess and TXT worker preserve old method entrypoints, retired strategy1/3 and motion methods are pass rather than deleted. CONTROL_TYPE1/2/3 remains available.

2026-11-04 correction: User requires DataProcessWorker unchanged too. Restore complete HEAD source, including original inheritance/signature and all frame/TXT/origin methods. Upper TxtAcquisitionAdapter selects strategy2, suppresses unpaired previews and adds cancellable final wait. Runtime mode1 routes original raw TXT output to the same processor as live mode2, exactly once; mode1 uses separate reader and processing processes. This supersedes the earlier direct TXT-worker recognition/pass-method implementation.

2026-11-04 user clarified PLC restoration is intentional: start from original PlcCommunicationProcess, replace deleted dependencies/movement portions with pass; leave all other code unchanged. Applied source-level pass-only edits; original init/create/run/read/connection method signatures retained, seven core read/chain/reconnect method ASTs unchanged. Upper PlcAcquisitionAdapter manages stop/config/telemetry. Removed dependency startup failure resolved. TXT reader feeder cancellation fix applied in upper adapter only; original DataProcessWorker remains unchanged.
