# C545D — 次回再開時に最初に読むファイル

**最優先は [ACTIVE_HANDOFF.md](ACTIVE_HANDOFF.md) と最新の [PR #54](https://github.com/taku077/c545d-recorder/pull/54)。** `main/docs/HANDOFF_CURRENT.md` の古い先頭のみから再開してはいけない。

## 自動引継ぎのしくみ

- `docs/ACTIVE_HANDOFF_CONFIG.json` が「現在の作業PR」を指定する。今はPR #54。
- `tools/refresh_active_handoff.py` はGitHubのAPIから指定PRの**最新HEAD SHAを取得**し、そのSHAの `docs/HANDOFF_CURRENT.md` の新しいセクションと、同一SHAで実行されたCIの成否を読み取る。
- `.github/workflows/active-handoff-refresh.yml` がPR更新・3時間ごとの定期実行・手動実行で `docs/ACTIVE_HANDOFF.md` を更新する。**PRのコードは実行しない。**
- 次のチャットでは生成ファイルのHEADと、GitHubのライブHEADが一致するかを照合する。一致しなければライブPRを確認する。自動更新の遅延・失敗はあり得る。
- 異なるPRを現在の作業にする場合、CONFIGを**意図的に**更新する。古い成果が黙って「最新」に戻らないよう、required_evidenceガードを使用する。
- GitHub Actionsの成功とユーザー実機での改善は必ず区別する。64サイクルの96.29%は**自動検証条件下のPrivateUsage増加量の削減**である。実機への修正配布は未実施。
- 実機録画は停止・再起動させず、資格情報・生ETL・レジストリ名を公開しない。未検証DLLのすり替えは禁止。

## 次回の作業順序

生成ファイル → 生きているPRのHEAD/CI/失敗ログ → 合格済みテストと未解決ゲート → 修正と自動検証。完了済みのWPRや4時間監視、手動WPA操作には戻らない。
