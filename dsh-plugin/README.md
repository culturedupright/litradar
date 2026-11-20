# 题眼 LitRadar · DSH 插件

把 LitRadar 挂进 DeepSeek Harness 左侧栏的插件层。整个产品仍然是一套本地引擎（Python，`127.0.0.1:8899`），插件只负责三件事：

1. 在 DSH 启动时检查引擎是否在跑，没跑就拉起来；
2. 在左侧栏注册一个「题眼 LitRadar」入口；
3. 点击入口后，在主区域嵌入引擎自带的界面。

因此它不脱离 DSH 独立运行，也没有第二套 Key：模型调用沿用引擎读取的 DSH 凭据（`~/.dsh/.credentials.yaml` 的 `DEEPSEEK_API_KEY`），面板里不需要再填一次。

## 装法

```powershell
dsh plugin --profile web add "link:D:/Projects/LitRadar/dsh-plugin"
```

`dsh plugin` 会把包写进 profile 的依赖，并把包名追加到 `dsh.profile.bundles`。包内 `cordis.patch.yml` 负责把插件本体插进 Loader 树，`dsh.client` 声明负责把 `lib/client.js` 发布成浏览器 bundle。

## 目录

| 文件 | 作用 |
|---|---|
| `lib/index.js` | 宿主侧：探活 + 拉起 Python 引擎，随 DSH 退出而停 |
| `lib/client.js` | 浏览器侧：左侧栏图标 + 主面板（工具条 + iframe 嵌入） |
| `cordis.patch.yml` | 挂载行 `id: litradar` |

## 可调环境变量

| 变量 | 默认值 |
|---|---|
| `LITRADAR_HOME` | `D:\Projects\LitRadar` |
| `LITRADAR_PORT` | `8899` |
| `LITRADAR_PYTHON` | `C:\Users\1\AppData\Local\Programs\Python\Python313\python.exe` |

## 验证清单

1. `dsh --profile web --dump-config` 里能看到 `- id: litradar`；
2. 启动 DSH 后左侧栏出现「题眼 LitRadar」；
3. 点进去状态点是绿的、显示 `本地引擎 · deepseek-chat`；
4. 面板里直接填方向、点「开始分析」，进度条和六页签都在 DSH 内完成。
