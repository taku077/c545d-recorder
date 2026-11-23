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
