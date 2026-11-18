C545D: ETLオフライン自動解析（実機検証前の試験版）
===================================================
目的：既存の202MB ETL（21:01の428ハンドル増加）から
PID 6168のハンドル生成スタックの「安全なモジュール名・関数名・件数」
を自動集計します。WPA画面の操作やwpaProfileの作成は不要です。

使い方：
1. 同梱のSTART_OFFLINE_ETL_ANALYSIS.cmdをダブルクリック。
2. 完了後、画面に表示される保存先のSAFE_SUMMARY.txtだけをチャットへ貼付。
3. ETL本体・レジストリパス・生のスタック情報はアップロード不要です。

注記：
- ETLは%LOCALAPPDATA%\C545D_GStreamer\WPR_Handle\C545D_Handle_20261118_210100.etl
- 上記ファイルのみ読み取り、録画・UST・GFlags・ハンドル・レジストリを変更しません。
- Microsoft .NET TraceProcessingのOtherHandlesは汎用ハンドル情報であり、
  このAPIだけではKey型と断定できません。
- no_close_recorded はETL内にCloseイベントがなかった件数であり、
  解放漏れの証明ではありません。
- ETLが生成スタックを含まない場合はNO_CREATE_STACKS_AVAILABLEと報告します。
- 公開PDBがない場合は関数名が出ない場合があります。既定では
  シンボルサーバーへのアクセスをしません。
- 202MBのETLを解析するため、古いHDD機ではCPU/RAM負荷に注意してください。
  録画に支障が出たら解析ウィンドウを閉じ、録画を優先してください。
- セルフテスト、CIビルドだけではユーザー実機ETLでの成功は保証できません。

Microsoft公式：
https://learn.microsoft.com/en-us/windows/apps/trace-processing/tutorial
https://learn.microsoft.com/en-us/windows/apps/trace-processing/symbols
