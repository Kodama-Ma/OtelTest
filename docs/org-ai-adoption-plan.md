# 組織の AI 活用度計測プラン
## Claude Code × OTel × Grafana 運用ガイド

> **対象読者**: エンジニアリングマネージャー・プラットフォームチーム  
> **目的**: ClaudeCode の組織全体への展開、テレメトリ収集、ダッシュボードによる生産性・コスト分析の一連の手順と判断基準を定める

---

## 1. 全体アーキテクチャ

```
 ┌─────────────────────────────────────────────────┐
 │ 各メンバーの端末（Mac / Windows / Linux）         │
 │                                                  │
 │  Claude Code CLI                                 │
 │   ├─ ~/.claude/managed_settings.json  ← MDM配布  │
 │   └─ OTEL_* 環境変数で自動テレメトリ送信          │
 └─────────────────┬───────────────────────────────┘
                   │ OTLP gRPC / HTTP (TLS)
                   ▼
 ┌─────────────────────────────────────────────────┐
 │ 中央 OTel Collector (社内サーバー or Grafana Cloud)│
 │   ├─ Metrics → Prometheus / Mimir              │
 │   ├─ Logs    → Loki                            │
 │   └─ Traces  → Tempo (beta)                    │
 └─────────────────┬───────────────────────────────┘
                   │
                   ▼
 ┌─────────────────────────────────────────────────┐
 │ Grafana ダッシュボード                            │
 │   ├─ 経営サマリー（採用率・コスト）               │
 │   ├─ チームリード用（成果・効率）                 │
 │   └─ Productivity v2（ランキング・比較）          │
 └─────────────────────────────────────────────────┘
```

---

## よくある質問（Q&A）

### Q1. テレメトリとはそもそもどういう技術？

元々は宇宙・航空分野の用語で「遠隔計測」の意味です。ロケットの飛行中の状態を地上に送り続ける仕組みがその原型です。

ソフトウェアにおけるテレメトリは「**アプリが自分の状態や行動を、外部に自動で送り続ける仕組み**」を指します。

```
Claude Code が動く     → 「セッションを開始した」
モデルを呼ぶ           → 「トークンを 500 個使った、コスト $0.01」
ファイルを書いた       → 「Python を 12 行追加した」
        ↓ ユーザーが何もしなくても自動送信
OTel Collector → Prometheus / Loki → Grafana で可視化
```

**OpenTelemetry（OTel）** は「どんなアプリからでも同じ形式でテレメトリを送れるようにした業界標準」です。特定のベンダーに縛られず、Grafana でも Datadog でも New Relic でも受け取れます。

送るデータは 3 種類あります：

| シグナル | 何を送るか | Claude Code の例 |
|---|---|---|
| **Metrics（メトリクス）** | 数値の時系列 | トークン数・コスト・LOC・セッション数 |
| **Logs（ログ）** | イベントの発生記録 | 「このツールを実行した」「API を呼んだ」 |
| **Traces（トレース）** | 処理の因果関係 | 「このプロンプト → この API コール → このツール実行」の流れ |

---

### Q2. MDM が使えない環境でも配布できる？

できます。MDM は「一番楽な方法」であり、必須ではありません。

| 方法 | 向いている規模 | 概要 |
|---|---|---|
| **MDM（Jamf / Intune）** | 大企業・管理端末が多い | 設定ファイルをプッシュ配信、ユーザー操作不要 |
| **Ansible / Chef / Puppet** | 社内インフラがある | playbook でファイルを全サーバーに配置 |
| **シェルスクリプト** | 数十人まで | `setup.sh` を README に貼って実行させる |
| **dotfiles リポジトリ** | エンジニアチーム向き | チームの dotfiles に設定を commit して clone させる |
| **手動 + README** | 少人数・個人検証 | 「このファイルをここに置いて」と案内するだけ |

**シェルスクリプト配布の例**（これを README に貼って `sh setup.sh` させるだけで完結）:

```bash
#!/bin/bash
mkdir -p "$HOME/.claude"
cat > "$HOME/.claude/managed_settings.json" <<EOF
{
  "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
  "OTEL_METRICS_EXPORTER": "otlp",
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.your-company.com:4317",
  "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative"
}
EOF
echo "設定完了。次回 claude 起動からテレメトリが有効になります。"
```

---

### Q3. DAU とは何？

**Daily Active Users（日次アクティブユーザー数）** の略です。「その日に 1 回以上使ったユーザーの数」を指します。

```
例: ライセンス契約数 20 人、ある日使ったのが 12 人
    DAU = 12、DAU 率 = 12 ÷ 20 = 60%
```

| 指標 | 意味 | 使い方 |
|---|---|---|
| **DAU** | 1 日に使ったユーザー数 | 「今日何人が使ったか」 |
| **WAU** | 1 週間に使ったユーザー数 | 「週次レビューの母数」 |
| **MAU** | 1 ヶ月に使ったユーザー数 | 「月次報告のアクティブ率」 |
| **DAU/MAU 率** | 月ユーザーのうち毎日使う人の割合 | 定着度の指標。40% 超が目安 |

Grafana のダッシュボードでは「**アクティブユーザー数**」パネルがこれに相当します。時間範囲を `Last 1d` にすると DAU、`Last 7d` にすると WAU 相当の数が得られます。

---

## 2. 環境構築（インフラ側）

### 2-1. OTel Collector + Grafana の構築

**ローカル検証（このリポジトリの構成）**:
```bash
# Colima 起動（初回のみ）
colima start --cpu 2 --memory 4

# LGTM スタック起動
cd /path/to/otel
docker compose up -d

# 動作確認
open http://localhost:3000  # admin / admin
```

**本番展開（推奨構成）**:
- Grafana Cloud の無料枠（個人〜小チーム）または有料プランで Collector + Storage を外部化
- 社内 Kubernetes なら `grafana/alloy`（OTel Collector 後継）+ `mimir` + `loki` + `tempo` を Helm で展開
- **必須設定**: TLS + Bearer Token（または mTLS）でエンドポイントを保護

### 2-2. チーム識別の設計（展開前に必ず決める）

`OTEL_RESOURCE_ATTRIBUTES` でチーム情報を注入する。以下を管理台帳で管理する:

| 属性キー | 例 | 用途 |
|---|---|---|
| `department` | `engineering` / `product` / `design` | 部署別集計 |
| `team.id` | `platform` / `frontend` / `mobile` | チーム別集計 |
| `cost_center` | `eng-001` / `biz-002` | コスト配賦 |
| `location` | `tokyo` / `osaka` / `remote` | 拠点別集計 |

---

## 3. クライアントへのインストール手順

### 3-1. Claude Code CLI のインストール

```bash
# Node.js 18+ が必要
npm install -g @anthropic-ai/claude-code

# 動作確認
claude --version
```

### 3-2. テレメトリ設定の配布（managed_settings.json）

**MDM（Jamf / Intune）または構成管理（Ansible / Chef）で全端末に配布する。**

配布ファイルのパス:
- macOS: `/Library/Application Support/ClaudeCode/managed_settings.json`
- Linux: `/etc/claude/managed_settings.json`

**managed_settings.json の内容（チームごとに `team.id` だけ変える）**:

```json
{
  "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
  "OTEL_METRICS_EXPORTER": "otlp",
  "OTEL_LOGS_EXPORTER": "otlp",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.internal.your-company.com:4317",
  "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer YOUR_TOKEN",
  "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative",
  "OTEL_METRIC_EXPORT_INTERVAL": "60000",
  "OTEL_LOGS_EXPORT_INTERVAL": "5000",
  "OTEL_METRICS_INCLUDE_VERSION": "true",
  "OTEL_METRICS_INCLUDE_ENTRYPOINT": "true",
  "OTEL_RESOURCE_ATTRIBUTES": "department=engineering,team.id=platform,cost_center=eng-001"
}
```

> **ポイント**: managed_settings はユーザーが上書きできない。`OTEL_LOG_USER_PROMPTS` や `OTEL_LOG_TOOL_DETAILS` は **managed_settings には入れない**（プロンプト・コマンド内容が漏れる）。

### 3-3. インストール確認コマンド（メンバー向け）

```bash
# テレメトリが出ているか console で即確認（10秒で結果が出る）
CLAUDE_CODE_ENABLE_TELEMETRY=1 OTEL_METRICS_EXPORTER=console \
  OTEL_METRIC_EXPORT_INTERVAL=5000 \
  claude -p "hi" --model haiku </dev/null

# → "claude_code.session.count" などが表示されれば OK
```

### 3-4. 展開チェックリスト

```
□ managed_settings.json を全端末に配布済み
□ エンドポイント (4317/4318) にファイアウォール穴を開けた
□ 各メンバーが claude auth login 済み（user.email の自動付与に必要）
□ Grafana で user_email ラベルが確認できている
□ プライバシーポリシーと利用規約をメンバーに周知した
```

---

## 4. ダッシュボードの確認方法

### 4-1. アクセス

```
http://localhost:3000  （ローカル検証環境）
https://grafana.internal.your-company.com  （本番）
```

- ログイン: admin / admin（初回、必ず変更する）
- ダッシュボード一覧から `Claude Code Productivity v2` を開く
- 右上の時間範囲を確認（週次レビューは `Last 7 days` 推奨）

### 4-2. 変数フィルタの使い方

| 変数 | 使い方 |
|---|---|
| **User** | 特定メンバーに絞る / All で全体確認 |
| **Model** | モデル別コスト比較（Opus vs Sonnet vs Haiku） |

### 4-3. どの指標がダッシュボードのどこで見られるか

> **ここを見ればいい** — 5章以降の指標とダッシュボードパネルの対応表。

ダッシュボード URL: `http://localhost:3000/d/claude-code-productivity-v2`

| 章 | 指標 | ダッシュボードパネル | 場所（行） |
|---|---|---|---|
| **5-1 採用度** | アクティブユーザー数（DAU相当） | 👥 アクティブユーザー数 | 最上段・左 |
| **5-1 採用度** | resume率（会話継続率）全体 | 🔄 resume率 | 最上段・左2番目 |
| **5-1 採用度** | resume率 ユーザー別ランキング | 🔄 resume率ランキング | 上から2段目・左 |
| **5-2 活動量** | 週次コスト合計 | 累計コスト (USD) stat | 上から3段目 |
| **5-2 活動量** | アクティブ時間 | アクティブ時間 stat | 上から3段目 |
| **5-2 活動量** | モデル別コスト比率（Opus使いすぎ確認） | 📊 モデル別コスト内訳 | 最上段・右側 |
| **5-3 成果** | LOC 追加行数 ランキング | 📝 LOCランキング | ランキング行 |
| **5-3 成果** | commit 数 / PR 数 | git commit stat / PR stat | 上から3段目 |
| **5-3 成果** | コスト効率 LOC/USD | コスト効率: LOC/USD | 下段 |
| **5-4 健全性** | ツール拒否率 ユーザー別 | ユーザー別 ツール拒否率 | 下段 |
| **5-4 健全性** | API エラー発生数 | ⚠️ APIエラー発生数 | 最上段・右端 |
| **5-4 健全性** | cacheRead 活用率 | 🧮 cacheRead率ランキング | 上から2段目・右 |
| **6章 生産性高い人** | cacheRead率 70%超 | 🧮 cacheRead率ランキング | 上から2段目・右 |
| **6章 生産性高い人** | resume率 30%超 | 🔄 resume率ランキング | 上から2段目・左 |
| **6章 生産性高い人** | LOC/USD 高い | コスト効率: LOC/USD | 下段 |
| **6章 生産性高い人** | 拒否率 10%以下 | ユーザー別 ツール拒否率 | 下段 |
| **7章 ボトルネック** | 高コスト×低LOC（パターン1） | コスト効率: LOC/USD の低い人 | 下段 |
| **7章 ボトルネック** | cacheRead率低い（パターン2） | 🧮 cacheRead率ランキング の低い人 | 上から2段目・右 |
| **7章 ボトルネック** | Opus使いすぎ（パターン3） | 📊 モデル別コスト内訳 | 最上段・右側 |
| **7章 ボトルネック** | 拒否率高い（パターン4） | ユーザー別 ツール拒否率 の高い人 | 下段 |
| *(参考)* | 使用言語の分布 | ユーザー別 使用言語分布 | 下段 |
| *(参考)* | イベント生ログ | イベントログ (Loki) | 最下段 |

**ダッシュボードで見られないもの**（Grafana Explore で直接クエリが必要）:

| 指標 | Explore のクエリ例 |
|---|---|
| DAU の日次推移グラフ | `count(count by (user_email) (increase(claude_code_session_count_total[1d])))` |
| compaction 頻度 | Loki: `{service_name="claude-code", event_name="compaction"}` |
| API リトライ枯渇ログ | Loki: `{service_name="claude-code", event_name="api_retries_exhausted"}` |
| リクエスト単位のトレース | Tempo（要 `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`） |

---

## 5. 読み方の基準 — 何を見れば何がわかるか

### 5-1. 採用度（Adoption）— 「使われているか」

| 指標 | クエリ | 判断基準 |
|---|---|---|
| DAU | `count(count by (user_email) (claude_code_session_count_total))` | ライセンス数の **60% 以上**が DAU なら健全な採用 |
| セッション継続率 | `resume / (fresh + resume + continue)` | 30% 以上なら「会話を引き継いで使えている」 |
| 新規 vs リピート | 週次 fresh セッション数の増減 | 右肩上がりなら浸透中 |

**アクション**: DAU 率が低い場合はオンボーディング研修か、ユースケースの提示が必要。

---

### 5-2. 活動量（Activity）— 「どれくらい使っているか」

| 指標 | クエリ | 目安 |
|---|---|---|
| 週次コスト/人 | `sum by (user_email) (claude_code_cost_usage_USD_total)` | $2〜$10/週 が標準的なアクティブユーザー |
| active_time | `sum by (user_email) (claude_code_active_time_seconds_total)` | 1日30分以上で「日常的に活用」 |
| トークン/セッション | `sum(tokens) / sum(sessions)` | 多いほど複雑な作業を任せている |

---

### 5-3. 成果（Outcome）— 「効果が出ているか」

| 指標 | クエリ | 判断基準 |
|---|---|---|
| LOC 追加 / 週 | `sum by (user_email) (lines_of_code{type="added"})` | チーム平均の **1.5倍以上** なら AI 効果が出ている可能性 |
| commit 数 / 週 | `sum by (user_email) (commit_count_total)` | 増加トレンドが継続するか確認 |
| PR 数 | `sum by (user_email) (pull_request_count_total)` | LOC と合わせて「質の高い出力か」を判断 |
| コスト効率 (LOC/USD) | `sum(loc_added) / sum(cost_usd)` | **高いほど効率的**。チーム平均を基準に相対比較 |

> **⚠️ 落とし穴**: LOC だけで評価しない。`removed` が多いメンバーは不要コードを削除している可能性があり、むしろ**高品質な貢献**。

---

### 5-4. 健全性（Health）— 「正しく使えているか」

| 指標 | 異常サイン | 対処 |
|---|---|---|
| ツール拒否率 | **25% 超**が続く場合 | Permission 設定の見直し、または安全でない操作をしようとしている |
| API エラー率 | 急増 | ネットワーク障害 or API 制限に引っかかっている |
| compaction 頻度 | 1セッションに何度も発生 | コンテキストが大きすぎる（分割して使うべき） |
| リトライ枯渇 | 発生している | スロットリング → レート制限の調整か利用時間帯の分散 |

---

## 6. 生産性が高い人の特徴（読み解き方）

以下が重なっている人が **AI を上手に活用しているメンバー**:

```
✅ セッション数が多い & resume 率が高い（会話を引き継いでいる）
✅ cacheRead トークンの比率が高い（70%以上）→ プロンプトを再利用している
✅ LOC added/USD が高い → 少ないコストで多くのコードを出力
✅ ツール拒否率が低い（10%以下）→ 適切な Permission 範囲で使えている
✅ effort が medium〜high → 複雑な作業を任せている
✅ commit/PR が増加トレンド → 実際に成果物に繋がっている
```

---

## 7. コスト的なボトルネック（無駄打ち）の特定

### パターン 1: 高コスト × 低成果

```promql
# コストは高いが LOC が少ない人を特定
sum by (user_email) (claude_code_cost_usage_USD_total)
/
sum by (user_email) (claude_code_lines_of_code_count_total{type="added"})
```

**LOC/USD が極端に低い（100以下）場合**: 
- 試行錯誤が多すぎる（同じ質問を繰り返している）
- プロンプトが長すぎて無駄なトークンを消費している
- 成果に繋がらない会話（雑談・質問のみ）に使っている

**対処**: ベストプラクティスの共有、CLAUDE.md の整備でコンテキストを自動注入する。

---

### パターン 2: cacheRead 率が低い

```promql
# cacheRead の比率
sum by (user_email) (claude_code_token_usage_tokens_total{type="cacheRead"})
/
sum by (user_email) (claude_code_token_usage_tokens_total)
```

**50% を下回る場合**:
- 毎回新しいセッションを立ち上げている（会話を引き継いでいない）
- プロンプトの先頭部分が毎回異なる（キャッシュが効かない）

**対処**: `claude` を `resume` オプションで起動する習慣づけ、または CLAUDE.md でシステムプロンプトを固定化する。

---

### パターン 3: Opus 使いすぎ

```promql
# モデル別コスト内訳
sum by (model) (claude_code_cost_usage_USD_total)
```

**Opus がコストの 60% 超を占める場合**:
- Opus は Sonnet の約 5 倍のコスト
- 単純な質問・コード補完に Opus を使っている可能性

**対処**: `/model` でデフォルトを Sonnet に設定。Opus は「難しいアーキテクチャ設計」「複雑なバグ調査」に限定するルールをチームで共有する。

---

### パターン 4: ツール拒否率が高い特定ユーザー

```promql
sum by (user_email) (claude_code_code_edit_tool_decision_total{decision="reject"})
/
sum by (user_email) (claude_code_code_edit_tool_decision_total)
```

**25% 超が続く場合**:
- 毎回 Permission プロンプトが出て手が止まっている → 生産性ロス
- または危険な操作（本番環境への直接変更など）を試みている → セキュリティリスク

**対処**: `.claude/settings.json` で許可リストを整備する。セキュリティ観点でのレビューが必要なケースも。

---

## 8. 週次レビューの運用フロー

```
毎週月曜 AM (10分)
  ↓
Grafana を開き、時間範囲を「Last 7 days」に設定
  ↓
① ランキングパネルで全体を俯瞰
  - コスト上位 3 名は先週比でどうか
  - LOC/USD（効率）は改善しているか
  ↓
② 異常値をチェック
  - ツール拒否率 25% 超のユーザーがいるか
  - API エラーが急増した日はないか
  ↓
③ アクション決定（必要な場合のみ）
  - 困っているメンバーへの個別フォロー
  - ベストプラクティスの全体共有
  - モデル設定の変更推奨
  ↓
月次でコスト推移を経営報告（Claude 投資対効果）
```

---

## 9. プライバシーと倫理のガイドライン

### やること
- 集計はチーム単位を基本とする（個人スコアを貼り出さない）
- データの保持期間・アクセス権を事前に文書化する
- テレメトリ収集の目的・内容をメンバーに事前説明し同意を取る

### やってはいけないこと
- 個人ランキングを人事評価に直接使う（信頼崩壊 → 計測値が歪む）
- `OTEL_LOG_USER_PROMPTS=1` をデフォルトで有効にする（プロンプトに機密情報が含まれる可能性）
- 成果指標（LOC・commit数）だけで優劣をつける（内容の品質は別途評価が必要）

---

## 10. ファイル一覧

| ファイル | 役割 |
|---|---|
| `docker-compose.yml` | ローカル LGTM スタック定義 |
| `claude-otel.env` | 個人検証用 OTel 環境変数（`source` して使う） |
| `dashboard-claude-code.json` | 基本ダッシュボード（コスト・トークン・Loki ログ） |
| `dashboard-productivity-v2.json` | 生産性ダッシュボード v2（ランキング・効率指標） |
| `inject-sample-users.py` | サンプルユーザーデータの注入スクリプト |
| `docs/otel-grafana-data-reference.md` | OTel / Grafana データリファレンス |
| `docs/productivity-monitoring-proposal.md` | 生産性計測の提案（4層フレーム・ロードマップ） |
| `docs/org-ai-adoption-plan.md` | 本ドキュメント（組織展開の運用ガイド） |

---

## 11. トラブルシューティング早見表

| 症状 | 確認コマンド | 対処 |
|---|---|---|
| Grafana にメトリクスが出ない | `otelcol_receiver_accepted_metric_points_total` を確認 | コレクタが受信していれば temporality が原因 → `cumulative` を設定 |
| コレクタに届かない | `nc -z -w3 <endpoint> 4317` | ファイアウォール / TLS 証明書を確認 |
| user_email ラベルがない | メトリクスの series を確認 | `claude auth login` を済ませる |
| セッションデータが来ない | `console` エクスポータで手元確認 | `CLAUDE_CODE_ENABLE_TELEMETRY=1` が managed_settings で設定されているか確認 |
| `claude -p` が止まる | stderr を確認 | `</dev/null` を付けて stdin を明示的に閉じる |

---

*参考: `otel-grafana-data-reference.md` / `productivity-monitoring-proposal.md`*
