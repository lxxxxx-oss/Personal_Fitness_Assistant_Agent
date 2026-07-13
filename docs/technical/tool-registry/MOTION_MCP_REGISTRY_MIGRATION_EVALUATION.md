# Motion/MCP ToolRegistry Migration Evaluation

本文用于回答一个后续优化问题：**Search、Knowledge/RAG 和 MCP execute 已经接入最小 ToolRegistry 后，Motion 要不要继续迁移？如果迁移，先迁移哪一部分，为什么？**

结论先行：

- **Motion 不建议一次性全量迁移**。当前 Motion 有两条链路：对话子图的 `.npz` 规划链路，以及独立 API 的图片/视频媒体分析链路。它们涉及上传文件、临时文件、MediaPipe 模型、`PoseSequence`、标准动作库和 NumPy 数组，不适合像 Search/RAG 一样直接替换为一个简单工具调用。
- **MCP execute 已完成接入**。MCP 子图的 `execute_tool_node` 已经通过 `ToolRegistry.execute("mcp.call_tool", ...)` 调用工具，并保留原有真实 server -> mock fallback 行为。
- **当前最合理的面试口径**：Registry 已经证明可管理 Search、Knowledge/RAG 和 MCP execute 三条真实链路；Motion 已经在默认 Registry 中有代表性 `motion.compare_pose` ToolSpec，但主链路还没强制迁移。后续优先评估 Motion 的“标准动作比较”这一小段是否迁移，媒体上传和姿态估计仍保持 API 层直接控制。

## 1. 当前状态

| 能力 | Registry 中是否有 ToolSpec | 主链路是否通过 Registry 执行 | 当前判断 |
|---|---|---|---|
| Search | 有：`search.tavily` | 是 | 已完成真实链路接入 |
| Knowledge/RAG | 有：`knowledge.retrieve` | 是 | 已完成 Chat/Diet 检索接入 |
| Motion | 有：`motion.compare_pose` | 否 | 只注册了代表性“姿态序列比较”工具，媒体链路未迁移 |
| MCP | 有：`mcp.call_tool` | 是，execute 节点已接入 | discovery/plan/format 仍由 MCP 子图控制 |

这里要区分“注册代表工具”和“主链路接入”。默认 Registry 注册 `motion.compare_pose` 和 `mcp.call_tool`，说明工具契约可以描述它们；MCP execute 已经接入主链路，但 Motion 仍只是注册了代表工具，不能说 Motion 已经被 Registry 接管。

## 2. 为什么 Motion 要谨慎

Motion 不是一个单一函数调用，而是由多段能力组成：

```text
图片/视频上传
  -> 文件校验与临时文件管理
  -> MediaPipe 姿态估计
  -> PoseSequence 生成
  -> 标准动作库选择
  -> schema/coordinate_space 安全比较
  -> FastDTW/余弦/逐关节距离
  -> 教练式反馈
```

其中最适合 Registry 管理的是 **`PoseSequence -> PoseSequence` 的标准动作比较**，也就是当前 `motion.compare_pose` 对应的能力。它的输入输出边界清晰，不直接处理文件和模型加载。

不建议立刻迁移的部分：

- **图片/视频上传**：涉及 `UploadFile`、文件大小、格式校验、临时文件删除和 HTTP 错误码，应该继续由 FastAPI API 层控制。
- **MediaPipe 姿态估计**：依赖本地模型文件 `pose_landmarker.task`，失败原因包括依赖缺失、模型路径缺失、无人体姿态、视频解码失败，错误边界比普通工具复杂。
- **标准动作库选择**：既要读目录，又要校验 reference 与用户序列 schema 是否兼容，和前端展示、用户选择强相关。
- **对话 Motion 子图**：当前更多负责文本规划和 `.npz` 引导，不是图片/视频主入口，强迁移收益有限。

因此，Motion 的迁移应该按“算法内核先接入，媒体入口后评估”的顺序，而不是把整个 Motion API 包成一个大工具。

## 3. MCP execute 已完成接入

MCP 子图当前链路是：

```text
discover_tools_node
  -> plan_tool_call_node
  -> execute_tool_node
  -> format_result_node
```

其中 `execute_tool_node` 的职责非常接近 Registry：

```text
tool_name + arguments
  -> MCPClient.call_tool(tool_name, arguments)
  -> ToolResult
```

现在已改成 Registry-backed 执行：

```text
execute_tool_node
  -> ToolRegistry.execute(
       "mcp.call_tool",
       {"tool_name": tool_name, "arguments": arguments},
       context={"allowed_permissions": ["subprocess"]}
     )
  -> ToolResult
```

这个迁移收益比较明确：

- `mcp.call_tool` 的参数可以被 Registry 做最小 schema 校验。
- `subprocess` 权限可以显式写进 context，而不是散落在口头说明里。
- 每次 MCP 调用都会有 `execution_id`、`duration_ms` 和 audit log。
- 后续可以把“工具名必须来自 `tools/list` 发现结果”升级为 Registry 或 MCP wrapper 的 allowlist 校验。
- 面试时可以更自然地解释：MCP 是外部工具协议，Registry 是内部治理层，MCPClient 可以作为 Registry 管理的一个工具。

需要注意的是，Registry 当前的 `timeout_seconds` 仍主要是策略元数据，真正超时仍依赖 MCPClient 内部实现；不能把它夸大成完整生产级超时隔离。

## 4. 建议实现顺序

### Step 1：MCP execute 节点接入 Registry（已完成）

目标：只替换 `execute_tool_node` 的执行入口，不改变 discover、plan、format。

已验收：

- MCP mock 模式仍能返回菜谱结果。
- 真实 server 不可用时仍能 fallback 到 mock。
- `_tool_result.meta` 包含 `tool_name=mcp.call_tool`、`execution_id`、`duration_ms`、`permission=subprocess`。
- 原有 MCP 测试通过，并新增 Registry 集成测试。

验证结果：

- `pytest tests\test_mcp_client.py tests\test_tool_registry.py -q`：`27 passed`
- `D:\Users\Lesedi\anaconda3\envs\fitness-agent\python.exe -m pytest tests/ -q`：`189 passed, 2 skipped, 2 warnings`

面试价值：证明 Registry 不只管理检索和搜索，也可以管理外部协议工具。

### Step 2：Motion 标准动作比较接入 Registry

目标：只迁移 `compute_pose_sequence_similarity(user_sequence, reference_sequence)` 这一段，不迁移上传、姿态估计和临时文件。

验收：

- 视频标准动作对比仍返回相似度指标。
- schema 不兼容仍被明确拒绝。
- Registry meta 能记录本次比较的执行信息。
- Motion API 的 HTTP 行为不变。

面试价值：证明 Motion 的数值算法也可以纳入工具治理，但仍保留媒体链路的边界控制。

### Step 3：再评估 PoseEstimator 是否需要 ToolSpec

只有当后续需要统一记录图片/视频姿态估计耗时、模型版本、失败原因和依赖状态时，才考虑新增：

- `motion.estimate_image_pose`
- `motion.estimate_video_pose`

这一步不是当前最迫切优化，因为它牵涉文件、模型依赖和 API 错误码，迁移成本高于面试收益。

## 5. 面试回答口径

如果面试官问“为什么 Motion 还没全部走 ToolRegistry，MCP 做到哪一步了”，可以这样回答：

> 我没有为了统一而强行把所有工具一次性塞进 Registry。Search 和 Knowledge/RAG 的输入输出都是结构化文本和检索结果，风险低，所以我先迁移它们；MCP 的 execute 节点也已经接入 Registry，因为它天然符合 `tool_name + arguments -> ToolResult`。Motion 的边界更复杂，涉及上传文件、姿态模型、`PoseSequence` 和标准动作库，所以我不会把整个 Motion API 包成一个大工具。下一步只评估标准动作比较这段算法内核是否接入 `motion.compare_pose`，媒体上传和姿态估计继续由 API 层控制。

这段回答要体现三点：

- 不是没想到统一治理，而是按风险和收益排序。
- Registry 不替代 LangGraph，也不替代 FastAPI 的上传边界。
- 个人项目要优先保证可运行、可解释和可验证，避免为了架构感破坏主链路。

## 6. 后续暂不迁移完整 Motion 的原因

MCP execute 已完成接入，但完整 Motion 仍暂不迁移，原因是：

- Motion 迁移涉及 API、工具、测试和小程序展示，应该拆成更小的增量。
- 媒体上传、模型文件缺失、视频解码和临时文件清理更适合留在 API 层。
- `motion.compare_pose` 只覆盖标准动作比较，不应被包装成整个 Motion 能力。

当前阶段已暂停继续迁移。后续如果重新启动工具治理，再评估 **Motion 标准动作比较接入 Registry**。
