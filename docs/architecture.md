# 架构

## 一句话

一个引擎，多个壳。引擎负责取数、抽取、聚合、出交接包；壳负责入口和展示。

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
多源检索      OA 全文/图注    模型 API（DSH 凭据）
```

## 七个阶段

| 阶段 | 模块 | 输入 | 输出 |
| --- | --- | --- | --- |
| 1 检索规划 | `plan` / `europepmc` / `sources` | 方向 + PICO + 年份 + OECD 子类 | 布尔检索式、源清单 |
| 2 多源检索 | `pipeline` + `sources` | 检索式、篇数、源 | `papers` 表、源体检 |
| 3 相关性闸门 | `domain` | 标题/摘要、OECD 子类 | 保留/挡掉 + 理由 |
| 4 全文 | `fulltext` | PMCID/DOI/OA 链接 | JATS XML、图注、图 URL、引用句 |
| 5 卡片 | `cards` | 全文 + 摘要 | 结构化字段 + 证据定位 |
| 6 聚合 | `aggregate` | 全部卡片 | 共识/争议/空白、方向候选 |
| 7 开题 | `proposal` | 选定方向 + 约束 + 卡片 + 聚合 | `proposal.md` + `proposal.meta.json` + `sources.csv` + `assets/` |

第 7 阶段有两种结构：`cn` 国内九节、`intl` 国际 research proposal。两者共用第 1–6 阶段的证据层，只换大纲与章节写法。正式 Word 不在引擎内完成；`proposal.preview.docx` 只是可选预览。

## 数据模型

`papers`：id、source、pmid、pmcid、doi、title、abstract、year、journal、authors、is_oa、cited_by、payload。

运行产物：

- `runs/<时间戳>/summary.json`：聚合结果、运行参数、源体检；
- `runs/<时间戳>/papers.csv`：检索决策；
- `runs/<时间戳>/proposal.md`：开题报告唯一内容源；
- `runs/<时间戳>/proposal.meta.json`：模式、章节、引用格式、内容哈希、交接说明；
- `runs/<时间戳>/sources.csv`：引文索引；
- `runs/<时间戳>/assets/`：图、表、流程图。

## 关键约定

1. **证据优先**：任何进入结论区的字段，必须能指到页码/图号/原文引句。
2. **可重跑**：所有阶段幂等，按 id 去重，缓存落盘。
3. **可中断**：长任务在后台，状态可查；不做“点了没反应”。
4. **不造假**：拿不到全文就只到摘要层，并在卡片上标注；样本量、统计功效、伦理批号不代填。
5. **一套引擎多壳**：壳不承载业务逻辑，只做输入与展示。
6. **内容与版式分离**：引擎只负责 Markdown + 元数据 + 素材；正式版式交给下游排版 agent。

## 目录

```
src/litradar/
├── config.py       # 路径、UA、限速
├── models.py       # Paper 数据类
├── store.py        # SQLite
├── sources.py      # 多源检索与规范化
├── domain.py       # 领域闸门
├── fulltext.py     # OA 全文与图注
├── cards.py        # 结构化卡片与证据定位
├── aggregate.py    # 共识/争议/空白
├── proposal.py     # 双模式开题报告 + 交接包
├── pipeline.py     # 七阶段编排
├── web.py          # 本地 Web
└── cli.py          # 命令行入口

docs/proposal_formats.md  # 双模式与交接契约
dsh-plugin/               # DSH 插件（Host + Client 两半）
packaging/                # 安装器与发布脚本
```
