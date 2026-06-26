# Level 2: 核心链路验证报告

**日期**: 2026-06-10
**测试类型**: 手动验证 (Manual Verification)
**测试人**: Fitness Agent Builder

---

## 测试结果总览

| 模块 | 通过/总数 | 通过率 |
|------|-----------|--------|
| 意图路由鲁棒性 | 16/16 | 100% |
| SSE 流式深度测试 | 2/2 | 100% |
| WebSocket 流式测试 | 1/1 | 100% |
| **总计** | **19/19** | **100%** |

---

## 2.1 意图路由鲁棒性

每个意图用 3-4 种不同措辞验证路由稳定性：

### chat 意图 (3/3)
| 输入 | 预期 | 实际 | 结果 |
|------|------|------|------|
| 你好呀 | chat | chat | ✅ |
| 今天心情不错 | chat | chat | ✅ |
| 什么是健身？ | chat | chat | ✅ |

### diet 意图 (3/3)
| 输入 | 预期 | 实际 | 结果 |
|------|------|------|------|
| 减脂期间应该怎么吃？ | diet | diet | ✅ |
| 健身完吃什么补充蛋白质？ | diet | diet | ✅ |
| 增肌每天需要多少热量？ | diet | diet | ✅ |

### motion 意图 (3/3)
| 输入 | 预期 | 实际 | 结果 |
|------|------|------|------|
| 分析一下我的深蹲姿势 | motion | motion | ✅ |
| 我的硬拉动作标准吗？ | motion | motion | ✅ |
| 帮我看看卧推的姿势对不对 | motion | motion | ✅ |

### search 意图 (3/3)
| 输入 | 预期 | 实际 | 结果 |
|------|------|------|------|
| 搜索最新的健身资讯 | search | search | ✅ |
| 查一下蛋白粉推荐 | search | search | ✅ |
| 最近有什么健身活动？ | search | search | ✅ |

### mcp 意图 (4/4)
| 输入 | 预期 | 实际 | 结果 |
|------|------|------|------|
| 怎么做番茄炒蛋？ | mcp | mcp | ✅ |
| 菜谱：红烧排骨的做法 | mcp | mcp | ✅ |
| 告诉我水煮鱼的做法步骤 | mcp | mcp | ✅ |
| 怎么做深蹲？ | mcp | mcp | ✅ |

---

## 2.2 SSE 流式深度测试

| 意图 | 消息 | meta | data 事件数 | done | 结果 |
|------|------|------|------------|------|------|
| chat | 介绍一下健身的好处 | ✅ | 473 | ✅ | ✅ |
| diet | 减脂期早餐吃什么？ | ✅ | 626 | ✅ | ✅ |

---

## 2.3 WebSocket 流式测试

| 意图 | 消息 | meta | token 数 | done | 结果 |
|------|------|------|----------|------|------|
| chat | 你好 | ✅ 1 | 237 | ✅ 1 | ✅ |

---

## 本次修复的问题

### Fix 1: `_prompt` 未保存到 LangGraph 状态
- **根因**: `RouterState` TypedDict 未包含 `_prompt` 字段，LangGraph 在 `graph.invoke()` 时将其过滤
- **修复**: 在 `RouterState` 中添加 `_prompt: str` 字段
- **影响**: SSE 和 WebSocket 流式端点现在能正常获取 prompt 并进行流式生成

### Fix 2: Keyword 路由覆盖不全
- **问题 A**: `"最近有什么健身活动？"` 未被路由到 search（缺少"最近"关键词）
- **修复 A**: 在 search 关键词列表添加 `"最近"`
- **问题 B**: `"怎么做深蹲？"` 路由到 motion 而非 mcp（`"深蹲"` 比 `"怎么做"` 先匹配）
- **修复 B**: 调整 KEYWORD_MAP 顺序 — mcp 放在 motion 前面（`"怎么做"` 前缀比单个动作名更具体）

### Fix 3: WebSocket 同步 LLM 生成阻塞事件循环
- **问题**: `generate_stream()` 是同步生成器，在异步上下文中阻塞事件循环，导致 WebSocket keepalive ping 超时断开
- **修复**: 使用 `asyncio.to_thread()` 将同步生成卸载到线程池

---

## 代码变更

| 文件 | 变更 |
|------|------|
| `app/graph/state.py` | 添加 `_prompt: str` 字段到 RouterState |
| `app/graph/router.py` | keyword 顺序调整 + 添加 `"最近"` 到 search |
| `app/main.py` | WebSocket 使用 `asyncio.to_thread()` 避免阻塞 |
