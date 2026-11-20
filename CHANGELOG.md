# Changelog

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Planned
- OA 全文抓取与图注解析
- 卡片抽取与证据定位
- 领域聚合与方向候选
- 本地 Web 界面
- DSH 插件

## [0.1.0] - 2026-11-20

### Added
- Europe PMC 检索客户端，支持 cursor 分页与失败重试
- PICO 四格转布尔检索式，支持同义词与年份窗口
- SQLite 本地库，按 DOI/id 去重
- CLI：`search` / `stats` / `export` / `list`
- 离线单测与 GitHub Actions CI
