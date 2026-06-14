"""
Codex CLI のサンプルテレメトリを OTLP HTTP で注入するスクリプト。
Codex が実際に emit するメトリクス名・属性に合わせた構成。

Codex 実メトリクス:
  codex.turn.token_usage      (histogram → sum として注入)
  codex.api_request           (counter)
  codex.tool.call             (counter, by tool/success)
  codex.turn.e2e_duration_ms  (histogram → sum として注入)
"""
import json, time, urllib.request, uuid, random

OTLP_ENDPOINT = "http://localhost:4318/v1/metrics"

# Claude Code と同じユーザー + Codex 固有の利用パターン
# （Codex は対話型よりもバッチ実行が多い想定でやや少なめ）
USERS = [
    {
        "email": "alice@team.example.com",
        "tokens_input": 95000,  "tokens_output": 18000,
        "api_requests": 38,     "e2e_duration_ms": 124000,
        "tool_calls": {"shell": 42, "apply_patch": 31, "read_file": 68},
        "tool_failures": 5,
    },
    {
        "email": "bob@team.example.com",
        "tokens_input": 61000,  "tokens_output": 11000,
        "api_requests": 24,     "e2e_duration_ms": 78000,
        "tool_calls": {"shell": 28, "apply_patch": 19, "read_file": 44},
        "tool_failures": 8,
    },
    {
        "email": "carol@team.example.com",
        "tokens_input": 44000,  "tokens_output": 8500,
        "api_requests": 17,     "e2e_duration_ms": 53000,
        "tool_calls": {"shell": 21, "apply_patch": 14, "read_file": 33},
        "tool_failures": 3,
    },
    {
        "email": "dave@team.example.com",
        "tokens_input": 18000,  "tokens_output": 3800,
        "api_requests": 8,      "e2e_duration_ms": 24000,
        "tool_calls": {"shell": 9, "apply_patch": 6, "read_file": 15},
        "tool_failures": 4,
    },
    {
        "email": "eve@team.example.com",
        "tokens_input": 7200,   "tokens_output": 1600,
        "api_requests": 3,      "e2e_duration_ms": 9000,
        "tool_calls": {"shell": 4, "apply_patch": 2, "read_file": 7},
        "tool_failures": 2,
    },
]

MODELS = ["o4-mini", "o3", "gpt-4o"]


def make_attrs(*pairs):
    return [{"key": k, "value": {"stringValue": str(v)}} for k, v in pairs]


def sum_metric(name, unit, points, is_monotonic=True):
    return {
        "name": name, "unit": unit,
        "sum": {
            "aggregationTemporality": 2,
            "isMonotonic": is_monotonic,
            "dataPoints": points,
        },
    }


def dp(extra_attrs, value, start_ns, now_ns, u_attrs):
    return {
        "attributes": make_attrs(*(list(extra_attrs) + list(u_attrs))),
        "startTimeUnixNano": str(start_ns),
        "timeUnixNano": str(now_ns),
        "asDouble": float(value),
    }


def post(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        OTLP_ENDPOINT, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def inject_user(user):
    now_ns = int(time.time() * 1e9)
    start_ns = now_ns - int(7 * 24 * 3600 * 1e9)
    model = random.choice(MODELS)
    session_id = str(uuid.uuid4())

    uid = uuid.uuid5(uuid.NAMESPACE_DNS, user["email"]).hex
    u_attrs = [
        ("user_email",   user["email"]),
        ("user_id",      uid),
        ("session_id",   session_id),
        ("app.version",  "0.1.0"),
        ("service.name", "codex"),
        ("model",        model),
        ("auth_mode",    "api_key"),
        ("session_source", "interactive"),
    ]

    # codex.turn.token_usage (input / output)
    token_points = [
        dp([("token_type", "input")],  user["tokens_input"],  start_ns, now_ns, u_attrs),
        dp([("token_type", "output")], user["tokens_output"], start_ns, now_ns, u_attrs),
    ]

    # codex.tool.call (by tool name, success/fail)
    tool_points = []
    for tool, cnt in user["tool_calls"].items():
        fail = int(user["tool_failures"] * cnt / sum(user["tool_calls"].values()))
        tool_points.append(dp([("tool", tool), ("success", "true")],  cnt - fail, start_ns, now_ns, u_attrs))
        if fail:
            tool_points.append(dp([("tool", tool), ("success", "false")], fail, start_ns, now_ns, u_attrs))

    metrics = [
        sum_metric("codex.turn.token_usage",     "tokens", token_points),
        sum_metric("codex.api_request",           "count",  [dp([], user["api_requests"],      start_ns, now_ns, u_attrs)]),
        sum_metric("codex.turn.e2e_duration_ms",  "ms",     [dp([], user["e2e_duration_ms"],   start_ns, now_ns, u_attrs)]),
        sum_metric("codex.tool.call",             "count",  tool_points),
    ]

    resource = {
        "attributes": make_attrs(
            ("service.name",    "codex"),
            ("service.version", "0.1.0"),
            ("user.email",      user["email"]),
        )
    }

    payload = {
        "resourceMetrics": [{
            "resource": resource,
            "scopeMetrics": [{"metrics": metrics}],
        }]
    }

    status = post(payload)
    total_tools = sum(user["tool_calls"].values())
    print(f"  [{'OK' if status==200 else 'FAIL'} {status}] {user['email']:35}"
          f" tokens={user['tokens_input']+user['tokens_output']:>7}"
          f" api_req={user['api_requests']:>3}"
          f" tools={total_tools:>3}")


print("=== injecting Codex sample users ===")
for u in USERS:
    inject_user(u)
print("Done.")
