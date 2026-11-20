# C545D core GIO MSVC candidate — release safety gate (DRAFT, NOT FOR INSTALL)

**This is a development-only safety checklist, not an instruction to modify the recorder.**
The current Windows 10 Tapo recording PC has **not** received this candidate. No user action is requested.

## Immutable candidate and evidence

- Source: GLib **2.82.4**, upstream tag commit `ca20e4ac71864f08e980dc044ac96c06d5482b37`.
- Core-only modifications: GAppInfo weak backreferences (`gwin32appinfo.c`), owned Win32 registry UTF-16 pointer (`gwin32registrykey.c`), GStreamer MSVC SDK export visibility (`gio/meson.build`). Diagnostic UWP bypasses, WinRT event bridges, synthetic failure injection, periodic restarts, and runtime registry changes are **excluded**.
- Proven CI artifact (GitHub Actions [#44757713497](https://github.com/taku077/c545d-recorder/actions/runs/44757713497), artifact `14640171070`): `gio-2.0-0.dll`, SHA256 `67b9f7246e4744fef7ee1ead3bed4ce2179c6f0465ec68a92d01dd12b4a3ccad`.
- Reference official **GStreamer 1.28.8 MSVC x64 SDK** GIO SHA256 `a875107c180fb248236d1e96e14f362f117124df2fee1237fa2142b7b363941b`. Exact MSVC export names 2047 vs 2047, missing zero; loaded as a standalone app-local overlay, passed camera-free dual H264 RTP, AAC and 5 short MP4 splitmux/EOS segments.
- 64-cycle A/B ([#44759302126](https://github.com/taku077/c545d-recorder/actions/runs/44759302126) four complete processes, [corrected saved-data CI #44760918648](https://github.com/taku077/c545d-recorder/actions/runs/44760918648)): SDK-registry Key +20929 vs candidate-registry Key -1, candidate total-handle absolute +1. After no-change controls, Key effect SDK+20932 vs candidate+2; PrivateUsage effect SDK+91533312 B vs candidate+1609728 B (**98.2414% less**). Candidate memory still grew; **zero lifetime slope is not proven**.
- This is **Windows Server 2022 CI**, not Windows 10/Tapo/24x365. Synthetic 5-fragment MP4 duration **6.231 seconds** does not verify one-hour production file splitting.

## Actual gst-launch loader isolation verified (2026-11-21 JST)

- **[Windows GitHub Actions #44769321898 — SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44769321898)**, source SHA `6a4bdb2a4f35b2655ad6601616579f5b97bd0f5c`; sanitized numeric artifact **14646598130** downloaded and independently inspected.
- Exact old candidate DLL SHA256 `67b9f7246e4744fef7ee1ead3bed4ce2179c6f0465ec68a92d01dd12b4a3ccad`, official 1.28.8 SDK GIO SHA256 `a875107c180fb248236d1e96e14f362f117124df2fee1237fa2142b7b363941b`, no recompilation.
- **Two REAL `gst-launch-1.0.exe` processes**, not a synthetic DLL loader surrogate: identical `PATH` pointing to candidate overlay first in both modes. From official SDK `bin`, the running process actually loads **SDK original GIO**; from **separate disposable EXE directory** containing a copy of the unchanged `gst-launch` EXE and candidate GIO, the running process actually loads **candidate GIO**. The absolute loaded module paths are checked by Windows `Get-Process.Modules`, compared internally, and never uploaded. Both complete a synthetic `audiotestsrc → S16LE/48kHz mono → wavenc → giosink` pipeline, produce valid output, and exit **0** as confirmed with query-only Win32 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess`.
- Strict numeric evidence `C545D_GIO_LOADER_OBSERVATION,mode=installed,module_expected=1,output_valid=1,process_exit=0` and same fields for `mode=isolated`, plus `C545D_GIO_REAL_PROCESS_LOADER_CI_PASS`. Exact SDK and candidate hashes unchanged. No user recorder action; the only process handle closed belongs to the ephemeral CI query and the child is a synthetic disposable runner process.
- Earlier targeted failures correctly classified: [#44766819276](https://github.com/taku077/c545d-recorder/actions/runs/44766819276) optional `gstpython.dll` discovery warning became a PowerShell 5.1 native command error; [#44767267036](https://github.com/taku077/c545d-recorder/actions/runs/44767267036) 10-second observer missed initialization; [#44767751952](https://github.com/taku077/c545d-recorder/actions/runs/44767751952) official output existed but WAV pipeline needed explicit conversion / process-status evidence; [#44768281349](https://github.com/taku077/c545d-recorder/actions/runs/44768281349) real pipeline generated a **942124-byte** WAV but `Start-Process` exposed a **null ExitCode**; [#44768764258](https://github.com/taku077/c545d-recorder/actions/runs/44768764258) `Start-Process` also exposed a null managed Handle after exit. All CI-only harness issues fixed without changing the candidate DLL; newest CI pass checks actual Windows native exit code.
- **Deployment approval remains HOLD**. Actual user's installed GIO hash is not known; the earlier `1.28.8.1` label is insufficient to establish SDK identity. Windows Server 2022 CI does not prove Windows 10/Tapo two RTSP inputs, 1-hour MP4 fragments, CPU/PrivateUsage/Key-handle lifetime plateau or full 24×365 recording. Do not run host preflight, copy DLLs, change environment/registry or stop recording without future explicit approval.

## Why a hot DLL replacement is forbidden

The production `Record.ps1` locates GStreamer `bin` from fixed installed paths, starts `gst-launch-1.0.exe` by **absolute path**, then prepends that installed `bin` directory to `PATH`. Merely adding a candidate DLL to `PATH` does not ensure it is used. Windows DLL search order is process-dependent; do **not** infer an overlay is in use from the parent PowerShell environment alone.

- **Never** overwrite `gio-2.0-0.dll` in the user's installed GStreamer tree while recording, and never force-close file handles or change registry DLL-search configuration.
- **Never** modify `Record.ps1` recording settings, video positions, bitrate, frame rate, audio, filenames, splitter or EOS just to enable candidate testing.
- **No periodic forced restart** is an acceptable leak fix.
- Avoid copying the candidate into the user's application directory without a proven isolated, version-pinned launch path and a controlled stop.

Microsoft references: [Dynamic-link library search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order), [Dynamic-link library security](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-security).

## Current fail-closed read-only inventory

[tools/Test-C545DCoreGioReadOnly.ps1](../tools/Test-C545DCoreGioReadOnly.ps1) is for **future supervised evaluation only**, with arguments `CandidateDll`, `ManifestFile`, `GStreamerBin`.

It does **not** load/copy/replace DLLs, start or stop any recorder process, run a pipeline, modify registry/PATH/configuration, read camera credentials or save user paths. Only fixed numeric fields are emitted. It blocks for a candidate hash/PE mismatch, unsupported or unknown GStreamer reference hash, missing GStreamer executable, an active recorder process or OS other than verified Windows 10. The `install_approved` field is **always 0**, even for an otherwise compatible host.

**Important:** the tested reference is the exact SDK **1.28.8**, whereas earlier user-host logs identified **1.28.8.1**. Those installed hashes may differ. **Do not bypass or relax the baseline hash check**; independently establish the exact installed file's MSVC exports/loader compatibility before any host acceptance. No user PC check requested now.

## Remaining AI-side work, in order

1. Confirm the preflight script against the signed CI artifact and authentic official SDK on Windows CI; exercise *correct reference*, *tampered candidate*, *unknown runtime*, and *Windows Server 2022 block* without any customer PC changes.
2. Use saved 64-cycle data to quantify late-memory sampling variability. Repeated long stress measurements are not justified until outstanding shorter AI-side analysis is exhausted.
3. Specify a **separate, private app-local GStreamer overlay** startup method that does not alter installed binaries. Test exact DLL loaded in the overlay by Windows loader identity and independent media/EOS safety checks on CI. A normal production launch must remain unchanged by default.
4. Preserve an easy rollback: terminate only an isolated *test* session gracefully, remove its disposable overlay after all its processes exit; since installed DLLs were never changed, normal recorder launch returns to original binaries.
5. After all AI-side checks and explicit user agreement, collect **one consolidated, minimal** Windows 10/Tapo host-specific validation during a natural safe stop. Do not request repeated four-hour measurements. Distinguish live 2×RTSP video/audio/one-hour MP4 continuity from synthetic CI.

## Current decision

**HOLD — candidate usable for CI evidence only.** Do not install/hot-swap or claim 24x365 stability or zero memory leak.
