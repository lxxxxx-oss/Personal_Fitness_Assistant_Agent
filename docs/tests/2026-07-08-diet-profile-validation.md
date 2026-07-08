# Diet 画像校验验收

## 覆盖

- 从带 Markdown 包装的模型文本中提取 JSON。
- 数字字符串、未知值、中文性别和偏好列表正常化。
- 越界身体数据拒绝进入结构化画像。
- 非 JSON 模型输出降级为空画像并产生稳定 warning。
- Diet 路由集成链路保持 HTTP 200。

## 定向结果

```powershell
python -m pytest tests/test_diet_profile.py tests/test_rag_context.py tests/test_integration.py::TestIntegration::test_intent_routing_diet -q -p no:cacheprovider
```

结果：`8 passed, 1 warning`。

全量回归：`155 passed, 2 skipped, 1 warning`。
