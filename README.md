# LitRadar · 题眼

> 从一个研究方向，到一套能开题的证据包。

输入一句话方向（可选平台、预算、周期），输出六件东西：领域全景、证据矩阵、单篇卡片、图表复刻清单、方向候选、开题卡。

**当前状态：`v0.1.0`，只有检索层可跑。** 卡片抽取、聚合、界面、DSH 插件都在路线图里，不假装已完成。

## 它解决什么

读文献最耗时的不是找，而是判断：

- 这个领域哪些已经做透了，哪些还在争？
- 每篇文章到底怎么设计的，n 是多少，测了什么？
- 这张图我能不能复刻，需要什么数据？
- 我现在的条件，能做哪几个方向？

LitRadar 把这几件事做成一条流水线，每条结论都要求带证据定位（页码/图号/原文引句），没有定位的进“待核”，不混进结论。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

要求 Python 3.10+，运行时只用标准库，不额外装依赖。

## 用法

```bash
# 直接检索
litradar search --query "coumarin AND rhizosphere" --limit 60

# 用 PICO 四格拼检索式（同义词用 | 分隔）
litradar search \
  --pico population="Oxytropis ochrocephala|黄花棘豆" intervention="endophyte|内生真菌" \
  --years 2012-2026 --limit 60

# 看库内统计、导出
litradar stats
litradar export --out papers.csv
```

默认库在 `~/.litradar/data/litradar.db`，可用 `LITRADAR_HOME` 或 `--db` 改。

## 数据与边界

- 只检索 **Europe PMC / PMC 开放获取** 英文文献；中文库没有公开接口，不在 MVP 范围。
- 卡片必须带证据定位；没有就标“待核”。
- 不生成不存在的文献、数据、图。
- 只给图表复刻方案，不生成成品图。
- 方向建议是候选，不是结论。

## 路线图

| 版本 | 内容 | 状态 |
| --- | --- | --- |
| v0.1.0 | Europe PMC 检索、PICO 检索式、SQLite、CSV 导出、测试与 CI | ✅ |
| v0.2.0 | OA 全文与图注抓取（JATS XML + `cloudpmc-path` CDN） | 计划中 |
| v0.3.0 | 结构化卡片抽取（9 字段 + 证据定位） | 计划中 |
| v0.4.0 | 领域聚合 + 方向候选 + 开题卡 | 计划中 |
| v0.5.0 | 本地 Web 界面 + 导出 Markdown/Excel/PDF | 计划中 |
| v0.6.0 | DSH 插件：左侧栏入口 + 面板 | 计划中 |

## 仓库结构

```
src/litradar/      # 引擎（检索、存储、后续流水线）
tests/             # 离线单测，不依赖网络
scripts/           # 一次性数据采集脚本
docs/              # 架构与插件说明
.github/workflows/ # CI 与 Release
```

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md)。提交用语义化前缀：`feat:`、`fix:`、`docs:`、`test:`、`chore:`。

## License

MIT
