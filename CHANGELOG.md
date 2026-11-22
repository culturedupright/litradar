# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.7.0] - 2026-11-22

### Added
- 多检索源：Europe PMC / PubMed / OpenAlex / Web of Science / Scopus，界面自由勾选，逐源体检
- 凭据管理：WOS / Scopus API Key 存本机 `credentials.json`，支持有效期，过期自动停用并提示重配
- OECD 学科分类（Frascati 2007，六大类 42 子类）接入界面，用于定闸门口径与卡片语义
- 课题组五维自评（PI / 平台 / 积累 / 梯队 / 经费），带权重、锚点、短板结论，写进开题报告
- 开题报告交付：九节骨架 + 三份附录，Markdown 与 Word 双格式（Word 依赖 python-docx，缺失时自动跳过）
- 界面新增检索源状态、凭据表单、课题组滑杆、开题报告页签与下载

### Changed
- 检索式规划同时产出 `keywords`，供不支持布尔语法的库使用
- 检索源单点失败不再中断整轮；全部失败才报错并列出每家原因
- 汇总报告与 summary.json 记录逐源数量与 OECD 口径

### Fixed
- 模型返回 JSON 字符串里带裸换行时解析失败（`strict=False` 兜底）
- 材料方向把“biological neural networks / in vivo”类文献误放行

## [0.6.0] - 2026-11-22

### Added
- 学科判定（`domain.py`）：材料与器件 / 植物—微生物 / 生物医学 / 通用四套档案，按词表投票自动判，0 命中或多方平票退回通用
- 相关性闸门（`relevance.py`）：主题词 + 标题 + 学科词加分，干扰词扣分，低于阈值挡掉并给出理由
- 检索体检：简报开头新增候选/同域/挡掉/保留率/阈值/期刊分布/年份跨度/被挡样例
- 检索式自动放宽：0 命中时从尾部逐个去掉 `AND` 组重试，最多 3 次
- 材料学科使用 PSPP 口径，卡片九字段描述改为“制备—表征—测试”，不再出现“盆栽”
- 学科下拉框（CLI `--domain`、Web 表单），可强制指定 auto/materials/agri/biomed/general

### Changed
- 卡片与聚合的提示词按学科参数化，键名不变，旧数据兼容
- 本轮运行只抓本轮候选的全文、只聚合本轮生成的卡片，不再把历史库里别的方向卡片拉进来
- `papers` 表新增 `relevance`、`gate`、`gate_reason`，旧库自动补列，默认放行
- 模型输出字段统一用中文（专有名词可保留英文），引句仍保留英文原文
- 全文抓取在 Europe PMC 返回 500 时自动退到 NCBI efetch 取同一份 JATS

### Fixed
- “rat” 误命中 “integrated”、“plant” 误命中 “implant” 之类的整词匹配假阳性
- 聚合阶段没有卡片仍调用模型、凭空编结论的问题

## [0.5.0] - 2026-11-20

### Added
- 进度面板新增实时活动日志：每个阶段、每篇全文/卡片、每次模型请求（含第几次重试、tokens、耗时）都带时间戳滚动显示
- 进度面板新增实时心跳：“已运行 1:31 · 本步已等 0:14”，超过 25 秒会提示“模型还在返回，页面没死”——卡在长请求时不再像假死

### Changed
- `llm.chat` 增加活动回调（`set_activity`），重试不再静默
- `run_pipeline` 增加 `note` 回调，抓全文/抽卡片/聚合/写简报都有细粒度事件

## [0.4.2] - 2026-11-20

### Changed
- 输入框示例改为中性表述：“根系分泌物如何塑造根际微生物组的组成与功能”

## [0.4.1] - 2026-11-20

### Changed
- 年份范围从单行文本框改成两个原生日期选择器（起 / 止），带日历图标，起止不得倒置

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
