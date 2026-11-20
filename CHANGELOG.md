# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.4.0] - 2026-11-20

### Added
- 结构化卡片抽取：9 字段 + `evidence` 引文，引文必须在归一化原文中命中，否则标“待核”
- 跨文献聚合：共识 / 争议 / 空白 / 图表套路 / 3–5 个方向候选
- 六件套简报：领域全景、证据矩阵、单篇卡片、图表复刻清单、方向候选、开题卡
- 本地 Web 界面（`litradar serve`，默认 8899）：表单、进度条、六页签、下载
- DSH 插件 `litradar-dsh-plugin`：左侧栏入口 + 面板 + 引擎托管，随 DSH 起停
- **DSH 模型发现**（`model_catalog.py`）：读 `~/.dsh/profiles/*/cordis.patch.yml` 的 providers，
  合并官方 DeepSeek `/v1/models` 实时探测，`/api/models` 输出全部可选模型，UI 下拉随之动态生成
- 模型路由：按 provider 的 `baseURL` + `apiKeyEnv` 取 Key，Key 一律复用 DSH 凭据，插件不再二次填写
- 分发打包：`scripts/pack.ps1` 产出 `dist/`（插件 tgz + 引擎 zip + 安装/卸载脚本 + 说明）

### Changed
- `DEFAULT_MODEL` 改为 `deepseek-flash`
- `llm.resolve_model` 改为走模型目录路由，不再写死两家

## [0.3.0] - 2026-11-20

### Added
- 卡片 / 聚合 / 简报 / 本地 Web 界面 / DSH 插件初版

## [0.2.0] - 2026-11-20

### Added
- `litradar fetch`：抓取 Europe PMC 开放获取文献的全文 XML，落盘并写入 `fulltext` 表
- JATS 解析：正文、图/表条目、图注、PMC CDN 原图直链
- 正文引用句配对：支持 `Fig. 1`、`Figs. 2, 3 and 4`、`Figs. 1–3` 与 `Table 1`
- `litradar list-figures`：查看图号、图注、原图链接与引用句
- 限速、失败重试、断点续跑；单篇失败不影响整批
- Windows 系统代理自动探测（Clash 等），命令行无需再设环境变量
- 新增 `litradar.cmd` 本地启动器，系统 Python 直接跑，不依赖虚拟环境

### Changed
- `stats` 增加“已抓全文”“图表条目”两项
- `--db` 现在既可写在子命令前，也可写在子命令后

## [0.1.0] - 2026-11-20

### Added
- Europe PMC 检索客户端，支持 cursor 分页与失败重试
- PICO 四格转布尔检索式，支持同义词与年份窗口
- SQLite 本地库，按 DOI/id 去重
- CLI：`search` / `stats` / `export` / `list`
- 离线单测与 GitHub Actions CI
