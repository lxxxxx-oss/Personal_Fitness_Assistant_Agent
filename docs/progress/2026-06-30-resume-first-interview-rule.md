# 2026-06-30 简历口径优先规则

## 背景

`docs/interview/agent.json` 是用户的简历 JSON 源文件，包含姓名、联系方式、教育经历、实习经历和项目描述等个人信息。该文件用于本地简历维护，不应提交到 GitHub。

同时，后续 interview 目录下的学习材料需要围绕简历项目描述来准备，优先服务面试追问，而不是只按当前代码完成度写成保守说明。

## 本次调整

- 在 `.gitignore` 中加入 `docs/interview/agent.json`，避免后续上传简历源文件。
- 在 `AGENTS.md` 中新增“简历口径优先规则”。
- 在 `docs/interview/README.md` 中补充简历口径优先说明。
- 按简历重新编写 P0/P1/P2 面试材料，重点覆盖 LangGraph、3D Motion、ReAct、MCP、Milvus、Tavily 和 6 轮 Memory。
- 将产品口径统一为“四类业务能力、五条执行路径”：Diet 与 MCP 同属饮食域，但分别承担营养建议与外部工具调用。
- 撤销“删除 MCP”作为当前路线的文档表述；保留 MCP Client、子图和 mock/真实 Server 双模式作为简历亮点。
- 为 Milvus、MCP mock、Search 来源透传等简历与当前仓库差异补充可防守问答。
- 同步更新 `docs/README.md`、`docs/API.md`、`docs/RUNBOOK.md`、Router 专题和小程序说明，避免当前文档互相冲突。

## 后续执行原则

1. `agent.json` 不提交、不推送。
2. `docs/interview/` 的回答围绕简历中的项目描述、技术关键词和可能追问组织。
3. 如果简历表述领先于当前代码实现，面试材料要准备可防守口径：当前做到哪里、为什么分阶段做、代码边界是什么、后续如何补齐。
4. 不主动弱化简历亮点，但避免低级逻辑矛盾。

## 统一面试口径

| 主题 | 对外主线 | 代码追问边界 |
|---|---|---|
| 功能数量 | 四类业务能力 | 五条 intent，Diet 与 MCP 都属于饮食域 |
| Milvus | RAG 的目标检索技术方案 | 当前仓库为 Sentence-Transformers + NumPy，未直接创建 Milvus 索引 |
| MCP | 自实现轻量 Client 与标准工具调用 | 默认 mock；真实 Server 需要显式配置 |
| Tavily 来源 | 搜索结果进入带来源约束的合成链路 | 普通 `/chat` 尚未完整透传结构化 `sources` |
| Motion | 3D 时序相似度与 ReAct 工具链 | 图片仅单帧，视频时序仍待补 |

## 测试说明

本次仅修改 Git 忽略规则和文档，没有修改运行时代码。已完成以下复核：

- `git diff --check`：通过。
- Markdown 本地链接检查：全部可解析。
- `git check-ignore -v docs/interview/agent.json`：命中 `.gitignore`，且文件未被 Git 跟踪。
- `python -m pytest tests/ -q -p no:cacheprovider`：`114 passed, 1 skipped, 1 warning`。
- Router 绿色集：`66/66`，accuracy `100.0%`。
- Router challenge set：primary、secondary 和 route plan 均为 `36/36`。

第一次从基础 Conda 环境调用 pytest 时因缺少 FastAPI/LangGraph 在收集阶段失败；切换到项目 `fitness-agent` 环境后全量通过。该失败属于环境选择错误，不是代码回归。
