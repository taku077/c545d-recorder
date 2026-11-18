# C545D ハンドル種類別・4時間自動記録

Windows 10 / Windows PowerShell 5.1 専用。2026-11-18のメモリCSVでは `gst-launch-1.0.exe` のハンドルが毎時01分と24分ごろに約428個ずつ増加した。これがどのカーネルオブジェクト型に集中するか、**録画を維持しながら毎分自動記録**する。

## セットアップ

1. **公式Microsoft Sysinternals Handle** を入手する: https://learn.microsoft.com/ja-jp/sysinternals/downloads/handle
2. 公式の `Handle.zip` を展開し、`handle64.exe` を `Monitor-C545DHandleTypes.ps1` と同じフォルダーに置く。Microsoftの実行ファイルをプロジェクトの配布ZIPに同梱しない。
3. 録画が通常稼働している状態で、`START_HANDLE_TYPES_4H.cmd` を**右クリック→管理者として実行**する。Handleは公式仕様で管理者権限が必要。初回の `-accepteula` でSysinternals EULAを受諾する（意図しない場合は実行しない）。
4. 起動時に `Preflight OK` が表示されることを確認する。取得権限不足・Handleの未設置・出力形式不一致なら4時間記録を始めず終了する。
5. コマンドウィンドウを最小化。4時間（1分間隔）で自動終了する。途中で閉じると記録は中断する。

## 保存されるデータ

`%LOCALAPPDATA%\C545D_GStreamer\HandleTypesMonitor\` 内に次の3つ：

- `C545D_HandleSummary_日時.csv`: timestamp, PID, process start, status, PrivateMB, WorkingSetMB, Get-ProcessのHandles, HandleのTotal handles, 種類合計, ツール応答時間
- `C545D_HandleTypes_日時.csv`: timestamp, sample, PID, **オブジェクト型名と件数のみ**
- `C545D_HandleEvidence_日時.zip`: 上記CSVを2つまとめた提出用ファイル

**提出するのはZIP1本だけ。** 個々のハンドルの名前、ファイルパス、レジストリ名、rawスタック、カメラ認証情報は取得・保存しない。非公開のローカルパスや個人情報を公開リポジトリに入れない。

- 複数 `gst-launch-1.0.exe`、実行失敗、PID変化などをステータスとして明示。
- `ProcessHandles` と `HandleToolTotal` は取得タイミングのずれで一致しないことがある。
- 1分ごとのHandle.exe起動で小さな負荷が生じ得る。実機の4時間無停止動作と実機ハンドル種類は未検証。
- **GFlags/USTの変更、再Capture、MP4ファイル操作、ハンドル強制close(`-c`)は一切しない。**
- Windows PowerShell5.1構文と解析の合成テスト・Windows実行環境でのHandle公式実行テストはGitHub Actionsで確認する。実録画のハンドル増加原因はまだ未確定。

手動の短い確認コマンド（**管理者PowerShell**・ツールのあるフォルダー内）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Monitor-C545DHandleTypes.ps1" -SelfTest
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Monitor-C545DHandleTypes.ps1" -Preflight
```

出典： https://learn.microsoft.com/ja-jp/sysinternals/downloads/handle
