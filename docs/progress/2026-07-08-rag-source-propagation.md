# RAG 来源透传闭环

## 问题

Retriever 已返回 `source`，但 Chat 只把 content 放进 `[RefN]`，Diet 甚至没有编号证据块；两者都没有写入 RouterState `_sources`。因此回答可能引用 `[Ref1]`，API 和客户端却无法看到对应知识文件。

## 修复

- 新增共享 `build_rag_context()`，统一生成编号证据块和去重来源列表。
- 证据格式包含 `[RefN]`、来源标识和内容。
- Chat 与 Diet 将来源列表写入 `_sources`，沿 HTTP、SSE、WebSocket 和多意图合成链路透传。
- Search 继续返回来源 URL；本地 RAG 当前返回知识文件名。

## Tool Spec 检查

- 职责：只格式化已召回证据和来源，不执行检索或生成。
- 输入：可迭代的结构化检索结果，读取 `content` 与可选 `source`。
- 输出：稳定的 `(context_text, sources)`；空内容跳过，来源稳定去重。
- 权限：纯内存转换，不访问文件、网络或凭据。
- 错误：缺 source 显示“未标注来源”但不伪造公共 source；缺 content 的记录安全跳过。

## 边界

本次完成“回答证据编号对应哪个来源”的元数据闭环，不验证模型每句话是否忠实引用，也不代表知识文件本身已经过医学或营养学质量审核。
