"""
複数ユーザーのサンプルテレメトリを OTLP HTTP で注入するスクリプト。
Prometheus に user_email 別のメトリクス series を作成する。
"""
import json, time, urllib.request, uuid, random

OTLP_ENDPOINT = "http://localhost:4318/v1/metrics"

# サンプルユーザー定義（現実感のある格差をつける）
USERS = [
    {
        "email": "alice@team.example.com",
        "name": "Alice",
        "profile": "heavy_user",
        "sessions": 48,
        "tokens_input": 280000,
        "tokens_output": 42000,
        "tokens_cache_read": 1800000,
        "cost_usd": 3.45,
        "loc_added": 2840,
        "loc_removed": 610,
        "commits": 23,
        "prs": 8,
        "tool_accept": 312,
        "tool_reject": 4,
        "active_s": 7200,
        "languages": {"Python": 18, "TypeScript": 9, "Go": 5},
    },
    {
        "email": "bob@team.example.com",
        "name": "Bob",
        "profile": "mid_user",
        "sessions": 31,
        "tokens_input": 155000,
        "tokens_output": 28000,
        "tokens_cache_read": 920000,
        "cost_usd": 1.87,
        "loc_added": 1540,
        "loc_removed": 380,
        "commits": 14,
        "prs": 5,
        "tool_accept": 198,
        "tool_reject": 11,
        "active_s": 4800,
        "languages": {"TypeScript": 14, "Python": 6},
    },
    {
        "email": "carol@team.example.com",
        "name": "Carol",
        "profile": "mid_user",
        "sessions": 22,
        "tokens_input": 98000,
        "tokens_output": 19000,
        "tokens_cache_read": 540000,
        "cost_usd": 1.12,
        "loc_added": 890,
        "loc_removed": 220,
        "commits": 9,
        "prs": 3,
        "tool_accept": 145,
        "tool_reject": 7,
        "active_s": 3200,
        "languages": {"Go": 11, "Python": 4, "Rust": 2},
    },
    {
        "email": "dave@team.example.com",
        "name": "Dave",
        "profile": "light_user",
        "sessions": 12,
        "tokens_input": 45000,
        "tokens_output": 9500,
        "tokens_cache_read": 210000,
        "cost_usd": 0.54,
        "loc_added": 380,
        "loc_removed": 90,
        "commits": 4,
        "prs": 1,
        "tool_accept": 62,
        "tool_reject": 18,
        "active_s": 1400,
        "languages": {"TypeScript": 8, "JavaScript": 3},
    },
    {
        "email": "eve@team.example.com",
        "name": "Eve",
        "profile": "new_user",
        "sessions": 5,
        "tokens_input": 18000,
        "tokens_output": 4200,
        "tokens_cache_read": 72000,
        "cost_usd": 0.21,
        "loc_added": 120,
        "loc_removed": 35,
        "commits": 1,
        "prs": 0,
        "tool_accept": 22,
        "tool_reject": 9,
        "active_s": 540,
        "languages": {"Python": 5},
    },
]

MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]


def make_attrs(*pairs):
    return [{"key": k, "value": {"stringValue": str(v)}} for k, v in pairs]


def resource_for(user, session_id):
    return {
        "attributes": make_attrs(
            ("service.name", "claude-code"),
            ("service.version", "2.1.177"),
            ("user.email", user["email"]),
            ("user.id", uuid.uuid5(uuid.NAMESPACE_DNS, user["email"]).hex),
            ("user.account_uuid", uuid.uuid5(uuid.NAMESPACE_OID, user["email"]).hex),
            ("user.account_id", f"user_{uuid.uuid5(uuid.NAMESPACE_URL, user['email']).hex[:20]}"),
            ("organization.id", "da93c5ae-2e09-4767-80c9-a1fef7cfe61c"),
            ("session.id", session_id),
            ("terminal.type", random.choice(["iTerm.app", "vscode", "Apple_Terminal"])),
        )
    }


def sum_metric(name, unit, points, is_monotonic=True):
    return {
        "name": name,
        "unit": unit,
        "sum": {
            "aggregationTemporality": 2,  # CUMULATIVE
            "isMonotonic": is_monotonic,
            "dataPoints": points,
        },
    }


def datapoint(attrs_pairs, value, start_ns, now_ns, user_attrs=None):
    """user_attrs を渡すと user_email 等をdatapoint attributeに付与する（Prometheusラベル化に必要）"""
    all_attrs = list(attrs_pairs)
    if user_attrs:
        all_attrs.extend(user_attrs)
    return {
        "attributes": make_attrs(*all_attrs),
        "startTimeUnixNano": str(start_ns),
        "timeUnixNano": str(now_ns),
        "asDouble": float(value),
    }


def post(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        OTLP_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode()


def inject_user(user):
    now_ns = int(time.time() * 1e9)
    start_ns = now_ns - int(7 * 24 * 3600 * 1e9)  # 7日前を開始時刻に
    model = random.choice(MODELS)
    session_id = str(uuid.uuid4())

    # Prometheusラベルに昇格させたいユーザー識別属性（datapoint attributes に付ける）
    ua = uuid.uuid5(uuid.NAMESPACE_OID, user["email"]).hex
    uid = uuid.uuid5(uuid.NAMESPACE_DNS, user["email"]).hex
    u_attrs = [
        ("user_email",        user["email"]),
        ("user_account_uuid", ua),
        ("user_account_id",   f"user_{uid[:20]}"),
        ("user_id",           uid),
        ("organization_id",   "da93c5ae-2e09-4767-80c9-a1fef7cfe61c"),
        ("session_id",        session_id),
        ("terminal_type",     random.choice(["iTerm.app", "vscode", "Apple_Terminal"])),
    ]

    metrics = [
        # session.count
        sum_metric("claude_code.session.count", "count", [
            datapoint([("start_type", "fresh")],    user["sessions"] * 0.7, start_ns, now_ns, u_attrs),
            datapoint([("start_type", "resume")],   user["sessions"] * 0.2, start_ns, now_ns, u_attrs),
            datapoint([("start_type", "continue")], user["sessions"] * 0.1, start_ns, now_ns, u_attrs),
        ]),
        # token.usage
        sum_metric("claude_code.token.usage", "tokens", [
            datapoint([("type", "input"),         ("model", model)], user["tokens_input"],            start_ns, now_ns, u_attrs),
            datapoint([("type", "output"),        ("model", model)], user["tokens_output"],           start_ns, now_ns, u_attrs),
            datapoint([("type", "cacheRead"),     ("model", model)], user["tokens_cache_read"],       start_ns, now_ns, u_attrs),
            datapoint([("type", "cacheCreation"), ("model", model)], int(user["tokens_input"]*0.05),  start_ns, now_ns, u_attrs),
        ]),
        # cost.usage
        sum_metric("claude_code.cost.usage", "USD", [
            datapoint([("model", model)], user["cost_usd"], start_ns, now_ns, u_attrs),
        ]),
        # active_time.total
        sum_metric("claude_code.active_time.total", "s", [
            datapoint([], user["active_s"], start_ns, now_ns, u_attrs),
        ]),
        # lines_of_code.count
        sum_metric("claude_code.lines_of_code.count", "count", [
            datapoint([("type", "added"),   ("model", model)], user["loc_added"],   start_ns, now_ns, u_attrs),
            datapoint([("type", "removed"), ("model", model)], user["loc_removed"], start_ns, now_ns, u_attrs),
        ]),
        # commit.count
        sum_metric("claude_code.commit.count", "count", [
            datapoint([], user["commits"], start_ns, now_ns, u_attrs),
        ]),
        # pull_request.count
        sum_metric("claude_code.pull_request.count", "count", [
            datapoint([], user["prs"], start_ns, now_ns, u_attrs),
        ]),
    ]

    # code_edit_tool.decision (言語別)
    edit_points = [
        datapoint([("decision", "accept"), ("tool_name", "Write"), ("language", lang)], cnt, start_ns, now_ns, u_attrs)
        for lang, cnt in user["languages"].items()
    ] + [
        datapoint([("decision", "reject"), ("tool_name", "Write"), ("language", "")], user["tool_reject"], start_ns, now_ns, u_attrs),
    ]
    metrics.append(sum_metric("claude_code.code_edit_tool.decision", "count", edit_points))

    payload = {
        "resourceMetrics": [{
            "resource": resource_for(user, session_id),
            "scopeMetrics": [{"metrics": metrics}],
        }]
    }

    status, body = post(payload)
    ok = "OK" if status == 200 else "FAIL"
    print(f"  [{ok} {status}] {user['name']:6} ({user['email']}) — sessions={user['sessions']} cost=${user['cost_usd']:.2f} loc_added={user['loc_added']}")


print("=== injecting sample users ===")
for u in USERS:
    inject_user(u)

print("\nDone. Wait ~15s for Prometheus scrape then check dashboard.")
