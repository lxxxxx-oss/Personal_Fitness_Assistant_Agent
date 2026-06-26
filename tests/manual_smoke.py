"""手动冒烟测试脚本 — 覆盖所有端点."""
import json
import urllib.request
import urllib.error
import sys

BASE = "http://127.0.0.1:8000"


def api(method, path, body=None):
    """发送 HTTP 请求并返回 (status, body_dict)."""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def check(label, condition, detail=""):
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status} {label}" + (f" -- {detail}" if detail else ""))


def test_health():
    print("\n=== 1. GET /health ===")
    code, body = api("GET", "/health")
    check("status=200", code == 200, str(code))
    check("body.status=='ok'", body.get("status") == "ok", str(body))


def test_chat_intents():
    print("\n=== 2. POST /chat — 5 种意图路由 ===")
    cases = [
        ("chat",   "你好，介绍一下你自己"),
        ("diet",   "减脂期间应该怎么吃？"),
        ("motion", "分析一下我的深蹲姿势"),
        ("search", "搜索最新的健身资讯"),
        ("mcp",    "怎么做番茄炒蛋？"),
    ]
    for expected_intent, message in cases:
        code, body = api("POST", "/chat", {"user_id": "smoke", "message": message})
        actual_intent = body.get("intent", "")
        has_reply = len(body.get("reply", "")) > 0
        check(
            f"intent={expected_intent}",
            code == 200 and actual_intent == expected_intent,
            f"code={code} intent={actual_intent} reply_len={len(body.get('reply',''))}"
        )


def test_history():
    print("\n=== 3. GET /chat/{uid}/history ===")
    code, body = api("GET", "/chat/smoke_history/history")
    check("status=200, history is list", code == 200 and isinstance(body.get("history"), list), str(body))

    print("\n=== 4. DELETE /chat/{uid}/history ===")
    code, body = api("DELETE", "/chat/smoke_history/history")
    check("status=200, status=='cleared'", code == 200 and body.get("status") == "cleared", str(body))


def test_validation():
    print("\n=== 5. 输入校验 ===")
    code, body = api("POST", "/chat", {"user_id": "test", "message": ""})
    check("空消息返回422", code == 422, f"code={code}")

    code, body = api("POST", "/chat", {"user_id": "", "message": "hello"})
    check("空user_id返回422", code == 422, f"code={code}")


def test_stream_sse():
    print("\n=== 6. POST /chat/stream (SSE) ===")
    import urllib.request as ur
    data = json.dumps({"user_id": "smoke", "message": "什么是深蹲？"}).encode("utf-8")
    req = ur.Request(f"{BASE}/chat/stream", data=data, headers={"Content-Type": "application/json"})
    try:
        with ur.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            has_meta = "event: meta" in raw
            has_data = "data:" in raw
            has_done = "event: done" in raw
            check("SSE包含meta事件", has_meta)
            check("SSE包含data token", has_data)
            check("SSE包含done事件", has_done)
    except Exception as e:
        check("SSE流式响应", False, str(e))


if __name__ == "__main__":
    test_health()
    test_chat_intents()
    test_history()
    test_validation()
    test_stream_sse()
    print("\n[PASS] Smoke test completed")
