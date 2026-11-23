# C545D — Real Windows mixed-size heap identity transfer and address-reuse calibration (2026-11-23 JST)

## Tested facts

Source development: [draft PR #62](https://github.com/taku077/c545d-recorder/pull/62), Windows 2022 GitHub Actions ONLY, not installed on the real Windows 10 recorder.

**Original verified known-lifetime ETW fixture** [#45148410946 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45148410946) was fixed to HeapAlloc(360)→HeapReAlloc(720) and could not establish whether other sizes were handled. To remove that limitation, this update creates:

- \`tests/C545DEtwHeapIdentity/GenericHeapLifetime.cs\` — **size-independent** per-(heap,address) original-allocation lifetime transfer for HeapAlloc, HeapReAlloc old/new address and HeapFree, with bounded provisional old-free-before-realloc matching, address-reuse generation handling, in-place and moved reallocations, source class \`Unresolved\` unless independently proven, phase-aware numerical summaries. Negative test cases cover missing initial allocation, size mismatch, collision, duplicate frees, stale realloc, invalid event/loss flags and false source ownership.
- \`tests/C545DEtwHeapIdentity/GenericEtwFixtureReader.cs\` — actual Microsoft TraceEvent 3.2.8 typed event reader for **one disposable, controlled mixed-size native fixture**. It does not classify GIO allocations by size. The test filters fixed fixture size classes only as a **known calibration marker** and keeps all real source owner assignments \`Unresolved\`. It observes other-size events specifically to retire reused addresses, rather than assigning them to the old owner. Requires private-runner ETL, PID, preworkload barrier, zero-loss controller, no raw output.
- \`tests/c545d_etw_generic_mixed_size_ci.c\` — 24 native \`HeapAlloc\` calls, 8 each of 192/448/832 B; six \`HeapReAlloc\` calls from two objects per class to 544/1216/1800 B, respectively; 18 ordinary frees, 6 held; on \`exit.signal\`, final six explicit frees; \`freed.signal\` **while producer remains alive**; only \`terminate.signal\` after ETW stop and identity comparison.
- \`tests/Invoke-C545DEtwReallocCalibration.ps1\` — \`-GenericMixed -ThroughCleanup\` branch preserves existing original mode. Captures only a short single private Windows ETW interval, checks same PID/zero-lost events/buffers, requires signals, stops ETW **before the process exits**, validates no external ETW sessions clobbered, deletes raw ETL, PDB and paths on exit. No production media, credentials or registry writes, no forced DLL closure.

Microsoft official [ETW_HEAP_EVENT_ALLOC](https://learn.microsoft.com/en-us/windows/win32/memory/etw-heap-event-alloc), [REALLOC](https://learn.microsoft.com/en-us/windows/win32/memory/etw-heap-event-realloc), [FREE](https://learn.microsoft.com/en-us/windows/win32/memory/etw-heap-event-free) supply the heap handle, address, sizes and old/new address. **Their \`Source\` field identifies allocation paths (LFH/lookaside/etc), NOT the allocating source-code function or a GLib owner**. Proper GIO owner claims additionally require a resolved original allocation call stack, not a heap size or a reallocation-group count.

## Failed trials and precise corrections

1. [Mixed-size CI #45167808307 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45167808307): the new model unit tests and C# build PASSED, but the controlled mixed-size actual ETW decoder failed closed. Early error reporting gave only \`source_or_lifetime_unverified\`; controller/reader were updated to disclose **allowlisted numeric counts** and a fixed reason enum (not paths, pointers or stack symbols).
2. [#45168268066 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45168268066): an automatic textual source edit accidentally introduced an unclosed PowerShell quote and duplicated trailing control code. Root cause: JavaScript string replacement special \`$'\` token was interpreted as the remainder of the original string. Restored exact quoted regex and removed duplicate controller tail with Git object content validation. [Original source regression #45168802991 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45168802991).
3. [#45168803028 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45168803028): actual ETW decoder correctly observed 24 original allocations, 6 linked reallocations, 6 held (7,120 B) before final frees; it rejected \`duplicate_provisional_free\` after the test process exit. The first hypothesis was native teardown/other-size address reuse. Added **explicit counting and identity retirement** when an unrelated-size allocation reuses the address of an already-freed selected fixture block; new negative fixtures verify this does not invent a prior owner.
4. [#45169113710 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45169113710) still reported a duplicate provisional free in pre-exit model. Therefore the validation window was tightened, not relaxed: native fixture now signals its final six HeapFree calls and **stays running** until after the ETW recorder has been stopped and analyzed. This is a justified isolation of teardown events, not a blanket ignore/free or global APC quiet proof.
5. [#45169368240 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45169368240) was from a transitional controller/native-source commit: the new process remained alive awaiting \`terminate.signal\`, but the old controller still awaited process exit at \`exit.signal\`. The next change taught controller to await \`freed.signal\`, stop ETW first, then send \`terminate.signal\`; no need to repeat this intermediate defect.

## Verified new mixed-size actual ETW result

**[Windows2022 CI #45169421721 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45169421721), job \`137674751327\`**:

| Metric | Verified numeric value |
|---|---:|
| HeapAlloc 192 / 448 / 832 B | **8 / 8 / 8** |
| Original fixture HeapAlloc | **24** |
| Original HeapReAlloc (moved pointers) | **6** |
| Old-address \`HeapFree\` paired to HeapReAlloc | **6** |
| Final **logical** fixture HeapFree | **24** |
| Held objects after 18 frees, before 6 final frees | **6** |
| Their requested retained bytes | **7120** |
| Held objects after explicit final six frees | **0** |
| Requested bytes remaining after final six frees | **0** |
| Provisional frees not finalized | **0** |
| Reuse of a previously freed fixture address by unrelated-size allocation | **1** |
| Selected-PID heap ETW events | **104** |
| Unrelated-size alloc/realloc/free events | **25 / 0 / 19** |
| Known model self-test outcomes | **3 positive / 18 rejection fixtures** |
| Logger events and buffers lost | **0 (controller precondition)** |
| Native process still alive when ETW stopped | **yes** |
| Real GLib/GIO original stack owner confirmed | **NO** |
| User Windows10/Tapo host touched | **NO** |

The source unit selftest and legacy original 360/720 identity tests also PASS in the same CI. This is real ETW event data from a **native controlled test**, not a 24/7 recording test.

The corrected model does **NOT** conflate the 6 old-address Free events associated with realloc, 24 real logical frees, one address reuse by a different-size unrelated allocation, and Windows native process teardown. Deliberate source class \`Unresolved\` for real stack ownership prevents an unwarranted GLib/GIO attribution. The one address reuse is a distinct observation and did not require a new user measurement.

## What remains and the ONLY next new discriminator

- Implement safe **original HeapAlloc call-stack identity resolution** from real ETL in a disposable Windows CI, e.g. using Microsoft's TraceEvent ETLX \`TraceLog.OpenOrConvert\` and \`TraceEvent.CallStack()\`, with explicit **stack absent/unresolved** counts. Verify with source-named native fixture call stacks, never infer from size, allocator \`Source\`, or a stack-group summary.
- Attach original stack owner token to the generic old→new realloc identity; verify stack IDs and free-after-phase identity with negative fixtures, requiring preworkload ETW, zero logger loss and stage-aligned AppInfo measurements. No raw ETL, stack names, addresses or media uploaded; only aggregate allowlisted owner classes.
- Preserve the **active subscribed** AppInfo phase model: six pending watcher subscriptions were stable in existing GIO 16-cycle run #45133754345 (6→6), while private commit still increased; this is NOT a globally closed WinRT/APC producer epoch. Do not force watchers to zero or claim all caches idle. Reuse previous original logs.
- Only after an actual original owner resolver and comparable active AppInfo epoch are source-verified, consider **one** new bounded disposable Windows GIO identity/PrivateUsage/REGION/handles/CPU comparison, not repeated Windows native calibrations and not user-host long runs.
- Existing release gate remains **4 broad cases EVIDENCE_GAP**, \`release_state=HOLD\`, \`install_approved=0\`, \`live_test_authorized=0\`, real post-patch recorder **untested**. Do not alter recorder DLLs, process, registry, stream layout, x264, audio, MP4 splitting or EOS.

## Source references

- [Native C mixed fixture](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/c545d_etw_generic_mixed_size_ci.c)
- [Generic per-allocation state machine](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/C545DEtwHeapIdentity/GenericHeapLifetime.cs)
- [Microsoft PerfView TraceEvent programmers guide](https://github.com/microsoft/perfview/blob/main/documentation/TraceEvent/TraceEventProgrammersGuide.md) (call stack resolution requires ETLX and is not automatic for all raw ETW events).
