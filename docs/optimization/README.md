# Optimization 优化路线入口

本目录只放“后续优化怎么设计、按什么顺序落地、当前做到哪里”的文档。它不是面试背诵目录，但可以支撑你回答“为什么这样演进、边界是什么、下一步怎么做”。

## 阅读顺序

| 顺序 | 文档 | 作用 |
|---:|---|---|
| 1 | [IMPLEMENTATION_SEQUENCE.md](./IMPLEMENTATION_SEQUENCE.md) | 总路线：Context Compression 与 Memory System 的落地顺序和当前进度 |
| 2 | [memory-system.md](./memory-system.md) | 记忆系统设计：SQLite source of truth、长期记忆、候选确认、Milvus 增强 |
| 3 | [context-compression.md](./context-compression.md) | 上下文压缩设计：Prompt Builder、结构化状态、compact、预算控制 |

## 当前重点口径

上下文压缩和记忆系统不是两个孤立功能，而是一套 Agent Memory & Context Engineering 闭环：

- 短期对话：用 SlidingWindow 保留最近上下文。
- 压缩摘要：长上下文超过阈值时触发 compact，防止 prompt 膨胀。
- 长期记忆：用户偏好、目标、饮食/健康约束进入 SQLite。
- 敏感治理：伤病、过敏等健康信息先进入 candidate 确认。
- 召回增强：FTS5/LIKE 做基础检索，Milvus 做可选语义召回。
- 注入控制：按 Prompt 预算注入高价值记忆和 RAG evidence。
- 评测闭环：用 Memory + Context + RAG benchmark 验证链路稳定性。

## 面试时怎么用

如果被问“为什么要做记忆和上下文压缩”，不要只说“为了记住用户”。更好的回答是：

> 长对话 Agent 的问题不是单纯上下文不够，而是历史越长噪声越多、用户偏好容易丢、敏感信息可能被误写、Prompt 成本和长度也不可控。所以我把短期工作上下文、压缩摘要和长期记忆拆开管理，再通过检索、预算注入和 benchmark 验证它们组合起来是稳定的。
