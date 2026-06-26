# Step 5: 工具规范化（错误码、输入校验、权限声明）

**日期:** 2026-06-10
**测试结果:** 58 passed, 1 skipped, 0 failed (+8 新增测试)

---

## 做了什么

### 新建共享类型 `app/tools/types.py`

| 类型 | 作用 |
|------|------|
| `ErrorCode` | 6 种标准错误码：CONFIG_MISSING / NETWORK_ERROR / PERMISSION_DENIED / INVALID_PARAM / DATA_NOT_FOUND / INTERNAL_ERROR |
| `ToolResult` | 统一返回结构（ok/data/error_code/error_message/meta），静态工厂方法 `.ok()` / `.fail()` |
| 校验函数 | `check_str_nonempty` / `check_str_len` / `check_int_range` / `check_float_range` |

### 逐工具修复

| 工具 | 输入校验 | 输出标准化 | 权限声明 | 错误码 |
|------|---------|-----------|---------|--------|
| **TavilySearchTool** | ✅ query 长度 1-500, max_results 1-20 | ✅ ToolResult + meta `is_mock` | ✅ 档敏感查询 | ✅ 网络/CONFIG/参数/权限 |
| **MotionTool** | ✅ shape/nonzero 校验 | ✅ ToolResult + labels + overall_verdict | ✅ 不替代教练 | ✅ 文件/格式/内部错误 |
| **MCPClient** | ✅ tool_name/arguments 非空 | ✅ 全部 ToolResult | ✅ 连接外部进程边界 | ✅ 网络/数据/内部 |
| **MemoryRetriever** | ✅ top_k 1-100, threshold 0.0-1.0 | ✅ ToolResult + meta `mode` | ✅ 不做事实核查 | ✅ embedding/keyword + 降级标记 |
| **LLMLoader** | ✅ prompt 非空 ≤8192 chars | ✅ 模型缺失返回 `[Error]` | ✅ 不替代医疗 | ✅ DATA_NOT_FOUND + 路径提示 |

### 新增 8 个测试

- `test_search_tool.py`: test_invalid_query_returns_error, test_query_too_long_returns_error, test_max_results_out_of_range
- `test_mcp_client.py`: test_mock_tool_call_unknown_recipe (增强)
- `test_motion_tool.py`: test_rejects_invalid_shape, test_rejects_all_zeros
- `test_mcp_client.py`: disconnect now tested via ToolResult

### 改动的子图调用方

| 文件 | 改动 |
|------|------|
| `chat.py` | `retriever.search()` → 取 `.data`, 记录 `.meta` |
| `diet.py` | 同上 |
| `search.py` | `tool.search()` → 取 `.data`, 记录 `.meta` |
| `motion.py` | `list_motion_library`/`load_npz_pose`/`compute_similarity` → 检查 `.ok` 再取 `.data` |
| `mcp.py` | `client.list_tools()` → 取 `.data` |

---

## 仍需继续的工作

1. `/motion/analyze` 端点（缺 .npz 数据）
2. Search Mock 数据丰富化
3. MCP Server 真实接入
4. Embedding 模型离线下载
