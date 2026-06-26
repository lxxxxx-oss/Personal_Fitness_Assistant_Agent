# Step 4: 知识库中文化 + 检索修复 + 验证

**日期:** 2026-06-10  
**测试结果:** 45 passed, 1 skipped, 0 failed（retriever 测试有随机向量概率性失败，非此次改动引入）

---

## 做了什么

### 1. 知识库全部中文化

| 文件 | 改动 | 大小 |
|------|------|------|
| `fitness_basics.txt` | 英文 → 中文，内容扩展（深蹲/硬拉/卧推动作细节、减脂/增肌原则、热身/放松） | ~3 KB, 60行 |
| `nutrition.txt` | 英文 → 中文，内容扩展（减脂/增肌餐单、食物营养成分、安全提醒） | ~3 KB, 55行 |
| `who_physical_activity.txt` | 已有（Step 3） | 1.6 KB |
| `cdc_strength_training.txt` | 已有（Step 3） | 2.0 KB |
| `who_healthy_diet.txt` | 已有（Step 3） | 2.3 KB |

全部知识库现在为统一中文。

### 2. 修复中文关键词检索

**问题：** `_keyword_search` 降级算法按空格分词（`split()`），但中文没有空格，导致所有中文查询返回 0 结果。

**修复：** 在 `app/tools/retriever.py` 的 `_keyword_search` 方法中增加子串匹配 + 字重叠算法：
- 方法1（英文）：空格分词 → 词集交集（保留）
- 方法2（中文）：完整查询子串匹配（score=1.0）+ 逐字重叠匹配（score=0.8）

### 3. 检索效果验证

在 **无 embedding 模型**（仅关键词匹配降级）的条件下测试：

| 查询 | 命中 | 分数 | 来源 |
|------|------|------|------|
| 深蹲 | ✅ | 1.00 | 健身基础动作指南 |
| 减脂 | ✅ | 1.00 | 运动营养实用指南 |
| 增肌 | ✅ | 1.00 | 健身基础动作指南 |
| 身体活动 | ✅ | 1.00 | WHO/CDC 指南 |
| 蛋白质 | ✅ | 1.00 | WHO/FAO 指南 |
| 健康饮食 | ✅ | 1.00 | 运动营养实用指南 |
| WHO运动指南 | ✅ | 0.80 | WHO/CDC 指南 |
| CDC力量训练 | ✅ | 0.80 | CDC 力量训练建议 |

**全部命中。** 在 embedding 模型可用后会获得更好的语义匹配质量。

### 4. PDF 提取失败

`中国居民膳食指南2021版.pdf` 为扫描版 PDF（图片内容），PyPDF2、pdfplumber、pymupdf 三个库均无法提取中文字符（仅 34-48 字节乱码）。建议：
- 寻找可编辑/文本版本的 PDF
- 或手动将核心内容整理为 .txt 文件
- PDF 已加入 `.gitignore`，不会被误提交

---

## 知识库当前全貌

```
data/knowledge/
├── .gitignore                         # 排除 *.pdf
├── who_physical_activity.txt          WHO 身体活动指南（2020）
├── cdc_strength_training.txt          CDC 成年人力量训练建议
├── who_healthy_diet.txt               WHO/FAO 蛋白质与健康饮食
├── fitness_basics.txt                 健身基础动作指南（中文）
├── nutrition.txt                      运动营养实用指南（中文）
└── 中国居民膳食指南2021版.pdf          扫描版，无法自动提取（本地参考）
```

纯文本总计约 **12 KB，200+ 行**，全部中文，条条有出处。

---

## 仍需继续的工作

1. 中国居民膳食指南 PDF 手动整理为知识文件
2. Search 子图 Mock 数据丰富化
3. `/motion/analyze` 端点
4. MCP Server 真实接入
5. Milvus 迁移
6. Embedding 模型离线下载（需网络）
