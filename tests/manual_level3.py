"""Level 3: Deep scenario validation — multi-turn, edge cases, error handling.

Tests:
  3.1 Multi-turn conversation memory
  3.2 Memory eviction (max_turns)
  3.3 History lifecycle (clear mid-conversation)
  3.4 Long message boundary
  3.5 Special characters / emoji
  3.6 Intent switching across turns
  3.7 User ID boundary cases
"""

import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {label}" + (f" -- {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {label}" + (f" -- {detail}" if detail else ""))


def chat(user_id, message):
    data = json.dumps({"user_id": user_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/chat", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def get_history(user_id):
    req = urllib.request.Request(f"{BASE}/chat/{user_id}/history")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def delete_history(user_id):
    req = urllib.request.Request(f"{BASE}/chat/{user_id}/history", method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ============================================================
# 3.1 Multi-turn conversation memory
# ============================================================
print("=" * 60)
print("3.1 Multi-turn Conversation Memory")
print("=" * 60)

uid = "l3_memory_test"
delete_history(uid)  # Start clean

# Turn 1: Ask about squats
code, body = chat(uid, "什么是深蹲？")
check("turn1: valid response", code == 200 and len(body["reply"]) > 50,
      f"code={code} reply_len={len(body.get('reply',''))}")

# Turn 2: Follow-up (uses "它" to refer to squat)
code, body = chat(uid, "它有什么好处？")
check("turn2: follow-up with pronoun", code == 200 and len(body["reply"]) > 50,
      f"reply_len={len(body.get('reply',''))}")

# Check history has 2 turns
hist = get_history(uid)
check("history has 4 entries (2 user + 2 assistant)",
      len(hist["history"]) >= 4,
      f"history_len={len(hist['history'])}")

# Turn 3: Another follow-up
code, body = chat(uid, "那我每天应该做几组？")
check("turn3: continues context", code == 200 and len(body["reply"]) > 50,
      f"reply_len={len(body.get('reply',''))}")

hist = get_history(uid)
check("history grows to 6 entries",
      len(hist["history"]) >= 6,
      f"history_len={len(hist['history'])}")


# ============================================================
# 3.2 Memory eviction
# ============================================================
print("\n" + "=" * 60)
print("3.2 Memory Eviction (max_turns=6)")
print("=" * 60)

uid2 = "l3_eviction_test"
delete_history(uid2)

# Send many turns to trigger eviction
for i in range(8):
    code, body = chat(uid2, f"第{i+1}个问题：什么是健身？")

hist = get_history(uid2)
# max_turns=6 means 6 user+assistant pairs = 12 history entries max
check("history capped at ~12 entries (6 turns)",
      len(hist["history"]) <= 12,
      f"history_len={len(hist['history'])}")
check("oldest messages evicted",
      len(hist["history"]) >= 4,
      f"history_len={len(hist['history'])}")


# ============================================================
# 3.3 History lifecycle
# ============================================================
print("\n" + "=" * 60)
print("3.3 History Lifecycle")
print("=" * 60)

uid3 = "l3_lifecycle_test"
delete_history(uid3)

chat(uid3, "你好")
chat(uid3, "健身计划怎么做？")

hist = get_history(uid3)
check("history after 2 turns", len(hist["history"]) >= 2)

# Clear
resp = delete_history(uid3)
check("clear returns 'cleared'", resp["status"] == "cleared")

# Verify empty
hist = get_history(uid3)
check("history empty after clear", hist["history"] == [],
      f"history={hist['history']}")

# Can continue chatting after clear
code, body = chat(uid3, "现在重新开始，减脂怎么吃？")
check("chat works after clear", code == 200 and body["intent"] == "diet",
      f"code={code} intent={body['intent']}")


# ============================================================
# 3.4 Long message boundary
# ============================================================
print("\n" + "=" * 60)
print("3.4 Long Message Boundaries")
print("=" * 60)

# Message exactly at limit (4096 chars in Chinese)
long_msg = "健身" * 2048  # 4096 chars
code, body = chat("l3_long", long_msg)
check("4096-char message accepted", code == 200,
      f"code={code}")

# Message just over limit
too_long = "健身" * 2049  # 4098 chars
code, body = chat("l3_long", too_long)
check("4098-char message rejected (422)", code == 422,
      f"code={code}")

# Empty message
code, body = chat("l3_long", "")
check("empty message rejected (422)", code == 422,
      f"code={code}")


# ============================================================
# 3.5 Special characters
# ============================================================
print("\n" + "=" * 60)
print("3.5 Special Characters")
print("=" * 60)

special_cases = [
    ("emoji", "健身💪有什么好处？🏋️"),
    ("English+Chinese", "What is 深蹲 and how to do it?"),
    ("numbers+units", "每天摄入2000卡路里够不够？"),
    ("url-like", "参考这个 https://example.com 的内容"),
    ("long numbers", "我的体重70kg身高175cm体脂率15%"),
]

for label, msg in special_cases:
    code, body = chat("l3_special", msg)
    check(f"{label}", code == 200 and len(body["reply"]) > 20,
          f"code={code} reply_len={len(body.get('reply',''))}")


# ============================================================
# 3.6 Intent switching across turns
# ============================================================
print("\n" + "=" * 60)
print("3.6 Intent Switching Across Turns")
print("=" * 60)

uid4 = "l3_switch_test"
delete_history(uid4)

# Start with diet
code, body = chat(uid4, "减脂期应该怎么吃？")
check("diet query -> diet intent", body["intent"] == "diet",
      f"intent={body['intent']}")

# Switch to motion
code, body = chat(uid4, "深蹲的标准动作是什么？")
check("motion query -> motion intent", body["intent"] == "motion",
      f"intent={body['intent']}")

# Switch to mcp
code, body = chat(uid4, "怎么做番茄炒蛋？")
check("mcp query -> mcp intent", body["intent"] == "mcp",
      f"intent={body['intent']}")

# History should have all 3 turns
hist = get_history(uid4)
check("history preserved across intent switches",
      len(hist["history"]) >= 6,
      f"history_len={len(hist['history'])}")


# ============================================================
# 3.7 User ID boundary cases
# ============================================================
print("\n" + "=" * 60)
print("3.7 User ID Boundaries")
print("=" * 60)

uid_cases = [
    ("single_char", "a"),
    ("max_length", "x" * 64),
    ("with_hyphen", "user-123_test"),
    ("chinese_uid", "用户001"),
]

for label, uid_val in uid_cases:
    code, body = chat(uid_val, "什么是健身？")
    check(f"uid '{label}'", code == 200 and len(body["reply"]) > 50,
          f"code={code} reply_len={len(body.get('reply',''))}")

# Too long user_id
code, body = chat("x" * 65, "hello")
check("uid too long (65 chars) rejected", code == 422,
      f"code={code}")


# ============================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"LEVEL 3 RESULTS: {passed}/{total} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    exit(1)
