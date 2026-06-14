# AI コーディングツール 利用状況モニタリング — クイックリファレンス

対象: **Claude Code** / **Codex CLI**（どちらも同じ Grafana LGTM スタックで収集・可視化）

詳細版: `org-ai-adoption-plan.md` / `otel-grafana-data-reference.md` / `productivity-monitoring-proposal.md`

---

## 起動（ローカル検証）

```bash
colima start --cpu 2 --memory 4   # VM起動（初回のみ）
docker compose up -d               # Grafana LGTM 起動
```

ダッシュボード → http://localhost:3000 （admin / admin）

---

## ツール別セットアップ

### 🟣 Claude Code

```bash
source ./claude-otel.env   # OTel 設定を読み込む
claude                     # ← これ以降が Grafana に流れる
```

**組織配布用**（`~/.claude/managed_settings.json`）:
```json
{
  "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
  "OTEL_METRICS_EXPORTER": "otlp",
  "OTEL_LOGS_EXPORTER": "otlp",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.your-company.com:4317",
  "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative",
  "OTEL_RESOURCE_ATTRIBUTES": "department=eng,team.id=platform"
}
```
> `claude auth login` 済みなら `user.email` が自動付与。チームごとに `team.id` だけ変える。

### 🟢 Codex CLI

```bash
# ~/.codex/config.toml を作成（1回のみ）
mkdir -p ~/.codex && cat > ~/.codex/config.toml <<EOF
[otel]
environment = "local"
exporter = { otlp-grpc = {
  endpoint = "http://localhost:4317"
}}
EOF

codex   # ← これ以降が Grafana に流れる
```

**組織配布用**（`~/.codex/config.toml`）:
```toml
[otel]
environment = "production"
exporter = { otlp-grpc = {
  endpoint = "https://otel.your-company.com:4317",
  headers = { "Authorization" = "Bearer ${OTLP_TOKEN}" }
}}
```
> `codex exec` はメトリクス未送信、`codex mcp-server` はテレメトリ全未対応（2026-06時点の既知制限）。

---

## ダッシュボード一覧

| ダッシュボード | URL | 用途 |
|---|---|---|
| **🟣 Claude Code Productivity v2** | `/d/claude-code-productivity-v2` | Claude Code 専用。採用度・成果・効率・ランキング |
| **🟢 Codex Productivity** | `/d/codex-productivity` | Codex 専用。リクエスト・ツール成功率・処理時間 |
| **🔀 統合比較** | `/d/ai-tools-unified` | 両ツールを並べて比較。総合スコアランキング付き |
| **Claude Code (basic)** | `/d/claude-code-otel` | コスト・トークン・Loki ログの基本ビュー |

---

## 🟣 Claude Code — 何を見るか

時間範囲: **Last 7d**。User / Model フィルタで絞り込み可。

| 知りたいこと | 見るパネル | 目安 |
|---|---|---|
| 何人が使っているか（DAU） | 👥 アクティブユーザー数 | ライセンス数の 60% 以上 |
| 会話を引き継いで使えているか | 🔄 resume率ランキング | 30% 以上が健全 |
| モデルの使い方が偏っていないか | 📊 モデル別コスト内訳 | Opus 60% 超なら要最適化 |
| エラーが起きていないか | ⚠️ APIエラー発生数 | 急増したら要確認 |
| 誰がコストを使っているか | 🏆 コストランキング | 上位3名を先週比で確認 |
| 実際にコードを書けているか | 📝 LOCランキング | チーム平均の 1.5 倍超なら効果あり |
| 少ない費用で多く書いているか | コスト効率 LOC/USD | 高いほど効率的 |
| キャッシュを活かせているか | 🧮 cacheRead率ランキング | 70% 以上が目標 |
| ツールを止められていないか | ユーザー別 ツール拒否率 | 25% 超は設定見直し |

## 🟢 Codex — 何を見るか

| 知りたいこと | 見るパネル | 目安 |
|---|---|---|
| どれだけ API を呼んでいるか | 🏆 APIリクエスト数ランキング | 多いほどアクティブ |
| ツールがちゃんと動いているか | ユーザー別 ツール成功率 | 92% 以上が目標 |
| 何のツールをよく使っているか | ツール別使用回数 | apply_patch が多いほど実際の編集に活用 |
| エラーが多いユーザーは誰か | ⚠️ ツール失敗数ランキング | 10 超は権限・操作方法を確認 |
| どのモデルを使っているか | モデル別トークン分布 | o3 偏りはコスト増リスク |

---

## 上手に使っている人の特徴

**Claude Code**:
```
✅ resume率 30% 以上     （会話を引き継いでいる）
✅ cacheRead率 70% 以上  （同じ文脈を繰り返し活用）
✅ LOC/USD が高い        （少コストで多くのコードを出力）
✅ ツール拒否率 10% 以下  （適切な権限範囲で動かせている）
```

**Codex**:
```
✅ ツール成功率 92% 以上  （エラーなく操作できている）
✅ apply_patch の比率が高い（質問だけでなく実際に編集している）
✅ 処理時間が長い         （複雑なタスクを任せている）
```

## コスト無駄打ち・問題のサイン

**Claude Code**:
```
⚠️ LOC/USD が低い（100以下）  → 同じ質問の繰り返し or プロンプト過大
⚠️ cacheRead率 50% 未満       → 毎回新規セッションで起動している
⚠️ Opus がコストの 60% 超     → 単純作業に高コストモデルを使っている
⚠️ ツール拒否率 25% 超        → 毎回 Permission で手が止まっている
```

**Codex**:
```
⚠️ ツール失敗数が多い（10超）  → 権限設定のミス or 危険な操作を試みている
⚠️ o3 がトークンの 80% 超     → 軽いタスクに高コストモデルを使っている
⚠️ api_request 数が少ない     → ほぼ使われていない（オンボーディングが必要）
```

---

## 週次レビュー（10分）

```
① 統合比較ダッシュボードで両ツールの総合スコアを確認
② 各ツールのランキングで上位・下位ユーザーを把握
③ 異常値チェック（拒否率 / 失敗数 / APIエラー）
④ 必要なら個別フォロー or ベストプラクティス共有
```

---

## テレメトリ・用語メモ

| 用語 | 意味 |
|---|---|
| **テレメトリ** | アプリが自分の動作を自動で外部に送り続ける仕組み。OTel はその業界標準 |
| **OTLP** | OTel のデータ送信プロトコル。gRPC(4317) か HTTP(4318) で送る |
| **DAU** | Daily Active Users。その日に1回以上使ったユーザー数 |
| **resume率** | 全セッションのうち前の会話を引き継いだ割合（Claude Code） |
| **cacheRead率** | 総トークンのうちキャッシュから読んだ割合。高いほど低コスト（Claude Code） |
| **LOC/USD** | 1ドルあたり追加した行数。コスト効率の指標（Claude Code） |
| **cumulative** | Prometheus が期待するメトリクスの集計方式。**Claude Code のみ必要**（Codex は不要） |
| **apply_patch** | Codex のコード編集ツール。多いほど実際の編集作業に使えている |

---

## トラブル早見表

| 症状 | 対処 |
|---|---|
| Claude Code のデータが出ない | `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative` を確認 |
| Codex のデータが出ない | `~/.codex/config.toml` の `[otel]` ブロックを確認 |
| user_email ラベルがない | `claude auth login` を実行（Claude Code）|
| コレクタに届かない | `nc -z -w3 <host> 4317` でポート疎通を確認 |
| `claude -p` が止まる | コマンド末尾に `</dev/null` を付ける |
| Codex mcp-server のデータがない | 既知の制限（2026-06）。interactive モードのみ対応 |
