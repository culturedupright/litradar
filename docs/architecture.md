# 架构

## 一句话

一个引擎，多个壳。引擎负责取数、抽取、聚合；壳负责入口和展示。

```
壳：本地 Web / DSH 插件 / Claude Desktop（MCP）
                │
                ▼
        ┌───────────────┐
        │  LitRadar 引擎 │
        │  SQLite + 文件 │
        └───────────────┘
                │
   ┌────────────┼────────────┐
   ▼            ▼            ▼
Europe PMC   PMC 全文 XML   模型 API
```

## 七个阶段

| 阶段 | 模块 | 输入 | 输出 |
| --- | --- | --- | --- |
| 1 检索式 | `europepmc.build_query` | 方向 + PICO + 年份 | 布尔检索式 |
| 2 检索 | `europepmc.iter_papers` | 检索式、篇数上限 | `papers` 表 |
| 3 筛选 | `screen`（待实现） | 标题、摘要 | 保留/排除 + 理由 |
| 4 全文 | `fulltext`（待实现） | PMCID | JATS XML、图注、图 URL、引用句 |
| 5 卡片 | `cards`（待实现） | 全文 + 摘要 | 9 字段 + 证据定位 |
| 6 聚合 | `aggregate`（待实现） | 全部卡片 | 共识/争议/空白、方向候选 |
| 7 开题 | `protocol`（待实现） | 选定方向 + 约束 | 开题卡 |

## 数据模型

`papers`：id、source、pmid、pmcid、doi、title、abstract、year、journal、authors、is_oa、cited_by、payload。

后续表：

- `cards(paper_id, data, confidence, created)`
- `runs(run_id, topic, query, counts, tokens, cost, started, finished)`
- `directions(run_id, data)`
- `protocols(run_id, direction_id, data)`

## 关键约定

1. **证据优先**：任何进入结论区的字段，必须能指到页码/图号/原文引句。
2. **可重跑**：所有阶段幂等，按 id 去重，缓存落盘。
3. **可中断**：长任务在后台，状态可查；不做“点了没反应”。
4. **不造假**：拿不到全文就只到摘要层，并在卡片上标注。
5. **一套引擎多壳**：壳不承载业务逻辑，只做输入与展示。

## 目录

```
src/litradar/
├── config.py       # 路径、UA、限速
├── models.py       # Paper 数据类
├── store.py        # SQLite
├── europepmc.py    # 检索
└── cli.py          # 命令行入口

dsh-plugin/         # 后续：DSH 插件（Host + Client 两半）
web/                # 后续：本地 Web 界面
```
