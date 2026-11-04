# Complete-workpiece acquisition interface

Status: resolved

Implement the approved design and plan linked from `../spec.md`.

Acceptance: only upper-layer mode 2, original LiDAR/model code preserved, original framework retained, simple Qt main window, continuous capture/matching until Exit, ID-only single-call/CLI interface, protected developer package, documentation and verification.

## Comments

2026-11-03: User revised Qt requirement: retain one main window with point cloud, connection status, start and exit. Needs SDK distribution boundary and choice of continuous versus single-workpiece GUI operation. The original no-Qt acceptance is superseded; see revised proposal in docs/superpowers/specs/2026-11-03-qt-sdk-distribution-proposal.md. Original implementation stopped before deleting Qt files.

## Answer

Final constraints implemented. 46 unreachable model .py implementations removed; retained model contents checked with normalized hashes; both LiDAR control files match original HEAD. 21 source and compiled-package tests pass, 31 private extensions compile on Windows x64/Python 3.11, compiled package frame/import smoke checks pass; GUI rendered with simulated cloud. Real PLC/laser/recognition accuracy remains a field acceptance task.

Final review: two Important findings fixed with regression tests (unbounded original raw queue; single correlated preview/result publisher). Minor retained-result history capacity is documented in developer guide; host should consume take_results periodically.

Latest UI correction completed: original IndustrialMainWindow/RealtimeControlPage styling restored, original theme/widgets/auth restored, only first navigation entry retained. Matching calls the supplied CabinetTypeRecognizer directly; actual recognizer regression added. User-updated processor signature accommodated with keyword runtime wiring. Independent focused review found startup-close bug; two regressions observed fail and pass after fix. Source and updated compiled developer package both pass 24 tests. Retained model/two-LiDAR checks continue to pass. Native Qt/OpenGL preview inspected with simulated cloud; screenshot `.superpowers/original-style-main-window.png`.

Latest corrections completed: CONTROL_TYPE retains 1/2/3; only acquisition strategy is fixed to2. Stop no longer closes the main window, including stop during startup. DataProcessWorker directly reuses the same processing methods as DataProcessingProcess and emits recognized IDs; mode1 no longer starts duplicate recognition. 40 source tests pass, including actual TXT worker spawn, actual recognizer contract, no-match/cancel and Stop-window preservation. Focused reviews found no new Important/Critical defects after fixes.

2026-11-04: User requires original supplied DataProcessingProcess unchanged, retaining same/independent-origin recognition and top-cover rule. Restored exact saved user source; upper WorkpieceProcessingAdapter handles stop/public results/paired preview. DataProcessWorker shares this processor; PlcCommunicationProcess and TXT worker preserve old method entrypoints, retired strategy1/3 and motion methods are pass rather than deleted. CONTROL_TYPE1/2/3 remains available.

Legacy compatibility verification: 49 source tests passed, including real spawned TXT/live adapter workers, independent-origin TXT pair, recognition agreement including zero, top-cover rule, and unmatched-cloud preview. Original supplied processor byte-identical; all original PLC/TXT method names retained; retained model/two-LiDAR preservation checks pass. Two private extensions rebuilt; SDK regenerated with 31pyd and only README; manifest verified. Full compiled-package execution remains unverified: Windows Application Control blocks loading the rebuilt PlcCommunicationProcess extension both inside and outside sandbox; no policy settings changed. Focused read-only review found no Important/Critical issue.

2026-11-04 correction: User requires DataProcessWorker unchanged too. Restore complete HEAD source, including original inheritance/signature and all frame/TXT/origin methods. Upper TxtAcquisitionAdapter selects strategy2, suppresses unpaired previews and adds cancellable final wait. Runtime mode1 routes original raw TXT output to the same processor as live mode2, exactly once; mode1 uses separate reader and processing processes. This supersedes the earlier direct TXT-worker recognition/pass-method implementation.

Worker restoration verification: DataProcessWorker matches HEAD exactly after newline/BOM normalization, with original default/signatures/class/frame methods restored. Seven focused TXT/processing tests pass, including spawned reader+processor clean stop, independent-origin TXT pair and actual recognizer. Source compile checks pass. During work PlcCommunicationProcess was externally restored to HEAD as well (not an agent edit); it imports deleted FrameQueueManager and motion modules, so full-source integration tests currently fail on import. User clarification pending; PLC file left untouched. No new compiled SDK validation claimed.

2026-11-04 user clarified PLC restoration is intentional: start from original PlcCommunicationProcess, replace deleted dependencies/movement portions with pass; leave all other code unchanged. Applied source-level pass-only edits; original init/create/run/read/connection method signatures retained, seven core read/chain/reconnect method ASTs unchanged. Upper PlcAcquisitionAdapter manages stop/config/telemetry. Removed dependency startup failure resolved. TXT reader feeder cancellation fix applied in upper adapter only; original DataProcessWorker remains unchanged.

Final original-worker restoration validation: source53/53 and compiled developer-package53/53 pass. Restored DataProcessWorker byte-identical to HEAD and DataProcessingProcess byte-identical to saved user version. PLC read/chain/connect/reconnect methods unchanged; deleted/motion dependencies only pass substitutions, with lifecycle/telemetry in upper wrapper. Both private extensions loaded from .pyd in package; prior Windows block did not recur with this new original-based PLC build. SDK has31 extensions and onlyREADME, hashes verified. Focused review found no new Important/Critical PLC wrapper issue; reader feeder cancellation fix has20k-point regression. Model and twoLiDAR preservation checks pass. No physical PLC/laser acceptance performed.

2026-11-04: startup-guard skipped workpiece must save and display point cloud without geometry/recognition. Upper AcquisitionPreviewAdapter enables saver preview only for skipped or incomplete capture, normal output remains processing-paired; runtime connects saver to preview queue; stale match cleared. Three focused and eleven UI tests pass; existing full-suite preservation baseline fails after user configuration and LiDAR source changes, which were not modified or reverted. SDK regenerated.

2026-11-04: User chose timestamps through seconds to distinguish same-minute captures. Saved cloud names now use channel_YYYYMMDD_HHMMSS; unique internal job ID and manifest retained. Same-second collision refuses overwrite. Real shared-memory save test passes outside Windows sandbox; SDK rebuilt and manifest verified.
