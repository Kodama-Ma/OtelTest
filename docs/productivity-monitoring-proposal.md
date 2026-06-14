# Claude Code 生産性チェック — OTel + Grafana 組織運用プロポーザル

---

## 大前提

> **トークン量・コスト・LOC は "活動量" であって "生産性" ではない。**

「行数で評価」は水増しを誘発し逆効果。**活動量 × 成果 × 採用 × 定性** を組み合わせ、
**個人の査定ではなくチームの改善ループ**に使うことが鉄則。

---

## フェーズ構成

### Phase 0 — 基盤整備（ローカル検証から本番化へ）

- LGTM スタックを**中央常設**に移す（Colima ローカルではなく、社内サーバー or Grafana Cloud）
- `CLAUDE_CODE_ENABLE_TELEMETRY=1` と `OTEL_*` を **managed settings** で全社配布（MDM 経由、ユーザー上書き不可）
- `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` は**必須**（これがないと Prometheus にメトリクスが出ない）
- mTLS または Bearer Token でコレクタへの通信を保護

**managed settings 例（`/etc/claude/managed_settings.json`）:**
```json
{
  "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
  "OTEL_METRICS_EXPORTER": "otlp",
  "OTEL_LOGS_EXPORTER": "otlp",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.internal.example.com:4317",
  "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative",
  "OTEL_METRIC_EXPORT_INTERVAL": "60000",
  "OTEL_METRICS_INCLUDE_VERSION": "true",
  "OTEL_METRICS_INCLUDE_ENTRYPOINT": "true"
}
```

---

### Phase 1 — 識別とセグメント

全シグナルに**チーム情報を付与**することで、チーム別・部署別の集計が可能になる。

**各メンバーの環境変数（チームごとに変わる部分）:**
```bash
export OTEL_RESOURCE_ATTRIBUTES="department=engineering,team.id=platform,cost_center=eng-123"
```

`user.email` / `user.account_uuid` / `organization.id` は認証済みなら自動付与。
これにより「誰が・どのチームで・いつ・どれだけ使ったか」がメトリクス上で紐付く。

---

### Phase 2 — 指標フレーム（4層で見る）

生産性をトークン量だけで判断しないための4層構造。

| 層 | 何を測るか | 取得元 | OTelシグナル |
|---|---|---|---|
| **採用 (Adoption)** | DAU/WAU、チーム別カバレッジ、`resume` 率 | Prometheus | `session.count` |
| **活動 (Activity)** | トークン/コスト、LOC、active_time、モデル・effort 構成、fast mode率 | Prometheus + Loki | `token.usage` / `cost.usage` / `lines_of_code.count` / `active_time.total` / `api_request` |
| **成果 (Outcome)** | commit 数 / PR 数、ツール成功率、エラー率、リトライ枯渇 | Prometheus + Loki | `commit.count` / `pull_request.count` / `tool_result` / `api_error` |
| **健全性 (Health)** | ツール拒否率、compaction 頻度、フィードバック傾向 | Prometheus + Loki | `code_edit_tool.decision` / `compaction` / `feedback_survey` |

---

### Phase 3 — 外部データとの接続でこそ「生産性」が言える

Claude Code のテレメトリ単体では **"使った量"** 止まり。以下と組み合わせて初めて効果が可視化できる。

| 外部データ | 接続ポイント | 何が分かるか |
|---|---|---|
| **GitHub / GitLab (DORA メトリクス)** | `commit.count` / `pull_request.count` を軸に JOIN | PRリードタイム・変更失敗率・デプロイ頻度との相関 |
| **Claude 非使用チームとの比較** | 同期間・同規模チームで `lines_of_code` / `commit` / `PR` を比較 | Claude Code 導入効果の差分 |
| **ビルド・テスト結果（CI）** | hooks 経由で CI 結果を OTel に追加送信 | コード品質との相関（LOC追加だけでなくテスト通過率も） |
| **インシデント数（PagerDuty等）** | 時系列で重ねて表示 | 生産速度向上がバグ増加を伴っていないか確認 |

---

### Phase 4 — ダッシュボード構成（3枚に分ける）

#### ダッシュボード 1: 経営・採用サマリー
対象: 経営層・部門長

| パネル | 内容 |
|---|---|
| 全社採用率（DAU/全ライセンス数） | チームごとのアクティブ率ヒートマップ |
| 月次コスト推移（チーム別） | コストの集中・偏りを検出 |
| commit/PR 数推移 | 成果の月次トレンド |
| モデル構成比 | どのモデルが使われているか（コスト最適化ヒント） |

#### ダッシュボード 2: チームリード用
対象: チームリード・エンジニアリングマネージャー
変数: `team.id` でフィルタ

| パネル | 内容 |
|---|---|
| 週次セッション数・active_time | チームの活動量トレンド |
| LOC (added / removed) 比率 | 増やした vs 削除した（削除もポジティブ） |
| ツール成功率ランキング | 失敗率の高いツール・操作を特定 |
| エラー・リトライ率 | API 障害や使い方の問題を検出 |
| effort 分布 | low/medium/high/max どの作業難度が多いか |

#### ダッシュボード 3: プラットフォーム / SRE 用
対象: 基盤チーム・セキュリティ

| パネル | 内容 |
|---|---|
| コレクタ受信率（`otelcol_receiver_accepted_*`） | テレメトリ基盤の健全性 |
| MCP 接続成否ログ（Loki） | どの MCP ツールが繋がっているか |
| トレース（Tempo）ウォーターフォール | 重いリクエストのボトルネック特定 |
| permission_mode 変更ログ | セキュリティ監査 |
| tool_decision 拒否ログ | ポリシー違反試行の検出 |

---

### Phase 5 — ガバナンス・プライバシー（必須）

組織展開前に決めておく必要がある事項。

| 項目 | 推奨方針 |
|---|---|
| **プロンプト本文の取得** | 原則 OFF（`OTEL_LOG_USER_PROMPTS` は出さない）。監査目的で必要な部署は個別に同意取得 |
| **ツール引数の取得** | `OTEL_LOG_TOOL_DETAILS=1` は機密コマンドが漏れるリスクあり。デフォルト OFF |
| **個人ランキングで吊るさない** | 集計粒度は基本チーム単位。個人データは本人のみ参照可 |
| **データ保持期間** | メトリクス: 13ヶ月、ログ: 90日 など事前に決める |
| **SIEM 連携** | `api_error` / `tool_decision(reject)` / `permission_mode_changed` は SIEM に別送信して監査ログとして管理 |
| **アクセス制御** | Grafana の org/team 権限でダッシュボードを分離（経営層は集計のみ、個人データは見えない） |

---

## 指標の読み方 — よくある罠

| 指標が上がった | 良い解釈 | 悪い解釈（罠） | 確認方法 |
|---|---|---|---|
| LOC (added) 増加 | 機能追加が加速 | コードの水増し | PR数・テスト通過率と同時確認 |
| トークン量増加 | 複雑な作業を任せている | 無駄な会話が多い | effort分布・active_timeと比較 |
| セッション数増加 | 採用拡大 | 同じ失敗を繰り返している | tool_result 成功率と比較 |
| コスト増加 | 活用が広がっている | 特定チームに集中 | チーム別内訳を確認 |

---

## ロードマップ（ローカル検証から組織展開まで）

```
[今] ローカル検証（Colima + LGTM）
  ↓
[次] 生産性ダッシュボード v2 追加（LOC/commit/PR/ツール成功率）
  ↓
[近] トレース有効化（beta）→ Tempo でリクエスト単位を追う
  ↓
[中期] 中央 OTel Collector 化 + managed settings 全社配布
  ↓
[中期] チーム属性付与 + ダッシュボード3枚化
  ↓
[長期] GitHub/DORA との接続 → 「生産性」の定量化
```

---

## 参考

- Claude Code monitoring ドキュメント: https://code.claude.com/docs/en/monitoring-usage
- Grafana LGTM: https://github.com/grafana/docker-otel-lgtm
- OpenTelemetry 仕様: https://opentelemetry.io/ja/docs/
- OTel × Grafana データリファレンス: `./otel-grafana-data-reference.md`
