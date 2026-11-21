# C545D production recorder private mirror — CI-only source-equivalence gate (2026-11-21)

**NOT FOR HOST EXECUTION / NOT AN INSTALLER / PRODUCTION CANDIDATE HOLD.**

This is the latest step after the official Windows 10 installed SDK six-core
read-only fingerprint matched 6/6 while the normal recorder was active.
There is still no approval to stop, test, or replace the user's recording DLLs.

## What is implemented

1. [New-C545DIsolatedProductionMirrorCI.ps1](../tools/New-C545DIsolatedProductionMirrorCI.ps1)
   reads the version-controlled `Record.ps1`, parses its PowerShell AST
   and requires **exactly one** `$bin = Find-GstBin` assignment. It emits
   a disposable CI-owned copy by substituting ONLY that assignment with an
   absolute private `bin` path; an exact roundtrip comparison proves that
   every other byte of script text is unchanged. The private `bin` must
   be under the direct CI-owned `RUNNER_TEMP` child with an owner marker,
   ordinary (non-reparse) directories, staged executable names and the
   previously qualified candidate GIO SHA256
   `67b9f7246e4744fef7ee1ead3bed4ce2179c6f0465ec68a92d01dd12b4a3ccad`.
   This renderer NEVER launches the source, reads camera credentials or
   touches production recordings. It also copies the original public
   `CommonSettings.ps1` byte-for-byte at this first stage.
2. [New-C545DPrivateOutputSettingsMirrorCI.ps1](../tools/New-C545DPrivateOutputSettingsMirrorCI.ps1)
   is a separate, explicitly tested CI-only layer. Only in the **copied**
   `CommonSettings.ps1`, it injects a single assignment of the in-memory
   `$s.output_folder` property to a private owned output child immediately
   before the existing unique `return $s` in `Read-C545DSettings`.
   A strict reverse-source equality assertion checks the entire unchanged
   source. Re-running refuses the already changed settings copy.
   The *original* project settings script and encrypted password storage are
   never changed; tests use a synthetic 192.0.2.11 camera configuration and
   never ask for the user's actual IP/password.
3. [Windows CI #44873653092 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/44873653092)
   checks PowerShell5.1 source parsing, the one-statement production
   `Record.ps1` delta, unchanged cloned settings before step 2, the
   existing production recording contract **on BOTH original and mirror**,
   refusal on a changed source anchor, modified candidate DLL and an
   app-local bin junction, the settings-only isolated output change,
   mock configuration resolving to the private output, refusal on duplicate
   application, and no changes to either original source.
   Log markers `C545D_PRODUCTION_MIRROR_CI_PASS` and
   `C545D_PRIVATE_OUTPUT_ISOLATION_CI_PASS`.
4. Intermediate failed #44873394577 was caused by the new script's
   source-string expression comparison, repaired by literal source guards
   at [a1ed5a7](https://github.com/taku077/c545d-recorder/commit/a1ed5a716fdb34a311e5f30e88c20798fc24d8b1).
   #44873469431 emitted the expected pass evidence but failed its job
   due to a deliberately rejected last test leaving `LASTEXITCODE=3`.
   The explicit successful final exit was fixed in
   [e11c6bb](https://github.com/taku077/c545d-recorder/commit/e11c6bb52e1a5ca6d56cc9783cba617f7772df00).
   #44873534226 SUCCESS verifies the first layer; #44873653092 SUCCESS
   verifies both layers. Neither failure was a GIO binary/Windows10 defect.

## Boundaries / next checks

- These are **source- and settings-equivalence checks only**. The CI staged
  GStreamer EXE names were inert test placeholders, never launched. They
  are NOT evidence that the mirrored `Record.ps1` starts, loads a real
  GIO module, preserves live dual RTSP stream clocks or emits playable
  hourly MP4. Actual app-local candidate GIO/WAV loader validation had
  been proved separately by earlier Windows Server2022 CI.
- Before any host trial, integrate the renderer with a genuine, validated
  1.28.8 MSVC x64 GStreamer SDK in a disposable CI runner, confirm the
  **actual** loaded candidate module path and original recording settings,
  and test media/stop/EOS with synthetic inputs. Do not launch the current
  mirror on a user's machine or interpret it as production-equivalent
  until these independent runtime gates are passed.
- Never modify installed GStreamer `bin`, registry or the user's
  `Record.ps1`. Stage must stay privately owned with reparse-safe cleanup.
  A real Tapo trial requires a separately approved natural safe recording
  stop and a **single consolidated** observation including one actual
  3600-second segment boundary, audio/video sync, MP4/EOS and
  CPU/PrivateUsage/Key-handle data. No repeated 4-hour WPR/UMDH checks.
- Prior corrected Windows2022 64-cycle CI A/B remains:
  PrivateUsage effect 98.2414% smaller, Key effect +2 candidate vs
  +20,932 original. This does **not** prove zero residual leak or
  any Windows10 production behavior.

**User action now: NONE. Production rollout: HOLD.**
