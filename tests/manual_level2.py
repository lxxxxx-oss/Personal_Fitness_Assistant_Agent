"""Level 2: Core link validation — intent robustness + SSE + WebSocket.

Tests:
  1. Intent routing — each intent with 3 different phrasings
  2. Intent routing — ambiguous/edge-case inputs
  3. SSE streaming — verify complete token flow for multiple intents
  4. WebSocket — full protocol: connect → send → receive → close
"""

import json
import urllib.request
import urllib.error
import sys
import asyncio
import websockets

BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000"

pass_count = 0
fail_count = 0


def check(label, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  [PASS] {label}" + (f" -- {detail}" if detail else ""))
    else:
        fail_count += 1
        print(f"  [FAIL] {label}" + (f" -- {detail}" if detail else ""))


def api(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def test_intent_robustness():
    """Test each intent with multiple phrasings to verify routing robustness."""
    print("\n" + "=" * 60)
    print("2.1 Intent Routing Robustness")
    print("=" * 60)

    test_cases = {
        "chat": [
            "你好呀",
            "今天心情不错",
            "什么是健身？",
        ],
        "diet": [
            "减脂期间应该怎么吃？",
            "健身完吃什么补充蛋白质？",
            "增肌每天需要多少热量？",
        ],
        "motion": [
            "分析一下我的深蹲姿势",
            "我的硬拉动作标准吗？",
            "帮我看看卧推的姿势对不对",
        ],
        "search": [
            "搜索最新的健身资讯",
            "查一下蛋白粉推荐",
            "最近有什么健身活动？",
        ],
        "mcp": [
            "怎么做番茄炒蛋？",
            "菜谱：红烧排骨的做法",
            "告诉我水煮鱼的做法步骤",
        ],
    }

    for expected, messages in test_cases.items():
        print(f"\n  [{expected}] intent:")
        for msg in messages:
            code, body = api("POST", "/chat", {"user_id": "l2_robust", "message": msg})
            actual = body.get("intent", "")
            has_reply = len(body.get("reply", "")) > 50
            check(
                f"'{msg[:20]}...' -> {expected}",
                code == 200 and actual == expected and has_reply,
                f"code={code} actual={actual} reply_len={len(body.get('reply',''))}"
            )


def test_ambiguous_inputs():
    """Test inputs that could match multiple intents — verify weighted routing."""
    print("\n  [Ambiguous / edge cases]:")

    # Generic "怎么做" is weak mcp evidence; movement names should win for training questions.
    cases = [
        ("怎么做深蹲？", "motion"),    # "深蹲" is stronger motion evidence than generic "怎么做"
        ("减脂运动方案", "diet"),       # "减脂" is diet
        ("深蹲有哪些好处", "chat"),     # conceptual explanation should stay in chat
        ("", None),                    # empty should be rejected by pydantic
    ]

    for msg, expected in cases:
        if msg == "":
            code, body = api("POST", "/chat", {"user_id": "l2_edge", "message": msg})
            check(
                f"empty msg -> 422",
                code == 422,
                f"code={code}"
            )
        else:
            code, body = api("POST", "/chat", {"user_id": "l2_edge", "message": msg})
            actual = body.get("intent", "")
            check(
                f"'{msg}' -> {expected}",
                code == 200 and actual == expected,
                f"code={code} actual={actual}"
            )


def test_sse_streaming():
    """Test SSE streaming with multiple intents — verify complete flow."""
    print("\n" + "=" * 60)
    print("2.2 SSE Streaming Deep Test")
    print("=" * 60)

    test_msgs = [
        ("chat", "介绍一下健身的好处"),
        ("diet", "减脂期早餐吃什么？"),
    ]

    for expected_intent, msg in test_msgs:
        print(f"\n  [{expected_intent}] '{msg[:30]}...':")
        data = json.dumps({"user_id": "l2_sse", "message": msg}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE}/chat/stream",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw = resp.read().decode("utf-8")
                lines = raw.strip().split("\n")

                # Parse SSE
                meta_intent = None
                tokens = []
                done = False
                for line in lines:
                    if line.startswith("event: meta"):
                        continue
                    if line.startswith("data:") and "intent" in line:
                        try:
                            meta_intent = json.loads(line[5:].strip()).get("intent")
                        except:
                            pass
                    elif line.startswith("data:") and "event: done" not in line:
                        token = line[5:].strip()
                        if token and token != "{}":
                            tokens.append(token)
                    elif line.startswith("event: done"):
                        done = True

                check("meta event present", meta_intent is not None, str(meta_intent))
                check("correct intent in meta", meta_intent == expected_intent, meta_intent or "None")
                check("tokens received", len(tokens) > 5, f"token_count={len(tokens)}")
                check("done event present", done, str(done))
                # Verify tokens form coherent text
                full_text = "".join(tokens)
                check("tokens form readable text", len(full_text) > 20, f"full_text_len={len(full_text)}")
        except Exception as e:
            check("SSE complete", False, f"{type(e).__name__}: {e}")


async def _ws_test_one(expected_intent, message):
    """Run a single WebSocket test."""
    results = {"meta": None, "tokens": [], "done": False, "error": None}
    try:
        async with websockets.connect(f"{WS_BASE}/chat/ws") as ws:
            await ws.send(json.dumps({"user_id": "l2_ws", "message": message}))
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type == "meta":
                    results["meta"] = msg.get("intent")
                elif msg_type == "token":
                    results["tokens"].append(msg.get("text", ""))
                elif msg_type == "done":
                    results["done"] = True
                    break
                elif msg_type == "error":
                    results["error"] = msg.get("message", "")
                    break
    except Exception as e:
        results["error"] = f"{type(e).__name__}: {e}"
    return results


def test_websocket():
    """Full WebSocket protocol verification."""
    print("\n" + "=" * 60)
    print("2.3 WebSocket Streaming Test")
    print("=" * 60)

    async def run_tests():
        # Test 1: Normal flow
        print("\n  [chat] '介绍健身的好处':")
        r = await _ws_test_one("chat", "介绍健身的好处")
        check("meta received", r["meta"] is not None, str(r["meta"]))
        check("correct intent", r["meta"] == "chat", str(r["meta"]))
        check("tokens received", len(r["tokens"]) > 5, f"count={len(r['tokens'])}")
        check("done received", r["done"], str(r["done"]))
        full = "".join(r["tokens"])
        check("readable output", len(full) > 20, f"len={len(full)}")

        # Test 2: Diet intent via WS
        print("\n  [diet] '减脂期怎么吃？':")
        r = await _ws_test_one("diet", "减脂期怎么吃？")
        check("correct intent", r["meta"] == "diet", str(r["meta"]))
        check("tokens received", len(r["tokens"]) > 5, f"count={len(r['tokens'])}")
        check("done received", r["done"], str(r["done"]))

        # Test 3: Invalid JSON
        print("\n  [error] Invalid JSON:")
        try:
            async with websockets.connect(f"{WS_BASE}/chat/ws") as ws:
                await ws.send("not json {{{")
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                check("error response for bad JSON",
                      msg.get("type") == "error",
                      str(msg))
        except Exception as e:
            check("error response for bad JSON", False, f"{type(e).__name__}: {e}")

        # Test 4: Empty user_id and message
        print("\n  [error] Missing fields:")
        try:
            async with websockets.connect(f"{WS_BASE}/chat/ws") as ws:
                await ws.send(json.dumps({"user_id": "", "message": ""}))
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                check("error for empty fields",
                      msg.get("type") == "error",
                      str(msg))
        except Exception as e:
            check("error for empty fields", False, f"{type(e).__name__}: {e}")

    asyncio.run(run_tests())


# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("LEVEL 2: Core Link Validation")
    print("=" * 60)

    test_intent_robustness()
    test_ambiguous_inputs()
    test_sse_streaming()
    test_websocket()

    print("\n" + "=" * 60)
    total = pass_count + fail_count
    print(f"RESULTS: {pass_count}/{total} passed, {fail_count} failed")
    print("=" * 60)

    if fail_count > 0:
        sys.exit(1)
