# Codex Session State

## Current Task

- Status: idle
- Goal: 为简历四项项目亮点分别建立可应对连续追问的专项面试文档。
- Updated: 2026-08-09

## Progress

- 已在 `docs/interview/` 生成混合意图路由、混合检索 RAG、分层记忆与上下文压缩、3D 动作相似度分析四份专项问答。
- 每份文档均包含技术首次出现说明、完整链路、完整问答、连续追问、防守边界、白板讲解和参考资料。
- 外部资料用于校准 Agent 岗位常见追问方式；项目答案以当前代码、测试和事实文档为准。

## Touched Files

- `docs/interview/01_混合意图路由专项面试问答.md`
- `docs/interview/02_混合检索RAG专项面试问答.md`
- `docs/interview/03_分层记忆与上下文压缩专项面试问答.md`
- `docs/interview/04_3D动作相似度分析专项面试问答.md`
- `.gitignore`
- `.codex/SESSION_STATE.md`

## Key Decisions

- 四份材料统一采用“是什么—解决什么问题—项目如何使用—替代方案—为何选择”的首次概念解释模板。
- 严格区分当前已实现、已验证指标、已知边界和生产化升级方向。
- `docs/interview/agent.json` 是个人简历源文件，仅补充忽略规则，不读取、不修改。

## Verification

- 四份文档共 91 组编号问答，文件均存在且 UTF-8 可读。
- 四份文档的本地 Markdown 链接检查通过，无行尾空白。
- 已确认 `docs/interview/agent.json` 被 `.gitignore` 排除。
- 本轮只改文档和忽略规则，未修改代码，未运行代码测试。

## Next Steps

- 可任选一个亮点，按对应文档进行模拟面试和连续追问训练。

## Resume Prompt

读取 `docs/interview/` 中用户指定的专项问答，以真实 Agent 岗面试官身份逐层追问，并在用户回答后指出事实错误、表达风险和更优口径。
