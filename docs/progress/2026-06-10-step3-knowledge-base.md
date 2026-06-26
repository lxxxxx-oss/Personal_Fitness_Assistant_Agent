# Step 3: 权威知识库构建

**日期:** 2026-06-10
**测试结果:** 45 passed, 1 skipped, 0 failed

---

## 做了什么

### 新增 3 份权威知识文件

通过 WebSearch 从国际权威卫生机构获取运动与营养指南，整理为知识库文件：

| 文件 | 来源 | 大小 | 核心内容 |
|------|------|------|----------|
| `who_physical_activity.txt` | WHO 2020 | 1.6 KB, 38行 | 成年人有氧/力量建议、老年人、儿童青少年、关键信息 |
| `cdc_strength_training.txt` | CDC 2023 | 2.0 KB, 55行 | 训练频率/组数/次数/强度、肌肉群、动作示例、常见问题 |
| `who_healthy_diet.txt` | WHO/FAO 2007 + WHO 2024 | 2.3 KB, 57行 | 蛋白质摄入标准（详表）、健康饮食五大要点、安全提醒 |

### 数据获取方式

- 使用 `WebSearch` 搜索 WHO、CDC 官方网站
- 搜索 API 返回了官方页面的完整指南文字内容（非摘要，是实际条款）
- `WebFetch` 因安全策略无法直接抓取 who.int / cdc.gov / nhs.uk 等卫生域名
- 内容可靠性：搜索结果的文字直接来自指南正文，数据具体、可交叉验证

### 知识库当前全貌

```
data/knowledge/
├── who_physical_activity.txt    🆕 WHO 身体活动指南（权威）
├── cdc_strength_training.txt    🆕 CDC 力量训练建议（权威）
├── who_healthy_diet.txt         🆕 WHO/FAO 健康饮食与蛋白质指南（权威）
├── fitness_basics.txt              训练动作讲解（实用补充）
└── nutrition.txt                   饮食方案示例（实用补充）
```

总大小：约 9 KB，184 行。几乎不占空间。

### 每篇都有出处标注

知识文件末尾标注了具体来源，如：
- `WHO Technical Report Series 935` — 蛋白质氨基酸需求报告
- `https://www.who.int/publications/i/item/9789240015128` — 身体活动指南
- `https://www.cdc.gov/physicalactivity/basics/adults/` — CDC 成年人指南

---

## 未完成

- `WebFetch` 无法抓取 gov/org/edu 域名，已尽力。如需 NHS 动作讲解、ACSM 立场声明等受限于网络限制的内容，建议手动下载后放入 `data/knowledge/`
- 旧文件 `fitness_basics.txt` 和 `nutrition.txt` 为英文，后续可翻译

## 仍需继续的工作

1. 知识库中文化（翻译旧文件）
2. Search 子图 Mock 数据丰富化
3. `/motion/analyze` 端点
4. MCP Server 真实接入
5. Milvus 迁移
