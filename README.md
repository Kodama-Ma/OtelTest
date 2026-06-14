# Claude Code テレメトリ ローカル検証環境 (OpenTelemetry + Grafana LGTM)

Claude Code 自身の利用状況テレメトリ（トークン消費・コスト・ツール実行など）を、
ローカルの **Grafana LGTM**（Grafana / Loki / Tempo / Prometheus / OTel Collector のオールインワン）
に送って可視化・検証するための環境です。コンテナは **Colima** 上の Docker で動かします。

参考:
- Grafana docker-otel-lgtm: https://github.com/grafana/docker-otel-lgtm
- OpenTelemetry docs: https://opentelemetry.io/ja/docs/
- Claude Code monitoring: https://code.claude.com/docs/en/monitoring-usage
- (発想元) zenn: https://zenn.dev/microsoft/articles/f439e06d07123e ※記事自体はCopilot CLI向け

## 構成

```
 ┌────────────┐   OTLP gRPC(4317)   ┌──────────────────────────────┐
 │ Claude Code│ ───────────────────►│ grafana/otel-lgtm (Colima)   │
 │  (CLI)     │   metrics / logs    │  Collector→Prometheus/Loki   │
 └────────────┘                     │  Grafana UI :3000            │
                                    └──────────────────────────────┘
```

## 前提

- Colima + docker CLI（`brew install colima docker docker-compose`）

## 起動手順

```bash
# 1) Colima 起動（VM。初回はイメージDLで数分）
colima start --cpu 2 --memory 4

# 2) LGTM スタック起動
docker compose up -d

# 3) 起動確認（ヘルスチェック）。Grafana が立つまで30〜60秒ほど待つ
open http://localhost:3000      # admin / admin

# 4) Claude Code 側のテレメトリ設定を読み込んで起動
source ./claude-otel.env
claude
```

## 確認方法（Grafana）

1. http://localhost:3000 にアクセス（admin/admin、初回パスワード変更はSkip可）
2. 左メニュー **Explore** を開く
3. データソース **Prometheus** を選び、メトリクスを検索:
   - `claude_code_token_usage_total` … トークン使用量
   - `claude_code_cost_usage_total` … 推定コスト(USD)
   - `claude_code_session_count_total` … セッション数
   - `claude_code_lines_of_code_count_total` … 編集行数
   - `claude_code_commit_count_total` / `claude_code_pull_request_count_total`
4. ログ/イベントは データソース **Loki** で `{service_name="claude-code"}` を検索
   （`user_prompt` / `tool_result` / `api_request` などのイベント）

メトリクスは 10 秒間隔（`claude-otel.env` の設定）で送信されるので、
Claude Code で何か操作してから10〜20秒待つと反映されます。

## ハマりどころ / トラブルシュート

- **メトリクスが Grafana に出ない（最重要）**: Claude Code はデフォルトで
  **delta** temporality で送るが、LGTM の Prometheus は **cumulative** を期待する。
  そのままだとコレクタは受信するのに Prometheus 変換で落ちる。
  → `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative`（`claude-otel.env` に設定済み）。
- **反映の確認（コレクタが受信したか）**:
  ```bash
  docker exec otel-lgtm curl -s \
    'http://localhost:9090/api/v1/query?query=otelcol_receiver_accepted_metric_points_total'
  ```
  `otlp grpc/http` の値が増えていれば受信はできている（あとは temporality 問題を疑う）。
- メトリクスは送信間隔（10秒）ごと。操作後 10〜20 秒待つ。

## 検証済みの結果（2026-06-14）

`source ./claude-otel.env && claude` で実際に流して確認済み:
- `claude_code_token_usage_tokens_total`（input/output/cacheRead/cacheCreation, model別）
- `claude_code_cost_usage_USD_total`（推定コストUSD）
- `claude_code_session_count_total` / `claude_code_active_time_seconds_total`
- Loki に `api_request` などのイベントログ

## 停止 / 後片付け

```bash
docker compose down          # スタック停止（データは volume に残る）
docker compose down -v       # データも削除
colima stop                  # VM 停止
```

## ファイル

| ファイル | 役割 |
|----------|------|
| `docker-compose.yml` | LGTM スタック定義 |
| `claude-otel.env`    | Claude Code 用 OTLP 送信設定（`source` して使う） |
| `reference/reference.md` | 元の参考メモ |
