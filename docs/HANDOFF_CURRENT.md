# HANDOFF_CURRENT — C545D recorder

<!-- CURRENT_HANDOFF_START: update this block, not only append to the archive -->

### 現在の最優先再開地点：2026-11-17 23:55 JST — 実機UMDH Compare成功・v4オフライン再解析待ち

- **ユーザーが `C545D_HEAP_SAFE_REPORT_PID9424.zip` を実際に提出**。ZIP CRC正常・安全要約テキスト1個を確認。実機 `-Mode Compare`（v3）は**成功**した。もう `-Mode Compare` をやり直す必要はない。
- **実測値**：PID9424、Private Memory `632.28 → 633.43 MB`（25.54分、+1.15MB、約+2.70MB/h）。Windows HeapのUMDH差分`parsed_backtraces=182`、`parsed_net_delta_bytes=-43425`（約−42.4KiB、解析されたWindows Heap差分の符号付き合計であってプロセスのPrivate総量ではない）。
- 安全レポートの上位**30件すべて `first_dll=unknown`**。原因モジュールやリークの所在は**未確定**。従来のレポート抽出器は `.dll!` を要求したが、UMDHは `ntdll!Function` のように拡張子なしシンボルを出力する場合があるため、unknownは元のRAWスタックに名前がない証明ではない。
- **改善PR #26** [GitHub](https://github.com/taku077/c545d-recorder/pull/26) は mainにマージ済み：`diagnostics/Reanalyze-HeapDiff.ps1` を追加。ローカル既存 `UMDH_RAW_DIFF_PID9424.txt` **のみ**読み取り、モジュール識別子を安全に再抽出する。録画本体・GFlags/UST・UMDHキャプチャは変更なし。
- Windows PowerShell 5.1構文・合成差分/PII除外のCIは成功：[Actions run 44108444584](https://github.com/taku077/c545d-recorder/actions/runs/44108444584)。**実際のRAW diffに解決済みシンボルが入っているかはまだ不明**。実機再解析結果を待つ。
- **v4キット**：GitHub Actionsの実体を取得し、二重ZIPを解消した `C545D_HeapTrace_Diagnostics_v4.zip` をこのチャットに添付済み。新しいチャットで古い sandbox パスは再利用せず、存在検証または再取得する。以前の404になった個別Actionsリンクを再案内しない。
- **次の唯一のユーザー操作**：v4キットを展開し、通常権限PowerShellで `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Reanalyze-HeapDiff.ps1" -TargetPid 9424` を実行。`%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424_V2.zip` **だけ**チャットへ提出。`V2`は安全レポートスキーマで、キット版はv4。実行するps1は既存の `HeapTrace.ps1` **ではない**。
- **禁止/不要**：二つのUMDH生ログの再Capture、再Compare、録画停止・再起動、新たなソフト導入、RAW差分やスタック/ユーザーパスの公開。UST管理のRestoreは前段説明の通り必要時のみ。現在UST状態は未確認。
- **次回チャット開始時**、この最新セクション→非公開hand-off（フォルダ絶対パス）→直近ユーザーのv4実行結果→GitHub HEAD/PR/CIを読む。下に残るv3/v2の指示は履歴として扱い、差分解析以前に戻らない。


### 最新の再開地点：2026-11-17 — HeapTrace v3 UMDH標準エラー問題を修正（次の実機Compare待ち）

- **新しい実機エラー**：ユーザーは修正v2を `-Mode Compare` 実行すると、`HeapTrace.ps1` **279行**で `umdh.exe : Warning: The -v switch is obsolete. Verbose is always on.` および `NativeCommandError` が発生したと報告。**文字化けパス復旧は少なくともUMDH起動まで進んだ**が、UMDHの差分比較はまだ成功していない。
- **新しい修正v3**：[PR #24](https://github.com/taku077/c545d-recorder/pull/24) はmainにマージ済み。UMDH比較から廃止済み `-v` を削除、Windows PowerShell 5.1の `2>&1` と `ErrorActionPreference=Stop` によるstderr警告の例外化を回避。標準出力/標準エラーを.NET ProcessStartInfoで別取得し、終了コード判定＋raw stdoutの保存を実装。
- **Windows CI PASS**：PowerShell 5.1構文、既存の日本語JSON復旧・曖昧拒否、安全parser、さらに**stderrに警告/終了0なら継続、終了19なら失敗**の合成テストPASS。GitHub Actions [HeapTrace test](https://github.com/taku077/c545d-recorder/actions/runs/44106226506) と [source validation](https://github.com/taku077/c545d-recorder/actions/runs/44106226459)。実機の差分完遂/Heap割当元/録画安定性は**未検証**。
- **実体を確認したv3 ZIP**：`C545D_HeapTrace_Diagnostics_v3.zip` を同じチャットに添付済み（GitHub Actions実体取得→二重ZIP解除、3ファイル・CRC・コード内容検証）。**新しいチャットで旧sandboxパスを流用しない**。ユーザー側へv3展開を案内したが、実際の展開は未確認。
- **次の1操作**：ユーザーがv3を展開後、**通常権限PowerShell**でv3の `HeapTrace.ps1 -Mode Compare` を1回だけ実行。例えば `%USERPROFILE%\Downloads\C545D_HeapTrace_Diagnostics_v3\HeapTrace.ps1`。**PID9424のT1/T2再Captureはしない、録画EXEは変更しない。** 成功なら `%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424.zip` だけを受け取り解析。失敗時はその新エラーに限定して修正する。
- **保存先の区別**：v3スクリプト展開先は例示で、ユーザー申告のv2展開先・旧キット・RC35 EXE・RAWデータ保存先とは別。既知の**正確なローカルパス**は非公開引継ぎ文書に記載、公開側にユーザー名は載せない。
- UMDHの比較stderrが出た場合ローカルに `UMDH_RAW_DIFF_PID9424.stderr.txt` が残り得る。RAW・stderr・MP4・個人設定ファイルは公開しない。**安全ZIPのみ提出**。USTがまだ有効でこのキットの管理下なら検証後に管理者PowerShellで `-Mode Restore`。
- これ以前のCURRENTブロック内「v2をダウンロードして比較する」という説明は**v3に置き換わった**。旧v2は今回の警告バグを含む。根本のネイティブメモリ増加はまだ未解決。


## 旧時点の作業要約（2026-11-17）— 直上のv3修正が優先

**再開地点はRC35 GStreamer録画のUMDHヒープ差分比較。VMMap・新規計測・GStreamerバージョン確認には戻らない。** 会話名「tapo録画2」「tapo録画3」「続きを再開」でこのプロジェクトを指す場合、まずこのブロックと非公開 companion の同名ファイルを読む。履歴セクションには旧日付の `IMMEDIATE NEXT STEP` が残るが、その指示は失効している。

### ユーザーから得た確定事実（再質問しない）
- Windows 10 Pro / Windows PowerShell 5.1、日本語を含むユーザープロファイル。GStreamer h264parse は 1.28.8.1（確認済み）。
- Microsoft Debugging Tools x64 (gflags.exe / umdh.exe) は導入済み。GFlags UST を有効化してから実測した。今現在のUST有効状態は未確認。
- **録画RC35 EXEの既存展開先**：`%USERPROFILE%\Downloads\C545D_EXE_SEI_Default_ON_Win10_x64\C545D_Recorder.exe`。ユーザーが申告した正確な絶対パスは**非公開** companion に記録。旧バージョンを勝手に消去/置換しない。
- **旧HeapTraceキットの既存展開先**：`%USERPROFILE%\Downloads\C545D_HeapTrace_Diagnostics_Kit\`、そこに `HeapTrace.ps1`。この旧フォルダー内スクリプトがv2に置換済みとは**未確認**。絶対パスは非公開 companion に記録。
- **スナップショットの保存先**：`%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\`（`snapshots.json` と生UMDHログ）。これはキットの展開先とは**別**の場所。
- 同一PID **9424** のRAWログが**2個とも実在**：`UMDH_RAW_PID9424_T1_20261117_223501.txt`（7525.9 KiB、2026-11-17 22:35:13 JST）、`UMDH_RAW_PID9424_T2_20261117_230044.txt`（7480.6 KiB、23:00:45 JST）。
- `snapshots.json`: `FirstRecorded=True`, `SecondRecorded=True` だが `FirstFileOK=False`, `SecondFileOK=False`。`-Mode Compare` は旧版で「Two captures of one process are required」と失敗。生ログが欠落していると推測しない。

### GitHub修正と実機未確認部分
- 修正PR **#22** `fix/heaptrace-utf8-json-recover-existing-pid9424` は **2026-11-17 mainへマージ済み**。`diagnostics/HeapTrace.ps1` はUTF-8でJSON読込、既存PID/T1/T2の唯一候補を復旧、曖昧なら拒否、`umdh -v` 差分、正常時のみ安全な結果ZIPを生成。
- Windows PowerShell 5.1構文テスト / 日本語フォルダーUTF-8読み書き / 旧パス復旧 / 曖昧候補拒否 / safe parser はCI **PASS**：`https://github.com/taku077/c545d-recorder/actions/runs/44102088473` およびPowerShellソース `https://github.com/taku077/c545d-recorder/actions/runs/44102088323`。**実機UMDH差分比較は未実施**。
- 修正版診断v2 ZIPは直前のチャットでGitHub Actions実体から取り寄せ、**チャット内のsandbox添付**として提供済み。ただし sandbox のパスは新しい会話で有効とは限らない。古い **GitHub Actions artifact個別リンクはユーザー環境で404**。有効なReleases配布が検証できない場合はGitHubコネクタから現物を再取得し、**実ファイルの存在を確認したうえで**新しいチャットに直接添付すること。リンクを推測しない。

### 次の1操作（ユーザー側）
1. **v2の `HeapTrace.ps1`** を含む診断ZIPを展開。旧展開先がv1のままかもしれないので、v2版を実行していることを確認する（録画EXEを更新する必要はない）。
2. 通常権限PowerShellでそのv2 `HeapTrace.ps1` のあるフォルダーを開き、`powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\HeapTrace.ps1" -Mode Compare` を**1回だけ**実行。スクリプトは既存 `%LOCALAPPDATA%` にあるPID9424の2ログを検索する。
3. 成功したら `C545D_HEAP_SAFE_REPORT_PID9424.zip` のみこのチャットに提出。`UMDH_RAW*.txt` や `UMDH_RAW_DIFF*.txt`、カメラ設定/資格情報は提出・公開させない。失敗時はエラーメッセージのみを確認し、再Captureを安易に要求しない。
4. 調査後、USTがまだONなら管理者PowerShellでv2の `-Mode Restore` を実行（以前この診断キットでEnableした場合）。録画を強制終了しない。

### 目的・不変条件と進行ルール
- 根本目標は継続録画時のPrivate/Heapメモリ増加の**割当元特定**。過去VMMapでは約18分でHeap committed +5.64 MiB、長時間Private増加は約6–8MB/h。ただし**リーク未断定**。
- Tapo C545Dの広角stream1＋望遠stream6を1画面で同期録画。2560×720/15fps、x264 medium/Q24、`avdec_h264`、AAC 48kHz、1時間MP4、正常EOS/再開、SEIフィルタ既存動作を不用意に変更しない。日次強制再起動や24–48h再測定を安易に提案しない。
- 次チャットでは**最初に**(1)この最新ブロック、(2)非公開hand-off（個人パス）、(3)最新のユーザー出力、(4)GitHub main/CI/PRを照合する。**確定/推定/未検証**を分け、すでに回答済みのフォルダーや設定を再質問しない。
- 状態が変わったら**このブロックと非公開側の先頭ブロックを同じターンで更新**し、日時・実際の保存場所・今止まっているエラー・次の操作・提供リンクの有効性を更新する。末尾の追記だけで済ませない。
- 公開repoにユーザー名を含む絶対パス・生ログ・IP/認証情報を記録しない。非公開側に記録したパスも公開PRへ転記しない。

**参照**: [PR #22](https://github.com/taku077/c545d-recorder/pull/22) / [Issue #21](https://github.com/taku077/c545d-recorder/issues/21) / [診断README](https://github.com/taku077/c545d-recorder/blob/main/diagnostics/README_HEAP_TRACE_JA.md) / private `taku077/c545d-recorder-internal:docs/HANDOFF_CURRENT.md`。
<!-- CURRENT_HANDOFF_END -->

---

## 以下は過去の調査記録（上記CURRENTに優先しない）


**Last updated:** 2026-11-16 (JST)  
**Purpose:** Canonical cross-chat handoff. When the user says **「続きから再開してください」** in the context of the C545D recorder, **read this document first**, inspect the current GitHub HEAD/CI/PRs and continue from the next action rather than restarting diagnosis.

## Confirmed user environment result — 2026-11-16 (supersedes previous version blocker)

- The read-only process-path-based `gst-inspect-1.0 h264parse` check **succeeded**.
- Reported `h264parse` plugin version: **1.28.8.1**.
- The GStreamer installation is a **per-user Windows MSVC x86_64 installation** under Local AppData (do not publish the personal Windows account name or absolute path).
- Because upstream fixed `gst_h264_parser_parse_nal()` in **1.28.2**, the inspected 1.28.8.1 plugin is expected to **already contain that fix** in a standard official build. The specific previously suspected parser leak therefore drops in priority as explanation of the observed residual growth; do NOT recommend updating the runtime on the basis of that fix alone.
- The command also emitted warnings: `External plugin loader failed` and `Failed to load plugin gstpython.dll` (unresolved DLL dependency). These warnings refer to the plugin-scanner helper and Python binding plugin, **not evidence that H.264 parsing or the active recording failed**. The requested `h264parse` version was returned successfully. The recorder does not directly require `gstpython.dll`; do not delete DLLs or reinstall while recording.
- This version verification **completes the previous immediate blocker**. Do **not** ask for this same version again unless the installed GStreamer changes.
- **Next engineering task:** investigate the still-unexplained positive private-memory slope, checking current 1.28.8.1 components and actual object lifetime, allocator/RTSP and muxer behavior, before proposing a targeted fix. Preserve `avdec_h264` CPU improvement and current A/V sync/recording settings. Do not add speculative diagnostic loops or daily auto-restarts.
- The currently running recording is unaffected by the PowerShell inspection. No GitHub code changes to the recorder were needed for the version check.
- References: https://gstreamer.freedesktop.org/releases/1.28/ ; https://gstreamer.freedesktop.org/documentation/installing/on-windows.html ; https://discourse.gstreamer.org/t/user-getting-error-priv-gst-plugin-load-file-for-registry-module-open-failed/4499

## Canonical repositories
- Public source and GitHub Actions: https://github.com/taku077/c545d-recorder
- Private sanitized development notes: `taku077/c545d-recorder-internal` (requires connected GitHub access).
- Public issue for long-run stability: https://github.com/taku077/c545d-recorder/issues/1 (OPEN).
- Merged PRs: [#2](https://github.com/taku077/c545d-recorder/pull/2) baseline regression checks; [#3](https://github.com/taku077/c545d-recorder/pull/3) GStreamer core version logging and existing CSV analyzer; [#4](https://github.com/taku077/c545d-recorder/pull/4) H.264 parser plugin version reporting and upstream leak eligibility note.
- Last verified public `main` when this was authored: `d3854fe98421a6f6b2d92c2819f3844792921374`. Check the live HEAD before editing; do **not** assume it remains unchanged.
- Last verified successful Windows CI: https://github.com/taku077/c545d-recorder/actions/runs/43852965696 (syntax, invariants, synthetic tests, ZIP packaging; NOT a real camera recording test).

## User's goal and non-negotiable constraints
- 24 hours/day, 365 days/year unattended security recording from Tapo C545D, combining two RTSP feeds into **one** video with efficient storage.
- Wide `stream1` on left, telephoto `stream6` on right. Preserve 2-stream time synchronization, audio continuity, one-hour MP4 segments, safe stop/restart and file naming.
- x264 **medium**, quantizer **24**, **2560×720**, **15fps**; AAC mono 48kHz / 192kbps target. Do not silently switch to fast, GPU decode or unrelated new technologies.
- Priority was NOT a low instantaneous CPU percentage, but **CPU usage increasing with elapsed recording time**. This improved substantially after preferring `avdec_h264` over `openh264dec`. Do not undo that baseline.
- Next open technical objective is **private-memory growth over time**, without reducing video/audio quality or causing recording gaps.
- No forced daily/periodic restart as an alleged fix; preserving evidence continuity matters.
- Eventually port to C# WinForms EXE with public Windows GitHub Actions; **not yet** and not until the existing pipeline is stable. No Visual Studio/.NET SDK required on the end-user recording PC.

## Known empirical results (sanitized aggregates only)
- New `avdec_h264`-preferred run: around **15h23m**, measured CPU around **19–21%** over hourly windows; private memory **593.7MB to 706.1MB**.
- Post-six-hour regression: approximately **+6.17MB/hour**, R² about **0.9965**. No plateau observed; no established root cause.
- Earlier `openh264dec`-preferred run had rising CPU toward ~40% and much faster memory growth.
- The working pipeline includes three `h264parse` elements; earlier ETL analysis reported allocation paths through `gstvideoparsersbad.dll`.
- GStreamer 1.28.2 release notes identify a fix for a memory leak in `gst_h264_parser_parse_nal()` (issue #4966 / MR !11060). **Candidate only**, not proof of causality; possible downstream backports.
- Current recorder's installed GStreamer core / h264parse plugin versions have **not yet been established**.

## IMMEDIATE NEXT STEP (current blocker, 2026-11-16)
The user tried a previous PowerShell path check and received **「GStreamerが見つかりません」**. The failed command only searched three assumed directories, so this **does not establish that GStreamer is absent**. The working recorder itself previously found GStreamer (`Record.ps1` also has a `Get-Command` fallback).

Ask for the output of this **read-only** PowerShell command, preferably **while recording**, which derives the actual `gst-inspect-1.0.exe` path from the running `gst-launch-1.0.exe` process:

```powershell
$p = Get-CimInstance Win32_Process -Filter "Name = 'gst-launch-1.0.exe'" | Select-Object -First 1
if ($p -and $p.ExecutablePath) {
    $gst = Join-Path (Split-Path $p.ExecutablePath -Parent) 'gst-inspect-1.0.exe'
    if (Test-Path -LiteralPath $gst) {
        & $gst h264parse | Select-String '^\s*Version\s+'
    } else { Write-Host "gst-inspect.exeが同じフォルダーにありません" }
} else { Write-Host "録画中のGStreamerプロセスが見つかりません" }
```

Interpretation:
- Plugin version **1.28.2 or newer** in the 1.28 branch: upstream parser fix expected to be present; look at other causes if memory still increases.
- Plugin **older**: relevant upstream fix might be missing; check backports and compare supported, verified official MSVC x64 GStreamer runtime **side by side** with rollback and **only after safe stopping**, never during a live recording.
- If process not present, don't claim it is uninstalled. Check whether recording is actually active; alternatively use `Get-Command gst-launch-1.0.exe` and existing log, without full HDD searches.
- If version output unavailable due to permissions, may use `Get-Process` `Path` or point-and-click Task Manager -> open file location.

## Working-code scope and guardrails
- User launcher: `C545D_Start.vbs`.
- GUI: `C545D_App.ps1` ; recorder: `Record.ps1`; worker: `RecordGUIWorker.ps1`; filename processing: `SegmentNamerWorker.ps1` / `SegmentNamer.ps1`; settings helper: `CommonSettings.ps1`.
- `Record.ps1` on current GitHub main logs `GStreamer runtime:` and `H264 parser plugin (videoparsersbad):` **at next startup only** (current already-running recorder will not automatically obtain new logging).
- Never claim CI proves actual 24x365 stability. Changes go in feature branches, are checked on `windows-2022` CI and PR, then merged if supported; `main` is a known-good candidate baseline.
- Public repo may be read by anyone; no camera credentials, local IP, usernames/passwords, `settings.json`, `camera_password.dpapi`, recorded media, ETL, or raw diagnostic logs in either repo. Sanitize any analysis.

## To resume reliably
1. Read **this** file and, if accessible, the private `docs/HANDOFF_CURRENT.md`.
2. Check current GitHub main SHA, Issue #1, open PRs and latest CI.
3. Continue from current blocker / user-supplied version result; don't re-ask already answered constraints or repeat costly diagnostic loops.
4. If the user only says **「続きから再開してください」** and multiple ongoing projects make the reference ambiguous, confirm this is the C545D recorder rather than silently choosing another project.


## Follow-up: plugin scanner file exists (2026-11-16 JST)
- User confirmed the PowerShell scanner existence probe returned **「補助プログラム：存在します」**.
- Therefore, `gst-plugin-scanner.exe` is present at the path derived from the actual running GStreamer executable. The earlier warning `External plugin loader failed` means it could not be launched/used in that invocation; **file absence is ruled out**, but missing DLL dependencies, environment PATH/scanner configuration, permissions, etc. remain possible.
- `gstpython.dll` failed to load with Windows' missing-module message. This can indicate a dependency of that DLL is absent; it does NOT prove the plugin file itself is missing. This optional Python plugin is not directly required by the C545D recorder pipeline.
- **Next safe test**: run `gst-inspect-1.0 h264parse` from the currently running GStreamer executable's directory in a separate PowerShell process/session with temporary, process-local `PATH` prepended with its `bin` folder and `GST_PLUGIN_SCANNER` set explicitly to the existing scanner path. Do not write system environment variables or interrupt live recording. Compare warnings; note registry caching can suppress re-scans, so absence of warning in one run is not definitive.
- If warning persists under correct environment, focus on missing dependency or scanner execution failure; do NOT reinstall or delete DLLs speculatively. Preserve `avdec_h264` stability and long-run memory work.
- Official docs: https://gstreamer.freedesktop.org/documentation/installing/on-windows.html ; https://gstreamer.freedesktop.org/documentation/gstreamer/running.html


## Repeated scanner warnings with process-local environment — 2026-11-16 JST
- User reran `gst-inspect-1.0 h264parse` with the **actual running** `gst-launch` binary directory prepended to `PATH` and `GST_PLUGIN_SCANNER` pointed explicitly at the existing scanner executable. **Both warnings persisted**: `External plugin loader failed` and `Failed to load plugin ... gstpython.dll` (Windows reported missing module). `h264parse Version 1.28.8.1` was returned again.
- A simple omitted `PATH` or `GST_PLUGIN_SCANNER` setting is therefore **not enough** to explain/fix the symptoms. Do not repeat that test or claim the complete install failed.
- Scanner existence was previously confirmed, but not that it executes successfully; DLL/CRT dependency, plugin scanner start failure, plugin path/registry issues remain hypotheses. `gstpython.dll` is optional for this recorder and may have a missing transitive dependency.
- Upstream `gstregistry.c` falls back to in-process scanning if external loader fails, explaining how required plugins can remain available. Matching discussion: https://discourse.gstreamer.org/t/user-getting-error-priv-gst-plugin-load-file-for-registry-module-open-failed/4499 . Official Windows setup: https://gstreamer.freedesktop.org/documentation/installing/on-windows.html
- **Recommendation:** Do not delete `gstpython.dll`, globally set `GST_REGISTRY_FORK=no` as if that fixed the root cause, delete the plugin registry cache, reinstall, or interrupt currently working evidence recording just to silence warnings. These messages have **not** been tied causally to the remaining +6.17MB/h private-memory growth.
- **Next action:** Keep working recorder unchanged. If a specific necessary recording element fails or the user prioritizes warning repair, diagnose the exact failing helper/DLL dependency using a bounded, evidence-driven test before recommending a repair; otherwise prioritize identifying long-run memory growth separately.


## EXE migration stage 1 built — 2026-11-16 (user requested pivot while memory runs)
- On 2026-11-16 user suggested checking private-memory trend **tomorrow (2026-11-17)** after a longer recording, and doing EXE work meanwhile. Respect this ordering. Do not infer residual leak fixed from the EXE build.
- Public [PR #5](https://github.com/taku077/c545d-recorder/pull/5) was **merged** (main commit `fac5263676e5f687214a8365c13475692ca985a9`). C# `.NET Framework 4.8` x64 `WinExe` was created at `src/C545D.Launcher/`. In this **stage-1 launcher**, `C545D_Recorder.exe` launches the **existing PowerShell WinForms GUI** (script `C545D_App.ps1`) in hidden STA PowerShell and sets `C545D_VIDEO_DECODER=avdec`; it exits while the original app manages the session.
- The nine existing .ps1/.vbs/README baseline files were not edited in this PR. Stop markers, CTRL+C→EOS, RTSP pipeline, AAC, 2560×720/15fps, x264 medium/Q24 and filename handling stay unchanged.
- New workflow `.github/workflows/build-exe.yml` uses `windows-2022` and `microsoft/setup-msbuild@v3` to build, package and smoke-test in a Unicode directory **without connecting to a camera**. PR CI passed: https://github.com/taku077/c545d-recorder/actions/runs/43863192829 . Main workflow: https://github.com/taku077/c545d-recorder/actions/runs/43863396922 ; job passed.
- Main workflow generated artifact named `c545d-exe-win10-x64` containing `C545D_Recorder_EXE_Win10_x64.zip`, with `C545D_Recorder.exe` and nine original source files. Current artifact expires 2026-11-23 UTC; download from the workflow run's **Artifacts** section while signed into GitHub. It may require unzipping the artifact wrapper then the app ZIP.
- Critical truth: this is **an EXE launcher**, not a complete C# WinForms controller or standalone single-file recorder; it still requires the bundled PowerShell scripts and separately installed GStreamer. No real Windows 10 camera recording validation yet. Do not instruct running it in parallel with currently active recorder.
- User's Windows 10 22H2 has `.NET Framework 4.8` as part of the OS, so no extra .NET runtime or Visual Studio should be needed. Source: https://learn.microsoft.com/en-us/dotnet/framework/install/on-windows-10 .
- Follow-on work is tracked in [Issue #6](https://github.com/taku077/c545d-recorder/issues/6): native C# WinForms **UI/control** port while retaining the working PowerShell/GStreamer back-end until confirmed stable. Preserve optional rename worker and safe stop/EOS semantics; test state transitions before on-device deployment.
- Tomorrow's memory review: use the **existing** local `Memory_Trend.csv` (or sanitized aggregate) over the extended session. Compare post-warmup private-memory slope with prior ~+6.17 MB/hour and check plateau without disrupting recording. Do not demand repeated costly diagnostics if existing data suffices.


## Memory mitigation candidate PR #7 — 2026-11-17 JST
- User explicitly requested an actual code change, without installing further diagnostic tools or repeating 24–48h waiting loops.
- Two VMMap snapshots from the same gst-launch PID (4820), about 18m04s apart, showed Heap committed roughly +5.64 MiB, with existing Heap about +3.39 MiB and one new Heap region about +2.23 MiB. This **does not identify** the allocating plugin, prove a leak or establish that any one branch caused the increase.
- PR #7 changes only the **discarded** telephoto/stream6 RTP audio branch in Record.ps1: queue max-size-buffers=8/max-size-bytes=262144/max-size-time=250000000/leaky=downstream; fakesink enable-last-sample=false. Default GStreamer queue was already bounded (200 buffers/10 MB/1 s); do not claim the old queue was unbounded.
- Recorded stream1 AAC, both videos, avdec_h264, x264 medium/Q24, 2560x720/15fps, NTP/tcp sync, splitmuxsink hourly segments, stop/EOS are not changed.
- This is a concrete retention-reduction patch, **NOT a verified fix for the residual Heap slope**. No real camera test or 24×365 validation was performed by public CI.
- If build/CI passed and main was merged, use new main artifact only at a safe stop, preserving rollback to 2026-11-16 known-good baseline. Do not run the old and new recorders simultaneously.
- No further user-installed tool is required for this candidate. Actual slope/quality changes require comparing existing Memory_Trend.csv over the same PID and checking MP4/AAC/dual-lens sync on the user PC.


## Stage 2 native WinForms EXE — 2026-11-17 JST (PR #8)
- User reported **stage-1 launcher EXE successfully starts recording on their PC**. This is a user-observed start/record result, NOT a passed stop/EOS/restart/long-run test.
- The Stage-2 candidate replaces the stage-1 PowerShell GUI launcher with a **native C# WinForms controller** in src/C545D.Launcher/RecorderForm.cs. It retains the UNCHANGED Record.ps1/RecordGUIWorker.ps1 media path and original C545D_App.ps1/C545D_Start.vbs as rollback.
- Native controller includes camera settings, same-user DPAPI secret via stdin-only PowerShell C545D_SettingsBridge.ps1, session-specific stop/ready markers, console Ctrl+C and GStreamer -e EOS, optional event-driven rename worker, restart after stop, tray actions, memory CSV and explicit emergency stop.
- No modification to x264 medium, Quantizer 24, 2560×720/15fps, avdec_h264 preference, AAC, dual RTSP NTP/tcp timestamp or hourly MP4 splitting.
- Public Windows GitHub Actions verifies compilation, synthetic native GUI startup and synthetic DPAPI round-trip. It CANNOT prove real-camera EOS stop, MP4 playback, RTSP sync or 24×365 stability. The user must preserve old stage-1 app until a normal real-PC stop→restart check is completed at a safe stop opportunity.
- Artifact accessibility: user reported **Actions > Artifacts did not expose a clickable download**, despite existing artifacts. GitHub docs require a signed-in account with read access for Actions artifacts and note expiry. Stage-2 workflow publishes a numbered **prerelease asset** to https://github.com/taku077/c545d-recorder/releases after successful push to main; direct ZIP links from Releases are the preferred download path. Also attach ZIP directly in ChatGPT when possible.
- This migration is NOT evidence that the unexplained private Heap increase (+5.64 MiB in ~18min VMMap comparison, historical post-warmup +6.17 MiB/h) has been fixed. Do not add user-installed diagnostics or 24–48h waiting loops as a default.
- Confirm GitHub main HEAD / PR #8 merge / release asset URL / live CI before continuing. The last known working stage-1 build is separate; never run both versions simultaneously.


## 2026-11-17 — RC11 interrupted-recording recovery
- Existing user logs: Native GUI worker PIDs 660, 11292, 11120 ended with `GStreamer returned; exitCode=0; stopMarker=False`, while gst-launch reported `handling interrupt`. Cause of unsolicited console events is **not proven**; native Stage 2 displayed a console and RC10 addressed it.
- Previously Record.ps1 treated any C545DWorkerStopSignal.StopRequested as an authorized stop and also treated gst exit-code 0 as terminal for a managed session. This can silently end an evidence capture without the GUI stop marker.
- RC11 only recognizes the per-session durable GUI `.stop` marker as authorized. Unexpected `CTRL_C_EVENT` or any unexpected GStreamer exit now follows existing bounded backoff/reconnect, even when gst exits code 0. Preserve standalone PS1 Ctrl+C behavior when no control session exists.
- Worker counts console control events via atomic counter (no I/O in control handler); logs `consoleCtrlCEvents`, `UNEXPECTED_CTRL_C`, `UNEXPECTED_GSTREAMER_EXIT` and explicit exit-policy. Native WinForms shows a red status and logs `UNEXPECTED_WORKER_EXIT` if the worker itself dies without a stop request.
- Unit tests for pure exit policy are executed in Windows CI without connecting cameras; original source invariant tests, native UI, DPAPI and EXE smoke tests remain. No recorder format/quality/synchronization change. Unknown real-camera success; do not claim a fixed memory leak or resolved libav/qtmux issue.
- Never run two recorders simultaneously. Keep RC10 as rollback and switch only after normal stop/EOS finalization.


## 2026-11-17 — RC13 H264 decoder / muxer timestamp errors
- User clarified that CTRL+C on visible Stage 2 console was **manually pressed by the user** because of error output; it is NOT evidence of unsolicited interruptions. Do not present worker PIDs 660/11292/11120 as spontaneous CTRL+C. Previous attribution in RC12 plan was incorrect. RC12 reconnect code remains in main for now, but the requested RC13 work **specifically targets repeated libav 'no frame!' and qtmux 'decreasing DTS'**, not UI/stop controls.
- FFmpeg H264 decoder's 'no frame!' is produced when no decodable slice/frame is present in packet; the RTSP logs show repeated examples near camera GOP cadence for both inputs (see GStreamer official docs and libavcodec h264dec.c source).
- Before RC13 parser used config-interval=-1 (reinsert SPS/PPS at each IDR). RC13 conditionally switches to config-interval=0 + byte-stream,alignment=au after rtph264depay; tests with synthetic RTP stream before camera startup, logs strategy; C545D_H264_INPUT=legacy rollback.
- qtmux decreasing DTS may be video or AAC; RC10's optional h264timestamper protects encoded video DTS but does not ensure AAC timestamp monotonicity. RC13 conditionally inserts audiorate skip-to-first=true tolerance=40000000 in stream1 decoded audio before AAC, with an AAC/MP4 synthetic preflight; C545D_AUDIO_TS=legacy rollback. This may insert/drop samples at discontinuities.
- No changes to video x264 medium/Q24, 2560×720 15fps, two NTP-linked sources, AAC target, 1h MP4 split, or stop/EOS. No filtering or suppression of GStreamer error messages.
- Synthetic pipeline success demonstrates negotiation only. It is **not proof** that camera-specific libav errors, MP4 DTS, or increasing Heap usage are fixed. Do not claim production validation.
- No extra user software installations or destructive MP4 testing. Existing worker transcript will show H264 RTP input guard, AAC timestamp guard and MP4 DTS guard states.


## 2026-11-17 — RC16 opt-in media diagnostic launcher
- User consented to a comprehensive evidence-first investigation, with tool/log requirements declared upfront, focused on `libav: no frame!`, `qtmux decreasing DTS`, and subsequent Heap retention.
- PR adding `START_DIAGNOSTIC.cmd`: no recorder pipeline edits, no new tools, and no debug logging in normal EXE start. Run only after normally stopping any active recorder.
- Launcher sets `GST_DEBUG=*:2,rtph264depay:5,h264parse:5,rtpjitterbuffer:4,qtmux:5,audiorate:4,splitmuxsink:4`, `GST_DEBUG_FILE=%LOCALAPPDATA%\C545D_GStreamer\Logs\GST_DIAG_%p_%r.log`, `GST_DEBUG_NO_COLOR=1` **only for subprocesses started from launcher**. Each child process gets unique file by PID/random. On short (~5–10min) diagnostic recording, provide Recording_*.txt, relevant largest gst-launch GST_DIAG_*.log (after checking for any RTSP credentials), optional Stop_Control.log only for genuine stop problem, Memory_Trend.csv if memory is focus.
- GStreamer official documentation confirms debug categories and GST_DEBUG_FILE %p and %r substitution. Do not assume warning-count=damaged frame-count; first attribute to stream and actual decoder damage.
- No extra tools now. If Heap cause demanded later, Microsoft Debugging Tools package GFlags+UMDH should be disclosed as one staged dependency (needs per-image UST prior to process launch). Wireshark already present optional for evidence of network packet anomaly.
- Stage RC16 is *diagnostic capture only*, not a cure for existing decode/DTS or Heap warnings.


## 2026-11-17 — Privacy-preserving diagnostic export
- User wants to upload logs directly to ChatGPT but correctly notes manual credential searching through enormous `GST_DIAG_*.log` is too much work.
- Added `EXPORT_SAFE_LOGS.cmd` + `Export-SafeDiagnostics.ps1`: schema-only allowlist export, no raw log lines, URLs, passwords, user names, local paths, raw debug text, or MP4 bytes in the ZIP. Scans latest 8 matching log files, up to 400k lines each, caps exported events at 18k; emits `summary.txt` and `media_events.tsv` to `C545D_SAFE_DIAGNOSTICS_<time>.zip` in Downloads. No admin/additional software. Source log and recordings are read-only.
- Synthetic Windows CI test includes literal credential, RTSP URI, IP and base64 token and verifies ZIP excludes them while retaining `LIBAV_NO_FRAME` and `QTMUX_DTS_BACKWARD`.
- Scope: lossy diagnostic extract; it may not suffice to distinguish audio/video pad or precise H264 AU issue. If insufficient, enhance safe allowlist (not ask user to browse raw logs manually). Never claim generic redaction guarantees all arbitrary log text.
- User should upload safe ZIP to existing ChatGPT conversation only; no raw log into public GitHub issues. Personal ChatGPT data controls may affect training and retention; avoid categorical security guarantees.


## 2026-11-17 — Safe ZIP first actual user capture, exporter V2
- User uploaded `C545D_SAFE_DIAGNOSTICS_20261117_182408.zip` (schema only: media_events.tsv + summary.txt). We inspected exact bytes in current turn. Original V1 exporter selected 8 logs, `LOG_02` read 400000 lines then stopped. It exported the first 18000 events, of which 15446 were routine DEBUG_SAMPLE, 2553 LIBAV_NO_FRAME (about 0.5s through 115.15s), one DISCONTINUITY. Summary counted 4242 LIBAV_NO_FRAME (including events not exported). No QTMUX_DTS_BACKWARD in exported subset, which does **NOT** exclude later qtmux DTS events. The exported error cadence was ~22/s, not once per 2s. Counts represent decoder error messages NOT confirmed missing frames.
- V2 exporter addresses V1 selection/cap issue by scanning newest diagnostics (2 largest among 12 latest GST_DIAG; 2 latest Recording logs), aggregating **all scanned** event counts per second, exporting only a few representative messages per second, and preserving QTMUX/dynamic error events. Output: summary.txt, media_events.tsv, event_rates.tsv. Scan is bounded to 5m lines/file and 10m lines total; must disclose TRUNCATED if any limit hit.
- CI synthetic test injects 20000 ordinary H264 debug lines *before* additional `no frame!`/qtmux DTS events and checks both are counted after previous V1 cap, plus fake password/IP/Authorization/RTSP URL do not appear. No raw messages copied, no new installs.
- User should **not** run another recording if original raw `GST_DIAG_*.log` files remain: install V2 exporter ZIP, double-click EXPORT_SAFE_LOGS.cmd, share newly generated SAFE_DIAGNOSTICS ZIP privately in conversation. Note that detailed logs are highly sensitive and safe schema-only report is intentionally lossy.
- Root cause H.264 vs qtmux vs native Heap remains unproven. Do not move to speculative pipeline repairs from V1 counts alone.


## 2026-11-17 — H264 SEI-only AU native filter candidate (PR #16)
- Existing private GST_DIAG original session about 747.8 seconds: 16,643 libav no-frame errors, ~16,644 SEI NALs parsed, 16,642 within 10ms on same decode thread; many standalone SEI-only AUs carried with an inserted AUD (NAL 9) and no VCL picture, explaining `avdec_h264` warning. A raw `no frame!` event is NOT proof of a lost output video frame.
- Implemented minimal C `c545dseifilter` GstBaseTransform (native/sei_filter/) supporting only `video/x-h264,stream-format=byte-stream,alignment=au`; conservative AU classifier drops **only** NAL type 6 SEI with optional 9 AUD or 12 filler and no slice/header/unknown NAL; VCL (1–5), SPS/PPS (7/8), malformed, AVCC and unknown bypass unchanged. No buffer data rewriting; metadata-only standalone SEI is deliberately not passed to the decoder, with stated metadata caveat.
- The new Windows CI downloads official GStreamer 1.28.8 MSVC development SDK onto GitHub runner ONLY, compiles x64 plugin and classifier, tests synthetic picture decode and custom appsrc/appsink AU pass/drop. No new installation needed on user's machine. CI builds DLL `gstc545dsei.dll` and packages it under app-local `plugins/`, without changing system GStreamer. Do not merge without green CI.
- `Record.ps1` recognizes `C545D_SEI_AU_FILTER=on` ONLY. Default normal EXE/normal diagnostics is OFF; opt-in trial launcher `START_SEI_FILTER_DIAGNOSTIC.cmd` sets environment for child. If DLL absent or synthetic preflight fails, log UNAVAILABLE and use legacy pipeline.
- Opt-in pipeline inserts filter after incoming h264parse (forced byte-stream AU caps) and before avdec_h264 on both lens branches. No change to NTP/tcp, AAC, compositor, x264 medium/Q24, hourly MP4, stop/EOS. This is a candidate to be validated on real C545D for warnings, picture output, metadata implications, CPU and memory.
- Before/after logs should cover matched ~5-minute sessions. Using `EXPORT_SAFE_LOGS.cmd`, user can share schema-only diagnostics. Do not paste private raw GST_DIAG to GitHub.
- Separate qtmux DTS warning not present in analyzed 747.8s session; not changed here. Heap leak remains unresolved. Earlier worker Ctrl+C was manually pressed by user after visible console errors, not an accidental interrupt.


## 2026-11-17 — RC26 field launch failure and real GStreamer release gate
- User reports second SEI opt-in trial **no recording / near-zero CPU**. Private schema-only safe ZIP `C545D_SAFE_DIAGNOSTICS_20261117_201724.zip`: `LOG_03_WORKER` had 3 `GST_LAUNCH`, 3 `GST_PIPELINE_ERROR`, 3 `GST_EXIT exit_code=1`; `LOG_04_WORKER` had 4 of each; total 7 failed launches, **zero success**. GST detailed logs were short: 2690 +701 scanned lines, no libav or DTS errors. A zero error count here does NOT establish decoder improvement.
- Existing CI checked native WinForms startup, synthetic plugin classification, and a naive separator token check; it never used GStreamer's actual parser on the entire production PowerShell-assembled graph. Thus prior claim that RC26 was sufficiently tested for recording was false.
- New PR #18 adds `tests/Export-RecorderGraphForCI.ps1` which extracts the **actual** `Record.ps1` pipeline generator with dummy IP/credentials/path; invokes GStreamer 1.28.8 MSVC native `gst_parse_launchv()` with NO state transition, camera connection, or MP4 writing. Matrix: SEI ON/OFF, input H264 guard ON/OFF, audio guard ON/OFF, output DTS guard ON/OFF = 16 cases. Any parse error fails the build BEFORE EXE packaging/Release.
- **Initial native test actually FAILED** variant 13 with `no element "video"` for SEI=ON, H264 guard=ON. First twelve combos passed. Root cause: when H264 input guard enabled, `Record.ps1` already emits `! video/x-h264,stream-format=byte-stream,alignment=au !`; trial SEI block emitted a second `video/x-h264` capsfilter immediately after, which GStreamer 1.28 grammar rejects. Removing only duplicate ! in PR #17 did not address it.
- Candidate fix in PR #18: re-use first capsfilter when H264 guard active, only add caps in legacy H264 path. **Do not merge/ship unless 16/16 native pipeline parse pass and other Windows tests remain green.** This gate still cannot prove real-camera streaming, EOS, audio/video quality or memory behavior. Field testing remains needed only after CI gate passes. No real passwords/paths used in GitHub CI.


## 2026-11-17 — Native EXE default SEI ON after user-verified RC32 playback
- User reported RC32 opt-in trial recorded for ~5 minutes; finalized MP4 played both wide-angle and telephoto picture with audible AAC and end-to-end playback. Safe GST report scanned ~297s and found 0 no-frame warnings vs prior 22.3/s, 0 DTS backward. This justifies making this filter the **default native EXE UI request**, not a claim of 24x365 stability or metadata preservation.
- User explicitly objects to having to launch an EXE through additional CMD wrappers. Modified `src/C545D.Launcher/RecorderForm.cs`: a visible **SEI対策を有効化（推奨）** checkbox defaults ON for direct `C545D_Recorder.exe` launch, and is disabled while recording. Immediately before starting `RecordGUIWorker.ps1` it sets `C545D_SEI_AU_FILTER` to `on` or `off` **for the EXE process only**; hidden-console child inherits it. No global environment change; no new software installation; no extra high-volume GST_DEBUG for normal EXE.
- `Record.ps1` retains DLL availability, GStreamer element detection and synthetic decode preflight, falling back to legacy path if the filter is missing or incompatible; worker log explicitly records `SEI-only AU filter: ON/UNAVAILABLE/OFF`. The UI check means ON requested, not proof of plugin actually loaded.
- The user can uncheck the box after normal stop to revert to legacy decode input, without external CMD or environment editing. Known good RC32 stays rollback.
- Windows EXE CI smoke now exercises actual native WinForms default ON and an explicit OFF startup, checks bundled plugin DLL, source transition order, and the mandatory 16/16 full gst_parse_launchv production graph gate. Real camera 24x365 and private-Heap slope are not asserted.


## 2026-11-17 — RC35 memory/CPU evidence and separate opt-in HeapTrace diagnostic kit (PR #20)
- 21:09–21:18 RC35 directly launched from native EXE with real recorder worker report `SEI-only AU filter: ON`, wide/tele RTSP PLAYING, GStreamer normal EOS exit 0 and GUI stopMarker=True. Current private heap remained mildly increasing: first 8 minutes PID 10432 592.8→597.5 MiB; after initial warmup 596.7→597.5 MiB in ~6 min. Earlier ~11h session 593.9→678.0 MiB (~7 MiB/hr). No proof of peak-out or actual native leak.
- Safe exporter selects old diagnostic GST logs by size and may produce misleading "zero errors" for current no-GST_DEBUG RC35 session; worker logs still useful to check startup/stop and SEI flag. Do not claim all old no-frame warnings are absent without matching detailed log.
- To attribute Windows Heap allocation growth **without changing RC35 media pipeline** added `diagnostics/HeapTrace.ps1`, one-click read-only check, Japanese procedure, new Windows CI with synthetic UMDH diff/privacy test, then a **separate diagnostic-only GitHub Releases ZIP**. Requires Microsoft Debugging Tools x64 (gflags and umdh) installed on PC.
- The scripted UST enable/disable is per-image `gst-launch-1.0.exe`, admin-only, tracks its own registry-change marker to avoid disabling another user's setting. Must take effect BEFORE launching new gst-launch. Normal RC35 GUI is launched in ordinary user context with process-only OANOCACHE=1. Capture 2 UMDH snapshots against same PID and start timestamp ~10–20 min apart, compare only, safe summary ZIP contains numeric deltas and DLL basename only; never upload raw UMDH stack traces or paths publicly.
- This is a *diagnostic candidate*, not a leak fix or full field-validated instrument. Windows CI covers PS syntax, test diff fake credentials and read-only Check. Real GFlags + UMDH side effects and actual capture have not been exercised on user's PC. UST overhead may change timing/CPU/Private memory, so the RC35 without tracing remains baseline. Restore UST once diagnosis is complete.
- If UMDH does not explain all of growing Private MB, check GLib/FFmpeg custom allocator coverage or GStreamer object tracer carefully before prescribing additional instruments; do not pile on tools without a distinct evidence question. No 24–48h wait loop as a prerequisite.


## 2026-11-17 — HeapTrace v2 recovery, Japanese profile path issue (PR #22)
- User captured two UMDH raw logs from the same PID 9424: T1 22:35 (about 7525.9 KiB) and T2 23:00 (7480.6 KiB). Both files physically exist under %LOCALAPPDATA%/C545D_GStreamer/HeapTrace; snapshots.json first/second both populated but File.Exists returned False for both. No raw files shared.
- Root cause: Save-Json used UTF8Encoding(false) (no BOM), while Windows PowerShell 5.1 Get-Content -Raw defaults to ANSI on BOM-less data; Japanese username path is corrupted, and reserialized on the second capture. This breaks Compare's old guard before UMDH diff can run.
- v2 Read-Json uses [IO.File]::ReadAllText with explicit UTF8. Compare reconstructs raw capture file paths from exactly one T1 and one T2 file matching the stored PID and timestamped filename within private HeapTrace directory, requires non-empty files and chronological order, refuses ambiguity, and saves repaired state only after successful UMDH diff + safe summary. Adds '-v' to UMDH comparison for stack traces. Raw memory trace remains private.
- Windows CI tests PowerShell 5.1 syntax, Japanese Unicode directory UTF8 JSON roundtrip, intentionally corrupted path recovery, ambiguous candidate refusal, synthetic summary privacy, read-only Check and zipped diagnostic release. No MP4/GStreamer recording changes.
- The user must download HeapTrace diagnostic v2 separately (not RC35), reuse existing raw captures, run ONLY '-Mode Compare' under ordinary PowerShell. No recapture/restart. Afterward '-Mode Restore' under Administrator if UST is still on. If Compare fails at UMDH parsing, review error output, not upload raw diff.
- Issue #21 and root investigation #12; no claim of memory-leak cause yet.
