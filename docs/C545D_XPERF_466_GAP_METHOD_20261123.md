# C545D — Xperf 466 arithmetic residual, format and provenance (2026-11-23 JST)

## Question and evidentiary boundaries

Why did the independent Windows-2022 disposable GIO late4 Xperf tests both report exactly **466** as `global_out - accepted_valid_top1024_row_out`, despite different volumes and instrumentation? This is **not** proof that 466 separate addresses, objects, or leaked allocations were present in both traces. The residual is an output-accounting difference, NOT a source-owned object set. `-stacks` shows stacks containing GIO/COM modules, not direct causal owners.

Microsoft documents that [Xperf heap actions](https://learn.microsoft.com/en-us/windows-hardware/test/wpt/heap) support `-stacks`, `-frames`, `-images`, `-top N` and `-totals`. The older [heap-action interpretation](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/xperf/using-actions-to-analyze-process-heap-data) clarifies whole-stack vs top-frame vs image aggregation, that `-top` truncates and the default unspecified limit is 10,000, and that outstanding is HeapAlloc without a matching HeapFree **in the captured interval**. A late4 ETW window cannot account for allocations prior to cycle13 or VirtualAlloc commitments outside heap events. A source frame appearing in a stack is not a unique allocation owner.

## Actual old and new evidence, reproduced without a new Windows run

[Archive-only CI #45131140960](https://github.com/taku077/c545d-recorder/actions/runs/45131140960) downloaded original numeric artifacts:
- [#45059995357, artifact 14768938259](https://github.com/taku077/c545d-recorder/actions/runs/45059995357/artifacts/14768938259): registry last4 global Out=16061, well-formed row Out=15595, **residual=466**. Exactly 30 rows rejected because their reported Out# exceeds Alloc#; 1024/1024 metric rows reached. All 15595 validated outstanding were on *GIO-containing call stacks*.
- [#45062227506, artifact 14770031930](https://github.com/taku077/c545d-recorder/actions/runs/45062227506/artifacts/14770031930): global Out=16252, valid rows Out=15786 (GIO-containing15608 and COM/WinRT-containing178), **residual=466**. Again 30 invalid Out>Alloc rows and top1024 saturation. This new instrumented run had 27 callbacks/24 workers, versus the old 17/18; their PrivateUsage/REGION levels are not comparable improvements or regressions.

`tests/analyze_c545d_etw_saved_pair_residual_ci.py` checks exact original artifact names, sanitized numeric lines, both identities and arithmetic, fail-closed on 10 deliberately corrupted samples, no new Windows runner, no raw ETL or registry data. CI **SUCCESS**.

## New static classification instrument

`tests/analyze_c545d_etw_stack_coverage_bounds_ci.py` measures the following *within the same local raw Xperf stack text only*:

1. Validated row count/Out sum vs GLOBAL.Out (the arithmetic residual).
2. Complete but **rejected** row raw Out/Alloc sums, separately and without validating them as real allocations.
3. Rejected row count and specifically the Out>Alloc subgroup.
4. Whether `TOP N` is fully saturated.
5. Relationship `rejected_raw_out` vs the arithmetic residual: less than/equal/greater than. Equality **does not establish disjoint identity** if Xperf aggregates overlap or if top rows are truncated.

[Source-only CI #45130839574](https://github.com/taku077/c545d-recorder/actions/runs/45130839574) PASS, [updated source CI #45131248581](https://github.com/taku077/c545d-recorder/actions/runs/45131248581) PASS. These are code/fixture checks, not measured GIO memory.

## Real Xperf grouping-mode calibration before choosing new tests

The CI-only **64 HeapAlloc / 48 HeapFree / 16 intentional outstanding** known-owner fixture was reused. [Windows #45131356719](https://github.com/taku077/c545d-recorder/actions/runs/45131356719) ran actual WPT actions on ONE small local ETL and returned:

| Action | Actual sanitized diagnostic |
|---|---|
| Known unfiltered `-stacks` | verified synthetic owner 64 allocated / 16 outstanding |
| `-frames` | exit 0, **no GLOBAL/TOP/Alloc/Outstanding metric records** matching the known stack-report schema |
| `-images` | exit 0, likewise no known metric records |
| `-image` | action returned nonzero |

This does not prove `-frames/-images` produce zero allocations, or that their entire formats are unsupported. It **does** falsify the assumption that the existing `-stacks` line parser can safely interpret those outputs. `-image` is present in one older Microsoft description, but failed on this tested WPT. Avoid another production-size trial based solely on changing one flag.

## One bounded, genuinely differentiating Windows CI trial

Only after the above archive and source preflights passed, [commit `bfac95f`](https://github.com/taku077/c545d-recorder/commit/bfac95f8b3ab9406c6163fd724bb54e5e11c3729) amended the **already-disposable** GIO late4 paired controller to add:
- from the **same captured ETL**, sanitize rejected row raw Out/Alloc counts in original `-stacks -top 1024`;
- rerun *offline Xperf analysis on that same ETL* with `-stacks -top 8192`, then sanitize corresponding coverage/invalid-row counts;
- leave the existing full-owner classification gate fail closed, preserve same-run QPC/PrivateUsage/REGION, and retain raw ETL/stacks on the temporary runner only.

[Windows #45131569995](https://github.com/taku077/c545d-recorder/actions/runs/45131569995) is **pending at this document's initial write**; inspect final job/log before asserting any new rows. This is one bounded Windows2022 GIO trial with NEW numeric discrimination, **not** a 4-hour user-PC repeat or another attempt to relabel 466 as a leak. Do not run the same old 16-cycle/top1024 again without a new discriminator.

### Decision rules after Windows trial

- If wider 8192 report increases validated Out and shrinks arithmetic residual, top1024 truncation matters; report the exact numerical change **without** declaring formerly missing bytes to be leaks.
- If the raw rejected Out sum matches residual, that is only one consistent numeric explanation; cannot conclude the 466 are exactly rejected rows while topN remains saturated or report rows may overlap.
- If raw rejected Out sum exceeds residual, per-row aggregates are not a disjoint inventory, so an allocation/free identity reader or another validated grouping is necessary.
- If wider count is insufficient/invalid and/or report exceeds the private 16MiB bound, publish the exact allowlisted reason and improve trace-format-specific evidence **before** any new long/multi-cycle measurement.
- Only an independently proven source-owned HeapAlloc/HeapFree lifetime through a justified callback/worker epoch, reconciled with same-PID commit sampling, can classify retained memory as transient vs bounded vs leak. QPC-negative worker overlap alone cannot prove global APC/WinRT quiet.

## Safety / release

All four `docs/MEMORY_CLASSIFICATION_CASES.json` cases stay `EVIDENCE_GAP`, production `HOLD`. No user work, actual Tapo camera, Windows10 recorder process, DLL swap or host registry change. Keep stream1 left/stream6 right, 2560x720@15, x264 medium QP24, AAC mono48kHz/192kbps target, hourly MP4, synchronized video/audio, avdec_h264 and safe EOS unchanged.

## Verified result of the one bounded GIO Windows trial

[Windows CI #45131569995](https://github.com/taku077/c545d-recorder/actions/runs/45131569995), job `137548033424` at tested source [`bfac95f`](https://github.com/taku077/c545d-recorder/commit/bfac95f8b3ab9406c6163fd724bb54e5e11c3729), **overall workflow FAILURE due intentionally strict complete source-owner gate**. The Windows GIO MSVC build and **2047 official SDK exports PASS**, zero-loss nochange ETW late4 Out#0 (Alloc8048), registry ETW late4 **Alloc619936, Out16061, rounded OutKB890.8**. The two new local Xperf reports from the SAME original ETL did produce safe numeric results:

| Measurement | Requested `-top 1024` | Requested `-top 8192` |
|---|---:|---:|
| Xperf actual `TOP` header and metric stack rows | 1024 | **1164** |
| Well-formed rows | 994 | **1134** |
| Rows with `Out# > Alloc#` | **30** | **30** |
| Well-formed rows Alloc sum | 584552 | **619936** |
| Well-formed rows Out sum | 15595 | **15595** |
| 30 rejected rows raw Alloc sum | **0** | **0** |
| 30 rejected rows raw Out sum | **466** | **466** |
| All rows raw Out sum | **16061** | **16061** |
| Independently observed GLOBAL.Alloc / GLOBAL.Out | 619936 / 16061 | 619936 / 16061 |

**New finding:** the 466 arithmetic residual is *entirely numerically accounted for by 30 zero-Alloc, positive-Out Xperf stack groups* in this trial. Widening the requested cap from1024 to8192 added 140 stack groups, raising valid Alloc counts by **35384** to equal GLOBAL.Alloc, but did not add outstanding blocks. The wider report emitted only **1164 groups**, below the requested 8192, so for this trace it is not top-N truncated. This is a **complete aggregate count reconciliation** (Alloc and Out sums), but **not** verified owner-lifetime attribution for these 30 groups. Source-frame membership, heap realloc grouping semantics and historical untraced allocation states remain unverified, and an Out#>Alloc# row does not by itself prove a leak.

**Parser assumption corrected without another Windows run:** the original `tests/analyze_c545d_etw_stack_coverage_bounds_ci.py` used equality of `TOP N` header and row count as evidence of saturation. Actual Xperf prints `TOP 1164` even though **the invocation requested `-top 8192`**, so that inference was invalid. [`61cd029`](https://github.com/taku077/c545d-recorder/commit/61cd0295e27062b90f36a16cfb2801846b7479ea) separates `top_header_rows` from explicitly supplied `requested_top`; without the requested bound, truncation remains unknown and cannot be silently asserted. A broad-count reconciliation cannot by itself mark 466 addresses as leaked.

Additional same-run 0→16 GIO resource comparisons (different interval from ETW's cycles13→16): PrivateUsage controlled **+385024 B**, Heap REGION controlled **+389120 B**, HeapWalk BUSY controlled **-3610 B**; registry callbacks17, workers18, QPC stop worker overlap0, one worker returned after stop-ack. These values do not establish cause or new cross-run improvement. No Tapo device/host changed.

### Technical next discriminator, no user measurements

Examine the actual pinned Xperf `Realloc` metric treatment and whether zero-Alloc/positive-Out groups can represent a **reallocation attribution or missing-allocation-stack group**, then construct a *small deterministic HeapReAlloc source fixture and fail-closed group classifier* in isolated Windows CI, not another GIO 16-cycle trace. Prove/deny that mechanism before another candidate-GIO measurement. Only after source-backed mapping can the 30 groups receive a valid owner label; a row with nonzero Out and zero Alloc is not automatically a malformed heap or source leak. Keep the four global classification cases OPEN and recorder release HOLD.

## 2026-11-23 JST — Xperf zero-Alloc/positive-Out grouped by HeapReAlloc is a REAL VALID reporting pattern

A separate **synthetic**, non-GIO, isolated Windows 2022 test uses `tests/c545d_etw_realloc_transfer_ci.c`, `tests/analyze_c545d_etw_realloc_transfer_ci.py`, `tests/Invoke-C545DEtwReallocCalibration.ps1` and workflow `.github/workflows/c545d-etw-realloc-transfer-ci.yml`. Explicit barriers start ETW before fixture operations; known sequence: 64 `HeapAlloc(360)`, then 16 `HeapReAlloc(...,720)` through a different noinline function, free 48, keep 16 only until ETW stop. No real device, GLib or recorder.

- First synthetic [Windows CI #45133170372 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45133170372) captured ETW but failed to verify original source frame due the new test source compiler using `/O2` and missing precise output diagnostics. It is a test-instrumentation failure, **not** a GIO leak.
- Fixed in atomic source revision [`a94c576`](https://github.com/taku077/c545d-recorder/commit/a94c5763b5fbb5468151347f10dc1cd7909aa9db): same `/Od` source frame preservation as previous calibrated HeapAlloc fixture, plus a strict numeric-only failure report. **[Windows CI #45133407278 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45133407278)**, job 137553886631, truly measured:
  - `global_alloc=81, global_out=16` (one incidental system allocation, not fixture source).
  - **Original allocation stack**: `Alloc=64, Realloc=0, Out=0`.
  - **Reallocation stack**: **`Alloc=0, Realloc=16, Out=16`**.
  - Local `-stacks -top4096` also shows full 4 rows with 1 `Out#>Alloc#` group; **raw rejected group Out=16 = GLOBAL.Out - wellformed.Out**. Event/lost buffer zero verified; original 16 are *intentionally held*, **not a leak**.
- **Conclusion that changes the parser contract**: a `Realloc` stack with `Alloc=0, Out>0` is a valid, source-calibrated Xperf aggregation phenomenon. The old predicate `Out#<=Alloc#` for every individual call stack **is too strict** as a general validity rule. A stack may describe where a block was *reallocated*, not where initially allocated. This does NOT yet say all 30 GIO zero-Alloc/positive-Out groups are realloc frames; their per-group Realloc counters were missing from the previously sanitized GIO artifact.
- **New discriminating GIO measurement**: on a single short Windows 2022 disposable paired run [#45133754345](https://github.com/taku077/c545d-recorder/actions/runs/45133754345), commit [`64f1b27`](https://github.com/taku077/c545d-recorder/commit/64f1b274be236f27296010c35775cfe6f858e0e2), the original `TOP1024` and exhaustive requested `TOP8192` reports from the SAME ETL now produce sanitized `rejected_raw_realloc_sum`, `out_exceeds_alloc_realloc_compatible_rows`, incompatible counts, plus explicitly distinguished **requested top limit vs printed TOP header row count**. This workflow is **in progress at this note creation**; do not infer a positive or negative GIO realloc result until jobs/logs confirmed.
- **Pass/fail interpretation**: if the same 30 rows have `realloc>=out-alloc` per row, this shows the GIO group shape is *compatible* with observed realloc events, not that memory is permanently retained or the original allocation owner is proven. Any failed row or source mismatch remains an explicit case with next missing evidence. Global WinRT/APC closure, later freeing, and PrivateUsage/committed heap cause still need a justified lifetime boundary. Do not rerun original user four-hour captures or force production restarts.

Classification ledger remains four `EVIDENCE_GAP` and release `HOLD`. No host/registry/DLL deployment and no user action.

## 2026-11-23 JST — actual GIO Realloc counts fully reconcile 466, and source-only original-owner lifetime model is now tested

**Actual original Windows 2022 GIO [CI #45133754345](https://github.com/taku077/c545d-recorder/actions/runs/45133754345), source [`64f1b27`](https://github.com/taku077/c545d-recorder/commit/64f1b274be236f27296010c35775cfe6f858e0e2).** Overall workflow `FAILURE` from *existing strict origin-owner proof gate*, NOT a new DLL/recording failure. MSVC GLib/GIO 2.82.4 build and **2047 exported SDK names PASS**, both paired process ETW captures completed with zero checked lost buffers/events, same-run QPC and resource postmortem succeeded; synthetic source parser preflight [#45133754193 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45133754193).

| Xperf scoped late-four numeric, registry arm | Measured |
|---|---:|
| GLOBAL.Alloc / GLOBAL.Out | 619937 / 16062 |
| Nochange global Out | 0 |
| Validated (old strict condition) stack Out | 15596 |
| Requested `-top8192`: actual number of groups | 1166 |
| Zero-Alloc, Out-positive stack groups | **31** |
| Their raw Realloc / raw Out counts | **3604 / 466** |
| Groups satisfying `Alloc+Realloc >= Out` | **31 of 31** |
| Incompatible groups under this necessary condition | **0** |
| Complete raw Alloc and Out numeric reconciliation | **yes** |
| Causal original HeapAlloc owner / matched later HeapFree | **not proven** |

The independently calibrated **64 original allocation /16 realloc /48 free** fixture [#45133407278 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45133407278) demonstrated a real positive case `realloc_source Alloc0/Realloc16/Out16`; this is why per-group `Out<=Alloc` **must not be required without considering Realloc semantics**. Microsoft [ETW_HEAP_EVENT_REALLOC](https://learn.microsoft.com/en-us/windows/win32/memory/etw-heap-event-realloc) exposes `OldAddress/NewAddress/OldSize/NewSize`, and Microsoft's [Xperf process-heap analysis](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/xperf/using-actions-to-analyze-process-heap-data) explicitly distinguishes `Realloc` from `Alloc`. The 466 group-accounting anomaly is now **numerically explained as reallocation-compatible stack grouping**, **not** demonstrated as an actual memory leak or as the identity of 466 source allocations.

Source-only [`tests/analyze_c545d_gio_etw_realloc_saved_ci.py`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/analyze_c545d_gio_etw_realloc_saved_ci.py) strictly downloads original *sanitized-only* Windows artifact **14799580784** from #45133754345, checks full group counts plus same-run PrivateUsage `+331776 B` / heap REGION `+303104 B` / BUSY `-7734 B` (cycle0→16, distinct from ETW cycles13→16), worker callbacks17/instances18 and QPC no overlapping GIO rebuild at ETW stop. **[Archive CI #45134515275 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45134515275)**, eleven corrupt cases rejected. No extra Windows runner for replay and no raw ETL/addresses/stack source rows uploaded. The status remains `real_GIO_expected_lifetime_unproven`.

**New source-only lifetime model** [`tests/analyze_c545d_realloc_origin_lifetime_ci.py`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/analyze_c545d_realloc_origin_lifetime_ci.py) transfers original allocation identity through `old_address→new_address`, including inplace resize, and tests before/after source-specific free. It rejects orphan reallocs, stale frees, wrong size, collisions, lost events and unverified producer epoch. [CI #45134991894 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45134991894). **This is a synthetic state-machine test only**; the actual Windows ETW event decoder and real producer-closed callback/WinRT/APC acknowledgment are still missing.

### Correct next AI-only engineering work

1. **Do not repeat** original 16-cycle GIO top1024/top8192 tests, old four-hour Windows10 UMDH/WPR, or synthetic realloc group calibration. They answered their targeted format questions.
2. Inspect available official ETW payload reader implementations and develop a validated disposable Windows event adapter for the raw `ETW_HEAP_EVENT_ALLOC/REALLOC/FREE` events with the original-address identity chain. Source and negative fixtures first; upload only numeric owner/lifetime summaries. An orphan realloc of a previously untraced allocation must be rejected explicitly; previous late4 traces began after 12 GIO cycles, so they cannot by themselves identify earlier original allocations.
3. Create a source-backed closed-producer epoch that differentiates watcher APC completion, queued AppInfo workers and WinRT callbacks. QPC no-work-at-Xperf-stop and 2.5s passive wait are not proof of globally completed asynchronous sources.
4. Only if both new observables are available, run **one** bounded disposable Windows GIO lifetime comparison with same-PID PrivateUsage/heap region and explicit phase windows. A true real Windows10 Tapo recording release test still needs explicit approval, and must be consolidated; no user action now.

**State:** numeric 466 report classification subproblem **explained**, all four broader `docs/MEMORY_CLASSIFICATION_CASES.json` cases remain **OPEN/EVIDENCE_GAP**, recorder release **HOLD**, `install_approved=0,live_test_authorized=0,real_device_untested=1`. No real host DLL/registry/camera/media changes.
