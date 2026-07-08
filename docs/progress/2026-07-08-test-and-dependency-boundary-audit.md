# 测试与真实依赖边界审计

## 代码核对

- 默认 pytest 的 autouse fixture 会替换 `LLMLoader.generate/generate_stream` 和 SentenceTransformer 编码。
- 真实本地模型测试在模型文件不存在时跳过；真实 Milvus 测试只有配置 `MILVUS_TEST_URI` 后运行。
- MCP Client 请求虽然生成 UUID，但 `_send_request()` 只读取 stdout 下一行，没有响应 ID 校验；工具调用也没有依据发现结果和 inputSchema 做强制验证。
- Dockerfile 当前不安装 Motion 可选依赖，Compose 不挂载 MediaPipe task 模型。

## 文档调整

- 将自动化测试总数解释为代码与契约回归，而非真实模型、检索或外部服务质量证明。
- 将 MCP 调整为“串行协议主链路原型”，明确缺少的协议与工具治理能力。
- 在 RUNBOOK 明确容器内 Motion 当前不可用及真实依赖的单独验收方式。

## 影响

本次不修改运行行为。主要价值是避免用总测试数代替真实效果验证，也避免把 MCP 目标架构描述成已完成能力。
