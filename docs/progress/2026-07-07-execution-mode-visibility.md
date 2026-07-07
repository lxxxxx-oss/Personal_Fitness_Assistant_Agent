# 黄金演示闭环阶段 1：执行模式可见性

## 阶段目标

解决“接口成功但无法判断真实依赖还是 mock/fallback”的问题。每次对话都公开一份安全、结构化的执行轨迹，小程序直接展示本次请求实际使用的 LLM、RAG、Search、MCP 或 Motion 模式。

## 已完成内容

- 为 RouterState 增加 `_execution`，由实际执行节点记录组件、模式、降级状态和安全说明。
- `/chat`、SSE meta 和 WebSocket meta 统一返回 `execution` 数组。
- 小程序消息气泡增加执行标签：绿色表示真实路径，黄色表示 mock/fallback 或低能力降级。
- 多意图执行期间保留各子图轨迹，最终响应按顺序去重。
- 对外只公开预定义说明，不泄露 API Token、MCP 命令、模型路径或原始异常。

## 同期修复

审查运行配置时发现两个隐蔽缺陷：已设置的浮点环境变量会解析为 `None`，布尔环境变量会返回浮点数。现已恢复正确的浮点解析和严格布尔解析，并增加回归测试。这会直接保证模型温度、检索阈值、Milvus 超时及 fallback 开关按配置生效。

## 接口设计检查

- 职责：`execution` 只描述本次执行模式，不承担健康检查或调试日志职责。
- 输入：不新增客户端输入。
- 输出：四个稳定字段 `component/mode/degraded/detail`，三种协议同构。
- 权限：过滤凭据、服务命令、路径和原始错误。
- 错误处理：降级不阻断回答，通过 `degraded=true` 和安全说明显式呈现。

## 当前验证

- Python 编译检查通过。
- API、配置、Search、MCP 定向测试：`28 passed, 1 warning`。
- 全量自动化回归：`129 passed, 2 skipped, 1 warning`。
- 小程序 JavaScript 语法检查通过。

## 遗留边界

- 执行标签尚未在微信开发者工具和真机进行视觉验收。
- `/health` 仍是进程级健康检查，不等价于 Milvus、Tavily、MCP、模型和 MediaPipe 的依赖健康。
- 下一阶段接入小程序 Motion 图片上传，让最有辨识度的能力进入真实用户主流程。
