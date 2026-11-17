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
