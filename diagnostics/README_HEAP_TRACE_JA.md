## v5：unknownの意味を分離するための既存UMDH差分の安全再解析（2026-11-18）

ユーザーから提出されたv4の安全レポート（`C545D_HEAP_SAFE_REPORT_PID9424_V2.zip`）を確認した。比較されたBackTrace 182件、正の差分+693,428B、負の差分−736,853B、純差−43,425B。増加上位は+380,928B、+178,176B、+94,208Bで、3件だけで正の差分約94.2%。v4の3件ともモジュール`unknown`。非システムモジュールを認識したトレースは81件だが、上位3件の原因は不明。

**重要**：v4の`unknown`は「スタック自体がない」「シンボルが全て解決不能」を意味しない。v4は`ntdll`/`kernelbase`等Windows標準モジュールだけのスタックも`unknown`と出力し、代替情報は表示していなかった。

v5の`Reanalyze-HeapDiff.ps1`は、すでにPCに残る`UMDH_RAW_DIFF_PID9424.txt`だけを読み、各正の差分を次の**非機密カテゴリー**に分ける：`recognized-non-system`、`windows-runtime-only`、`other-module-symbol`、`address-like-no-symbol`、`no-recognized-frames`。上位30件にカテゴリーと該当パターン行数だけ表示。住所・シンボル関数名・生スタックは出力しない。未知モジュール名は`other-module`に抽象化。これは形状判定で、原因DLLや漏れを断定しない。

v5のキットを展開して、通常権限PowerShellから1回だけ実行する（v4/v3のファイルは上書きしない）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Reanalyze-HeapDiff.ps1" -TargetPid 9424
```

出力：`%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424_V3.zip` のみ共有。末尾の`V3`は安全レポートのスキーマであり、キットはv5。既存RAWスナップショットやRAW差分をアップロードしない。新規Capture、録画停止、UMDH比較、UST有効化、ソフト追加は不要。

Microsoft公式：https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison

## v4：既存UMDH差分から割り当て元を追加抽出（2026-11-17）

ユーザー提出の `C545D_HEAP_SAFE_REPORT_PID9424.zip` は、PID9424の実機Compareに成功し、25.54分のPrivate Memory 632.28→633.43MB、`parsed_backtraces=182`、UMDH差分 `parsed_net_delta_bytes=-43425` を報告。ただし上位30件が **すべて `first_dll=unknown`** で、原因DLLは未特定。

旧版の抽出ロジックは **`.dll!` が付く表記だけ**を探していた。しかしMicrosoft UMDH解説では `ntdll!RtlAllocateHeap` や `MyApp!Function` と表示され、`.dll` とは限らない。今回の `unknown` は抽出仕様による可能性がある。実機RAW差分は未提出のため、実際にシンボルが含まれるか未確認。

v4キットに `Reanalyze-HeapDiff.ps1` を追加。保存済みRAW差分だけをローカルで解析する独立スクリプトで、UMDH再起動・再Capture・録画停止・管理者権限・追加ソフトは不要。

通常権限PowerShellでv4を展開したフォルダーから1回実行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Reanalyze-HeapDiff.ps1" -TargetPid 9424
```

結果：`%LOCALAPPDATA%\C545D_GStreamer\HeapTrace\C545D_HEAP_SAFE_REPORT_PID9424_V2.zip`。**新しいZIPのみ**チャットに提出（V2はレポートスキーマ、診断キットはv4）。`UMDH_RAW*` / `.stderr.txt` / 生スタック・ローカルパスは共有しない。

安全出力は既知のGStreamer/GLib/FFmpeg等のモジュール識別子に制限し、未知の名前は`other-module`/`unknown`と記載。モジュール識別だけでリーク原因の証明にはならない。シンボル未解決なら`unknown`が残る。`parsed_net_delta_bytes`は検出BackTraceの符号付き合計でPrivate Memoryそのものではない。

公式：https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/interpreting-a-log-comparison

## v3: Compare時に「Warning: The -v switch is obsolete」で止まる場合（2026-11-17）

旧v2では、実在するT1/T2の発見・復旧後、UMDHの実行まで進んでも、
現在のUMDHがstderrに `Warning: The -v switch is obsolete. Verbose is always on.` と出すと、
Windows PowerShell 5.1の `$ErrorActionPreference='Stop'` と `2>&1` の組合せで
`NativeCommandError` となり、その時点で処理が中断する場合があります。

v3ではUMDH比較呼出しから不要な `-v` を外し、.NET ProcessStartInfoで
標準出力と標準エラーを別々に取り込み、**実際の終了コード**を確認します。
warningが出た場合もstderrはHeapTraceのローカルにだけ保存し、rawログ・録画に触れません。
Windows CIは警告stderrがあってexit 0なら成功し、exit 19なら失敗する合成テストを追加。

**すでに保存されているPID9424のRAWログ2本は再測定不要**。
更新したv3の `HeapTrace.ps1` だけを使用し、通常権限PowerShellで
`-Mode Compare` をもう一度実行してください。v2と録画RC35のEXEを混同しないでください。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\HeapTrace.ps1" -Mode Compare
```

成功時に提出するのは従来通り `C545D_HEAP_SAFE_REPORT_PID9424.zip` **のみ**。
`UMDH_RAW*.txt`、`UMDH_RAW_DIFF*.txt`、`UMDH_RAW_DIFF*.stderr.txt`
は個人情報やアドレスを含み得るため提出しないでください。

実機UMDHの差分出力形式が未知の場合は安全レポートが生成できず
`UMDH diff format unknown` になる可能性があります。その場合も再Captureは不要です。
誤って「メモリ増加なし」と判定しないでください。

## v2: 日本語ユーザーフォルダーにおけるCompareエラーを修復

Windows PowerShell 5.1では、BOMのないUTF-8 JSONを既定のANSIで読み込むため、
日本語ユーザーフォルダーに保存されたT1/T2のフルパスが文字化けする場合があります。
このため、旧v1で「Saved RAW snapshot 1/2」と表示された後でも、
Compareで「Two captures of one process are required」となる不具合がありました。

**2つのUMDH_RAW_PID..._T1/T2ファイルが残っている場合は、測定し直さないでください。**
v2はJSONを明示的にUTF-8で読み込み、記録済みPIDとT1/T2番号に一致する
保存済みUMDHログを直接発見します。候補が複数あれば勝手に選ばずエラーにします。

既存測定データの復旧操作（例：PID9424の2ファイルが保存済みの場合）：
1. 展開したv2のHeapTrace.ps1を使用する。旧v1は残しても構いません。
2. 通常権限PowerShellで v2のHeapTrace.ps1 に対して「-Mode Compare」を再実行。
   Capture／Launch／Enableは実行しないでください。
3. 成功時のみ、C545D_HEAP_SAFE_REPORT_PID*.zip をこのチャットに提出。
   UMDH_RAW*.txt／UMDH_RAW_DIFF*.txtを共有・公開しないでください。
4. USTがまだ有効なら、管理者PowerShellで「-Mode Restore」を実行します。

詳細な操作：
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\HeapTrace.ps1" -Mode Compare

注意：v2のWindowsテストは合成JSONとダミーUMDHファイルを使ったものです。
実際のUMDH差分計算の成功・メモリリークの原因までは、実機ログを確認する必要があります。

# C545D RC35：Heap割り当て元調査キット

既存の録画エンジン、MP4、通常ログは変更しません。最初の Check-HeapTools.cmd は読み取り専用で、録画中でも実行できます。

## 必要なツール
Microsoft公式 Debugging Tools for Windows (x64) の gflags.exe と umdh.exe。
公式配布：https://learn.microsoft.com/ja-jp/windows-hardware/drivers/debugger/debugger-download-tools
Windows SDKインストーラーからDebugging Tools for Windowsのみを選択可能です。

## 手順
1. RC35のC545D_Recorder.exeと同じフォルダーに HeapTrace.ps1 と Check-HeapTools.cmd を配置。現在録画中なら止めずに Check-HeapTools.cmd で事前確認。
2. 診断開始時、現在の録画を通常停止してMP4確定後、管理者PowerShellで下記を実行。gst-launch-1.0.exeのUSTのみ設定します。

   powershell -NoProfile -ExecutionPolicy Bypass -File .\HeapTrace.ps1 -Mode Enable

3. 管理者ウィンドウを閉じて通常権限PowerShellから下記を実行。OANOCACHE=1を子プロセスだけに設定してRC35を起動。

   powershell -NoProfile -ExecutionPolicy Bypass -File .\HeapTrace.ps1 -Mode Launch -ExePath ".\C545D_Recorder.exe"

   RC35で録画開始。SEI対策は通常どおり初期ONです。

4. 録画が落ち着いてから1回目のスナップショット。録画は停止しません。

   powershell -NoProfile -ExecutionPolicy Bypass -File .\HeapTrace.ps1 -Mode Capture

5. 約15分（目安10～20分）録画継続後、同じPIDで2回目。

   powershell -NoProfile -ExecutionPolicy Bypass -File .\HeapTrace.ps1 -Mode Capture

6. 差分比較と安全ZIPを作成（録画中でも可）。

   powershell -NoProfile -ExecutionPolicy Bypass -File .\HeapTrace.ps1 -Mode Compare

   %LOCALAPPDATA%\C545D_GStreamer\HeapTrace の C545D_HEAP_SAFE_REPORT_PID*.zip のみChatGPTに提出。UMDH_RAW*.txtは提出しない。

7. 調査終了後、管理者PowerShellで必ず元の設定へ戻す。

   powershell -NoProfile -ExecutionPolicy Bypass -File .\HeapTrace.ps1 -Mode Restore

## 重要事項
- GFlagsは設定後に起動されたgst-launchだけへ有効。稼働中の既存録画に後から有効化できません。
- gst-launchが複数ある場合は対象を確認して -TargetPid 数字 を指定。推測しない。
- UMDH生ログにはアドレス、スタック、個人ファイルパスが含まれる可能性がある。絶対にGitHubへアップロードしない。
- 安全ZIPは数値とDLL名だけを抽出するが、未知の情報形式まで完全な匿名化を保証するものではありません。
- USTはCPU・メモリに計測負荷を加えます。診断終了時はRestoreを実行してください。
- Windows Heapで差が出なくても、GLib等の独自アロケータの問題がないとは断定できません。
- Windows CIは構文とダミー差分検査。UMDH実機取得や長時間録画は未検証です。

公式：
https://learn.microsoft.com/ja-jp/windows-hardware/drivers/debugger/using-umdh-to-find-a-user-mode-memory-leak
https://learn.microsoft.com/ja-jp/windows-hardware/drivers/debugger/preparing-to-use-umdh
