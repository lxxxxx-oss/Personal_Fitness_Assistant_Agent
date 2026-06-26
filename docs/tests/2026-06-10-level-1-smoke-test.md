# Level 1: 全端点冒烟测试报告

**日期**: 2026-06-10
**测试类型**: 手动验证 (Manual Verification)
**测试人**: Fitness Agent Builder

---

## 测试环境

| 项目 | 值 |
|------|-----|
| 服务地址 | `http://127.0.0.1:8000` |
| LLM 模型 | Qwen3-0.6B (CPU) |
| 模型路径 | `D:/Users/Agent/model/models/Qwen/Qwen3-0___6B` |

---

## 测试结果总览

| # | 端点 | 方法 | 结果 | 详情 |
|---|------|------|------|------|
| 1 | `/health` | GET | ✅ PASS | `{"status": "ok", "version": "0.1.0"}` |
| 2 | `/chat` → chat 意图 | POST | ✅ PASS | intent=chat, reply=432字符 |
| 3 | `/chat` → diet 意图 | POST | ✅ PASS | intent=diet, reply=3935字符 |
| 4 | `/chat` → motion 意图 | POST | ❌ FAIL | **500: `'ToolResult' object has no attribute 'keys'`** |
| 5 | `/chat` → search 意图 | POST | ✅ PASS | intent=search, reply=473字符 |
| 6 | `/chat` → mcp 意图 | POST | ✅ PASS | intent=mcp, reply=854字符 |
| 7 | `/chat/{id}/history` | GET | ✅ PASS | 返回空历史列表 |
| 8 | `/chat/{id}/history` | DELETE | ✅ PASS | `{"status": "cleared"}` |
| 9 | 空消息校验 | POST | ✅ PASS | 返回 422 |
| 10 | 空 user_id 校验 | POST | ✅ PASS | 返回 422 |
| 11 | `/chat/stream` (SSE) | POST | ❌ FAIL | **`IncompleteRead` — 流式输出中途断开** |

**通过率: 9/11 (81.8%)**

---

## 发现的 Bug

### Bug 1: Motion 子图 — `'ToolResult' object has no attribute 'keys'`

- **严重程度**: 高（导致 motion 意图完全不可用）
- **现象**: 发送运动分析相关消息（如"分析一下我的深蹲姿势"）时，服务端返回 HTTP 500
- **错误信息**: `'ToolResult' object has no attribute 'keys'`
- **根因分析**: motion 子图中某处将 `ToolResult` 对象当作 `dict` 使用，调用了 `.keys()` 方法。应使用 `ToolResult` 的属性访问方式
- **涉及文件**: 大概率是 `app/graph/subgraphs/motion.py`

### Bug 2: SSE 流式端点 — `IncompleteRead`

- **严重程度**: 中（影响流式体验，非流式 `/chat` 正常）
- **现象**: 调用 `/chat/stream` 后，服务端在流式输出过程中提前关闭连接
- **错误信息**: `http.client.IncompleteRead: IncompleteRead(0 bytes read)`
- **根因分析**: 可能是 LLM 生成过程中的异常未捕获，或流式生成器提前退出

---

## 测试输入详情

### 意图路由测试用例

| 预期意图 | 输入消息 |
|----------|----------|
| chat | 你好，介绍一下你自己 |
| diet | 减脂期间应该怎么吃？ |
| motion | 分析一下我的深蹲姿势 |
| search | 搜索最新的健身资讯 |
| mcp | 怎么做番茄炒蛋？ |

### 边界校验用例

| 测试场景 | 输入 | 预期 | 实际 |
|----------|------|------|------|
| 空消息 | `user_id="test", message=""` | 422 | 422 ✅ |
| 空 user_id | `user_id="", message="hello"` | 422 | 422 ✅ |

---

## 测试脚本

测试脚本保存在: `tests/manual_smoke.py`
