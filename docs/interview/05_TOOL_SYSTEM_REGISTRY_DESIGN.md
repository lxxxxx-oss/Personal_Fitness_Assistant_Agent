# P1 专题：工具系统口径与最小 ToolRegistry 设计

这份文档专门回答一个高频追问：**你的 Agent 工具系统到底是怎么做的，和 MCP 有什么区别，最小 ToolRegistry 已做到哪里，为什么还不说它是生产级工具平台？**

## 1. 一句话口径

> 项目里的工具系统不是“写几个函数让 LLM 调用”，而是把检索、搜索、动作分析、姿态估计、MCP Client 等确定性能力封装成有输入契约、权限边界、统一返回和错误码的执行单元；当前已经在 `ToolResult/ErrorCode` 和子图调用边界之上，补了最小 `ToolRegistry` 原型，用来集中管理工具元数据、参数校验、权限、超时策略字段、有限重试、fallback 和 audit log，并让 Search 子图通过 Registry 调用 `search.tavily`，让 Chat/Diet 的 RAG 检索通过 Registry 调用 `knowledge.retrieve`，让 MCP 执行节点通过 Registry 调用 `mcp.call_tool`。每次 Registry 调用都会产生 `execution_id` 和 `duration_ms`，fallback 会复用同一个 `execution_id` 并标出 `fallback_from`；但 Registry 当前不负责强制中断超时执行，真实超时隔离仍依赖具体工具自身或后续 ToolExecutor 增强。

## 2. 工具系统和 MCP 的区别

| 概念 | 它是什么 | 在项目中的位置 | 面试口径 |
|---|---|---|---|
| 内部工具系统 | 项目自己定义和调用的确定性能力集合 | SearchTool、Retriever、MotionTool、PoseEstimator、MCPClient 等 | 主线是“工具契约 + 受控执行 + 统一结果回传” |
| MCP | 外部工具发现和调用的标准协议 | 作为 `MCPTool` 子链路的一种外部协议适配 | 只是工具协议补充，不是整个工具系统本身 |
| ToolRegistry | 工具元数据和执行治理中心 | 已落地最小原型，Search、Knowledge/RAG 与 MCP execute 已接入，尚未全面接管所有子图 | 用于统一注册、发现、校验、权限、执行、审计和基础观测 |

面试时不要把 MCP 当成全部工具系统。更稳的说法是：

> MCP 解决的是“外部工具如何标准化接入”；内部工具系统解决的是“项目里的每个工具如何定义、校验、执行、失败处理和回传”。MCPClient 本身也可以作为一个内部工具被 Registry 管理。

## 3. 当前工具调用链路

```text
用户请求
  -> Router 判断能力域
  -> LangGraph 子图选择工具
  -> 工具函数/工具类执行确定性任务
  -> ToolResult(ok/data/error_code/error_message/meta)
  -> 子图写回 RouterState
  -> LLM 基于结构化结果生成自然语言回答
```

当前工具系统已经统一的部分：

- **职责**：每个工具只做一类确定性任务，例如 Retriever 检索知识、SearchTool 联网搜索、MotionTool 计算姿态相似度。
- **输入**：函数签名、`check_str_nonempty`、`check_int_range`、`check_float_range`、Pydantic 请求模型和 `PoseSequence` 共同承担输入契约。
- **输出**：所有核心工具返回 `ToolResult`，成功时 `ok=True` 并放入 `data`，失败时返回 `error_code` 和 `error_message`。
- **权限**：LLM 不直接操作文件系统、命令或网络；工具只能在子图允许的边界内执行。
- **错误处理**：用 `CONFIG_MISSING`、`NETWORK_ERROR`、`PERMISSION_DENIED`、`INVALID_PARAM`、`DATA_NOT_FOUND`、`INTERNAL_ERROR` 区分失败原因，方便 fallback 或明确告知用户。

当前还没有完全统一的部分：

- 内部工具不是让 LLM 动态发现后自由选择，而是由 Router 和子图控制调用。
- Search 子图已经通过 `ToolRegistry` 调用 `search.tavily`，Knowledge/RAG 已通过 `ToolRegistry` 调用 `knowledge.retrieve`，MCP execute 已通过 `ToolRegistry` 调用 `mcp.call_tool`，但 Motion 还没有强制改走 Registry。
- 权限、超时策略字段、重试和审计已有最小 Registry 入口，但还没有覆盖所有子图调用，也还没有实现 Registry 层硬超时中断。
- MCP 的 `inputSchema` 校验和真实 Server 兼容性仍属于后续增强。

## 4. 最小 ToolRegistry 设计

最小设计目标不是做一个复杂框架，而是补齐面试官关心的五件事：**职责、输入、输出、权限、错误可处理**。

### 4.1 核心对象

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    permission: str
    executor: Callable[[dict], ToolResult]
    timeout_seconds: float = 10.0
    max_retries: int = 0
    retryable_error_codes: tuple[str, ...] = ("NETWORK_ERROR",)
    fallback_tool: str | None = None
```

```python
class ToolRegistry:
    def register(self, spec: ToolSpec) -> None: ...
    def list_tools(self, scope: str | None = None) -> list[ToolSpec]: ...
    def get(self, name: str) -> ToolSpec: ...
    def validate_args(self, spec: ToolSpec, args: dict) -> ToolResult: ...
    def check_permission(self, spec: ToolSpec, context: dict) -> ToolResult: ...
    def execute(self, name: str, args: dict, context: dict) -> ToolResult: ...
```

### 4.2 最小字段为什么够用

| 字段 | 解决什么问题 | 示例 |
|---|---|---|
| `name` | 工具唯一标识，避免到处 import 后名字混乱 | `knowledge.retrieve`、`motion.compare_pose` |
| `description` | 让 Router/子图知道什么时候该用 | “检索本地健身知识库” |
| `input_schema` | 参数结构化校验，避免 LLM 传错格式 | `query: string`、`top_k: 1..10` |
| `permission` | 区分只读、网络、文件、外部进程等风险 | `read_only`、`network`、`subprocess` |
| `executor` | 真正执行工具逻辑 | 调用 Retriever、Tavily、MotionTool |
| `timeout_seconds` | 记录工具级超时策略，供具体工具或后续 ToolExecutor 使用；当前 Registry 本身不强制中断执行 | MCP Client 自身 stdout 超时、后续统一 executor 超时 |
| `max_retries` | 失败恢复有边界 | 网络错误最多重试 1-2 次 |
| `fallback_tool` | 可用性降级 | Milvus 失败 fallback 到 MemoryRetriever |

### 4.3 执行流程

```text
ToolRegistry.execute(name, args, context)
  -> get ToolSpec
  -> validate_args(input_schema, args)
  -> check_permission(permission, context)
  -> run executor（当前不在 Registry 层强制中断 timeout）
  -> if retryable: bounded retry
  -> if still failed and fallback_tool exists: fallback
  -> ToolResult.meta 写入 execution_id/duration_ms/attempts
  -> audit log 写入 execution_id/duration_ms/fallback_from
```

这个设计的关键是：**Registry 不负责业务规划，业务规划仍由 Router 和 LangGraph 子图负责。Registry 只负责工具治理。**

## 5. 为什么不说它已经是完整工具平台

面试时可以这样回答：

> 我现在只把 ToolRegistry 做到最小可用原型，并先接入 Search、Knowledge/RAG 和 MCP execute，因为这几条链路的执行入口比较清晰、面试收益高。Motion 处理文件、MediaPipe 模型和 NumPy 姿态序列，如果一下子强行替换整个 Motion API，会引入适配风险，不一定提升核心链路。当前更合理的做法是先用 Search、Knowledge 和 MCP execute 证明 `ToolSpec + ToolRegistry` 的 schema、权限、执行、重试、fallback 和审计链路可行，再谨慎评估 Motion 标准动作比较这一小段算法内核。

这句话要体现两个点：

- Registry 已有最小原型，但不是生产级工具平台。
- 主链路稳定优先，接入顺序要从低风险工具开始。

### 5.1 Motion 为什么不一次性迁移？MCP 做到哪一步？

如果面试官继续追问“既然你有 ToolRegistry，为什么 Motion 还没全部走它，MCP 做到哪一步”，可以这样答：

> 我没有为了统一而强行把所有工具一次性塞进 Registry。Search 和 Knowledge/RAG 的输入输出主要是文本、检索结果和结构化列表，风险低，所以我先迁移它们；MCP 的 execute 节点也已经接入 Registry，因为它天然是 `tool_name + arguments -> ToolResult`。Motion 的边界更复杂：它有图片/视频上传、临时文件、MediaPipe 模型、`PoseSequence`、标准动作库和数值比较。所以我的策略是只评估 Motion 标准动作比较这段算法内核是否接入，媒体上传和姿态估计继续由 FastAPI/API 层控制。

这不是回避实现，而是工程边界控制：

- **MCP execute 已完成迁移**：`execute_tool_node` 已经拿到 `tool_name` 和 `arguments`，现在通过 `ToolRegistry.execute("mcp.call_tool", ...)` 调用工具，收益是权限、审计和执行元数据统一。
- **Motion compare 适合后迁移**：`PoseSequence -> PoseSequence` 的标准动作比较输入输出清晰，可以接入 `motion.compare_pose`。
- **Motion 媒体入口暂不迁移**：上传文件、模型文件缺失、视频解码、临时文件清理和 HTTP 错误码更适合由 API 层直接控制。
- **准确口径**：MCP execute 已经进入 Registry，但 MCP discovery/plan/format 仍由子图控制；Motion 只注册了 `motion.compare_pose` 代表工具，不能说 Motion 已完整迁移。

细节版设计记录见：`docs/technical/tool-registry/MOTION_MCP_REGISTRY_MIGRATION_EVALUATION.md`。

## 6. 如果面试官继续追问

### Q：新增一个工具的完整流程是什么？

> 当前流程是：先定义工具职责，再确定输入结构和校验方式，然后让工具统一返回 `ToolResult`，最后在对应 LangGraph 子图里接入调用并把结果写回状态。现在有了最小 ToolRegistry 后，新增工具可以进一步注册成一个 `ToolSpec`：写清 name、description、input_schema、permission、executor、timeout、retry 和 fallback。短期内子图仍可以直接调工具，逐步迁移后子图再通过 registry 调用。

### Q：ToolRegistry 会不会和 LangGraph 重复？

> 不重复。LangGraph 解决“任务流程怎么流转”，比如先检索还是先搜索、失败后去哪一步；ToolRegistry 解决“一个具体工具怎么被安全、稳定、可观测地执行”。前者是流程编排层，后者是工具治理层。

### Q：ToolRegistry 会不会和 MCP 重复？

> 不重复。MCP 是外部工具协议，主要解决工具发现和远程调用规范；ToolRegistry 是项目内部治理层，既可以管理本地工具，也可以把 MCPClient 作为一个工具纳入管理。简单说，MCP 是一种工具来源，Registry 是工具管理方式。

### Q：最小版本先做什么？

> 最小版本已经先注册了 Retriever、SearchTool、Motion compare、MCPClient 四类代表工具，并统一了 `ToolSpec` 元数据、参数校验、权限检查、有限重试、fallback 和 audit log。它不做复杂动态规划，也不让 LLM 任意发现和调用工具，仍保持 Router/子图控制执行顺序。目前 Search、Knowledge/RAG 和 MCP execute 已经接入 Registry，Registry 结果和 audit log 也已经包含 `execution_id`、`duration_ms`、attempts 和 fallback 归因。
