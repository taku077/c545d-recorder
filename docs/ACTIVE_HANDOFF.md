# C545D — 現在の開発引継ぎ（自動生成の入口）

**重要：このファイルは本リポジトリの新しい単一入口です。** GitHub ActionsによりPR #54の最新ブランチ・同一HEADのCI結果から再生成されます。

- 現在の開発PR: [#54](https://github.com/taku077/c545d-recorder/pull/54) / `investigate/gio-2824-key-handle-lifecycle`
- 前回確認時のHEAD: `d08eeb5d2fb52bf1fa735301a7cd05bcebb86f61`
- GLib 2.82.4の`Application`–`ShellVerb`循環参照を`GWeakRef`へ変え、レジストリパスの重複`g_wcsdup()`も除去。
- Windows-2022/MSYS2 64サイクル自動検証で、weakrefのみPrivateUsage +39,497,728B → 併用修正 +1,466,368B（**96.29%削減**）。16サイクルのハンドル純増は無修正 +5,152 → 併用修正 **0**。64サイクルでは併用修正 +2。
- **実機に修正版DLLはまだ適用していない。** 残存メモリ約1.40MiBの原因と、安全な配布互換性を調査中。
- 直近HEADの新たなCI: 64サイクルハンドル+7で許容±4超過、MSVC版ABI差分はSDK公開エクスポート1個欠落。**配布不可のゲートが残る。**
- 根拠: [成功した比較 #44363594321](https://github.com/taku077/c545d-recorder/actions/runs/44363594321) / [最新弱参照テスト #44366839862](https://github.com/taku077/c545d-recorder/actions/runs/44366839862) / [MSVC互換性 #44366839819](https://github.com/taku077/c545d-recorder/actions/runs/44366839819)。
- **これは初期スナップショットです。** 新しいGitHub Actions `C545D active development handoff auto-refresh` が稼働すると、PR HEADに固定した最新資料とCI一覧へ自動更新されます。現在のライブPRを必ず確認してください。

詳細手順: [HANDOFF_READ_FIRST.md](HANDOFF_READ_FIRST.md)
