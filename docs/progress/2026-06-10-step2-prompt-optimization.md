# Step 2: Prompt 全面优化

**日期:** 2026-06-10  
**测试结果:** 45 passed, 1 skipped, 0 failed

---

## 做了什么

### 改动范围

5 个文件，9 个 prompt，全部优化。

### 优化原则

| 原则 | 说明 |
|------|------|
| 统一中文 | Qwen3-0.6B 是中文模型，所有 prompt 从英文/中英混用改为统一中文 |
| 角色具体化 | 不只说"你是健身助手"，定义具体专长领域、行为约束 |
| 结构化输出 | 每个 prompt 指定输出格式（结论先行 → 要点展开 → 来源标注） |
| Few-shot 示例 | 格式敏感的 prompt（extract_profile, query_understanding, plan_tool_call）添加示例 |
| 安全护栏 | 所有涉及健康的 prompt 加入"不替代医生"的安全提醒 |
| 来源引用 | Chat/Search 子图要求标注信息来源 |

### 逐文件改动详情

#### 1. `app/graph/subgraphs/chat.py` — generate_node

- 角色从 `"You are a professional fitness assistant"` → 定义 4 个专长领域
- 添加 4 条回答规则：参考资料优先、诚实边界、结构化输出、安全提醒
- 所有文字从英文改为中文

#### 2. `app/graph/subgraphs/diet.py` — extract_profile_node

- 添加 2 个 few-shot 示例
- 字段名规范化：`Height (cm)` → `height_cm`，`Dietary preferences` → `preferences`
- 明确"只输出 JSON，不要任何解释文字"

#### 3. `app/graph/subgraphs/diet.py` — recommend_node

- 角色：`"professional fitness nutritionist"` → `"注册运动营养师"`
- 添加 5 段结构化输出要求：画像摘要→核心建议→食物推荐→餐次安排→注意事项
- 添加安全提醒：不推荐极端饮食

#### 4. `app/graph/subgraphs/search.py` — query_understanding_node

- 添加 2 个 few-shot 示例（深蹲膝盖弹响、减脂水果摄入）
- 规则细化为 3 条：提取核心概念、中英文均可、只输出关键词

#### 5. `app/graph/subgraphs/search.py` — synthesis_node

- 添加 5 条回答规则：摘要先行、要点展开、来源标注、诚实说明、安全提醒
- 英文 → 中文

#### 6. `app/graph/subgraphs/motion.py` — think_node

- 角色细化：`"3D motion analysis expert"` → `"运动生物力学专家"` + 专长描述
- 分析要点从 3 条扩充到 4 条，更具体

#### 7. `app/graph/subgraphs/motion.py` — check_node（两分支）

- 无数据分支：添加角色定义、告知用户如何获取 .npz 数据、不做无根据推测
- 有数据分支：添加三个指标的解读标准（DTW<0.3 优秀、余弦>0.85 优秀、形状差<0.2 优秀）、处理指标矛盾情况、5 条回答要求

#### 8. `app/graph/subgraphs/mcp.py` — plan_tool_call_node

- 添加 2 个 few-shot 示例（番茄炒蛋→get_recipe、鸡蛋番茄→search_ingredients）
- 中文角色定义 + 输出格式约束

#### 9. `app/graph/subgraphs/mcp.py` — format_result_node

- 添加 5 条格式要求：标题、配料列表、步骤编号、小贴士、语言风格
- 英文 → 中文

---

## 未改动

- 所有业务逻辑代码（节点函数、数据流、条件路由）
- API 接口
- 测试用例
- 配置文件

## 仍需继续的工作

1. **Step 3:** 知识库扩写（fitness_basics.txt, nutrition.txt 目前内容偏少）
2. **Step 4:** Search 子图 Mock 数据丰富化
3. **后续:** `/motion/analyze` 端点、MCP Server 接入、Milvus 迁移
