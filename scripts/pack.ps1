# 打出可分发的安装包：dist\ 下生成 tgz + 引擎压缩包 + 安装/卸载脚本
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

# 1) 插件包
Push-Location (Join-Path $Root "dsh-plugin")
try {
  npm pack --pack-destination $Dist
  if ($LASTEXITCODE -ne 0) { throw "npm pack 失败" }
} finally { Pop-Location }

# 2) 引擎压缩包（只带运行时需要的文件）
$Stage = Join-Path $Dist "_stage"
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Copy-Item (Join-Path $Root "src") $Stage -Recurse
Get-ChildItem -Path $Stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $Stage -Recurse -File -Include *.pyc,*.pyo | Remove-Item -Force
Copy-Item (Join-Path $Root "pyproject.toml") $Stage
Copy-Item (Join-Path $Root "litradar.cmd") $Stage
Copy-Item (Join-Path $Root "run.ps1") $Stage
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath (Join-Path $Dist "litradar-engine.zip") -Force
Remove-Item $Stage -Recurse -Force

# 3) 安装/卸载脚本与说明
Copy-Item (Join-Path $Root "packaging\install.ps1") $Dist
Copy-Item (Join-Path $Root "packaging\uninstall.ps1") $Dist
Copy-Item (Join-Path $Root "packaging\安装与卸载.md") (Join-Path $Dist "README.md")

Get-ChildItem $Dist | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 2) } } | Format-Table -AutoSize | Out-String
