# OTel × Grafana — 取得できるデータリファレンス

Claude Code が出力する OTel シグナルと、Grafana で扱えるデータの全体像をまとめたリファレンスです。

---

## 1. OTelで取れるデータ — これで全部か

Claude Code が公式に出力するシグナルは **3種類**。以下が完全なリストです（2026-06 時点、Claude Code v2.1.177 確認）。

### A. メトリクス（時系列・全8種）

| メトリクス名 | 内容 | 主な属性（分解軸） |
|---|---|---|
| `claude_code.session.count` | セッション開始数 | `start_type`(fresh/resume/continue) |
| `claude_code.token.usage` | トークン量 | `type`(input/output/cacheRead/cacheCreation), `model` |
| `claude_code.cost.usage` | 推定コスト USD | `model` |
| `claude_code.active_time.total` | 実作業秒数 | — |
| `claude_code.lines_of_code.count` | 追加/削除した行数 | `type`(added/removed), `model` |
| `claude_code.commit.count` | git commit 作成数 | — |
| `claude_code.pull_request.count` | PR 作成数 | — |
| `claude_code.code_edit_tool.decision` | 編集ツールの許可/拒否数 | decision |

> **今のローカルダッシュボードは上4つのみ使用。**
> `lines_of_code` / `commit` / `pull_request` / `code_edit_tool.decision` が未使用で、これらが生産性観点では特に重要。

#### 全メトリクスに共通する標準属性

| 属性 | 内容 |
|---|---|
| `session.id` | セッション識別子（デフォルト on） |
| `user.account_uuid` / `user.account_id` | アカウント UUID（デフォルト on） |
| `user.email` | OAuth 認証済みユーザーのメールアドレス |
| `user.id` | インストールスコープの匿名 ID（常時付与） |
| `organization.id` | 組織 UUID |
| `terminal.type` | iTerm.app / vscode / cursor / tmux など |
| `app.version` | Claude Code バージョン（デフォルト off） |
| `app.entrypoint` | cli / sdk-ts / sdk-py / claude-vscode など（デフォルト off） |
| `OTEL_RESOURCE_ATTRIBUTES` のキー | 任意カスタム属性（department / team.id など） |

---

### B. イベント（Loki に溜まる行動ログ・全約25種）

| イベント名 | いつ発火するか | 主な属性 |
|---|---|---|
| `user_prompt` | ユーザーがプロンプトを送信したとき | `prompt_length`, `command_name`, `command_source` |
| `tool_result` | ツールが実行完了したとき | `tool_name`, `success`, `duration_ms`, `error_type`, `decision_source` |
| `api_request` | Claude API リクエストのたび | `model`, `cost_usd`, `duration_ms`, `input/output/cache_*_tokens`, `speed`, `effort`, `query_source` |
| `api_error` | API リクエスト失敗時 | `error_type`, `http_status_code` |
| `api_refusal` | モデルが実行を拒否したとき | `refusal_category` |
| `api_retries_exhausted` | リトライ上限到達時 | `error_type`, `attempts` |
| `tool_decision` | ツール実行の許可/拒否決定時 | `tool_name`, `decision_type`, `decision_source` |
| `permission_mode_changed` | Permission モード変更時 | `permission_mode` |
| `mcp_server_connection` | MCP サーバー接続試行時 | `mcp_server_name`, `success` |
| `skill_activated` | スキル起動時 | `skill_name` |
| `plugin_installed` / `plugin_loaded` | プラグイン操作時 | `plugin_name` |
| `compaction` | コンテキスト圧縮時 | `tokens_before/after` |
| `internal_error` | 内部エラー発生時 | `error_type`, `error` |
| `feedback_survey` | フィードバック送信時 | `sentiment` |
| `hook_registered` / `hook_execution_start` / `hook_execution_complete` | フック操作時 | `hook_event`, `duration_ms`, `exit_code` |
| `auth` | 認証操作時 | `auth_type` |
| `at_mention` | @ メンション使用時 | — |

> イベントには `prompt.id`（プロンプト単位の相関 ID）が付き、同一プロンプト起因のイベントを横断して追える。

---

### C. トレース（beta）— リクエスト単位の span

有効化: `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER=otlp`

```
claude_code.interaction          ← ユーザープロンプト1回分のルートspan
├── claude_code.llm_request      ← API呼び出し
├── claude_code.hook             ← フック実行
└── claude_code.tool             ← ツール実行
    ├── claude_code.tool.blocked_on_user  ← 許可待ち時間
    ├── claude_code.tool.execution        ← 実行時間
    └── (Agent tool) サブエージェントのspan群
```

Tempo でリクエスト1回のウォーターフォール（どのツールが何ms かかったか）が見える。

---

## 2. OTelのカスタマイズ — できること・できないこと

### できること

| 目的 | 手段 |
|---|---|
| チーム/部署ラベルを付ける | `OTEL_RESOURCE_ATTRIBUTES="department=eng,team.id=platform,cost_center=cc-123"` |
| プロンプト本文を記録 | `OTEL_LOG_USER_PROMPTS=1`（プライバシー注意） |
| ツール引数・エラー詳細を記録 | `OTEL_LOG_TOOL_DETAILS=1` |
| トレースを有効化 | `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER=otlp` |
| メトリクスとログを別エンドポイントへ | `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` / `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` で別指定 |
| 組織全体へ強制配布 | managed settings（MDM 経由、ユーザー上書き不可） |
| カーディナリティ削減 | `OTEL_METRICS_INCLUDE_SESSION_ID=false` などで属性を削る |
| hooks で独自データを追加 | hooks 経由で外部にメトリクスを push（Claude Code 外のデータと合成） |

### できないこと

- Claude Code が出す**メトリクス定義を増やすことはできない**（公式の8種が上限）
- イベントに**任意のフィールドを追加**することはできない（属性は公式仕様に固定）
- ただし Grafana 側で既存データから**派生指標・集計比率**は自由に計算できる

---

## 3. Grafanaで見えるデータ — これで全部か / カスタムできるか

### 利用できる4つのデータソース（grafana/otel-lgtm 構成の場合）

| データソース | 役割 | 主な用途 |
|---|---|---|
| **Prometheus** | メトリクス時系列 | PromQL で集計・派生指標・アラート |
| **Loki** | イベントログ | LogQL でツール成功率・duration 集計・行動分析 |
| **Tempo** | 分散トレース | リクエスト単位のウォーターフォール（beta 要） |
| **Pyroscope** | 継続プロファイリング | パフォーマンス分析（Claude Code には直接関係薄） |

### 今のダッシュボードは「全部」ではない

現状のローカルダッシュボード (`claude-code-otel`) は検証用のサンプルです。Grafana は以下のすべてが自由にカスタムできます:

- パネル種別（stat / timeseries / barchart / piechart / table / heatmap / logs / traces …）
- 変数（model / team / user でドリルダウン）
- ダッシュボードの数・構成（ロール別に複数枚）
- アラート（コスト上限・エラー率閾値でSlack/PagerDuty通知）
- JSON ファイルでバージョン管理・GitOps 運用可能

### Loki での集計例（LogQL）

```logql
# ツール別の成功率
sum by (tool_name) (count_over_time({service_name="claude-code", event_name="tool_result", success="true"}[1h]))
/
sum by (tool_name) (count_over_time({service_name="claude-code", event_name="tool_result"}[1h]))

# ツール実行時間の分布（duration_ms を抽出）
quantile_over_time(0.95, {service_name="claude-code"} | json | event_name="tool_result" | unwrap duration_ms [1h]) by (tool_name)
```

---

## ローカル環境で確認済みの動作（2026-06-14）

- コレクタ受信確認: `otelcol_receiver_accepted_metric_points_total` (grpc/http とも正常)
- Prometheus 到達確認: `claude_code_*` 4系列 (cost / token / session / active_time)
- Loki 到達確認: `api_request` イベント
- **重要な落とし穴**: `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` が必須（デフォルトの delta では Prometheus に出てこない）
