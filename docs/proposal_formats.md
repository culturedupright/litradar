# 开题报告双模式与排版交接约定

## 1. 两种内容模式

| 模式值 | 名称 | 适用 | 章节 |
| --- | --- | --- | --- |
| `cn` | 国内开题报告 | 校内开题、答辩、培养管理 | 九节：立项依据、研究目标、研究内容、研究方案与技术路线、创新点、可行性分析、预期成果、进度安排、参考文献 |
| `intl` | 国际 Research Proposal | 海外申请、国际项目、英文 proposal 底稿 | Abstract、Introduction / Problem、Literature Review / Gap、Research Questions / Hypotheses、Theoretical Framework、Methodology、Data / Ethics、Timeline / Budget、Outcomes / Contribution、Risk / Limitations、References |

两套模式共用同一次检索、同一批卡片、同一套引文校验和聚合结果。差异只放在大纲规划和章节写法，不重复跑检索。

国内没有全国统一的强制开题报告国标，各校模板不同；国家自然科学基金委只发项目申请书模板/撰写提纲，不发高校开题报告模板。因此 `cn` 是“通用九节骨架 + 学校覆盖层”，`intl` 是“国际 research proposal 核心结构 + 学校/资助方覆盖层”。

## 2. 交接包（每次运行目录下）

```text
runs/<时间戳>/
├─ proposal.md              # 唯一内容源
├─ proposal.meta.json       # 元数据与内容哈希
├─ sources.csv              # 引文索引，C1/C2... 对应正文
├─ assets/                  # 图、表、流程图
│  └─ README.md
├─ proposal.preview.docx    # 可选，仅 --preview-docx 或页面勾选时生成
├─ report.md                # 证据简报
├─ papers.csv               # 检索决策
└─ summary.json             # 聚合结果与运行参数
```

`proposal.preview.docx` 是预览版：只有标题、表格、项目符号的基础排版，没有封面、目录、页边距、页眉页脚、学校模板。正式 Word/PDF 由下游排版 agent 读取 `proposal.md` + `proposal.meta.json` 生成。

## 3. `proposal.meta.json` 关键字段

- `schema`：`litradar.proposal/1`
- `doc_type`：`cn_kaiti_report` / `research_proposal`
- `mode`：`cn` / `intl`
- `language`：正文语言，当前为 `zh`
- `heading_language`：`zh` / `en`（`intl` 为英文标题 + 中文正文）
- `template`：`id`、`label`、`source`、`school`、`notes`；`source` 明确写“LitRadar 通用骨架，不是官方模板”
- `sections`：章节 id、标题、层级
- `citation_style`：`GB/T 7714` / `APA 7`，并标注“待按学校/资助方确认”
- `word_limit`：默认 `null`，不写死；由模板/学校要求决定
- `content_sha256`：`proposal.md` 的内容哈希，用于下游校验“只排版不改内容”
- `evidence`：卡片数、共识/争议/空白数、已核/待核证据数、候选/同域/挡掉数
- `constraints`：研究类型、经费、周期、湿实验条件
- `handoff`：交接文件名与说明

## 4. 下游排版 agent 的边界

可以做：

- 套学校/资助方模板：封面、目录、页边距、页眉页脚、字体字号、行距、图表编号；
- 把 `assets/` 里的图按 `proposal.md` 的占位插入；
- 按 `citation_style` 重排参考文献；
- 生成正式 DOCX/PDF；
- 在 `intl` 模式下翻译成英文并做语言润色。

不应做：

- 改研究目标、研究内容、创新点、结论；
- 删除或改写“待申请人补充/待核”标记；
- 把未核证据写成已核；
- 伪造样本量、统计功效、伦理批号、预算明细。

校验建议：比较 `content_sha256`、章节标题序列、正文字数区间、引文编号集合；任何一项变化都要记录为“排版 agent 修改”，不能静默覆盖。

## 5. 命令行与页面入口

```bash
litradar run --direction "研究方向" --proposal-mode cn
litradar run --direction "研究方向" --proposal-mode intl
litradar run --direction "研究方向" --proposal-mode intl --preview-docx
```

页面“报告结构”下拉框对应 `proposal_mode`；勾选“生成预览 Word（非正式排版）”才生成 `proposal.preview.docx`。
