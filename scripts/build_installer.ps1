# 构建 Windows 一键安装器：内部含独立引擎 EXE + DSH 插件包 + 引擎源码包
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Py = "C:\Users\1\AppData\Local\Programs\Python\Python313\python.exe"
$Version = (Get-Content (Join-Path $Root "dsh-plugin\package.json") -Raw | ConvertFrom-Json).version

if (-not (Test-Path (Join-Path $Dist "litradar-engine.exe"))) {
  Push-Location $Root
  try {
    & $Py -m PyInstaller --noconfirm --clean --onefile --noconsole --name litradar-engine `
      --paths src --hidden-import yaml --collect-all docx --collect-all pypinyin `
      --add-data "src\litradar\data;litradar\data" `
      --distpath (Join-Path $Dist "exe") --workpath (Join-Path $Root "build") `
      packaging\engine_entry.py
    if ($LASTEXITCODE -ne 0) { throw "引擎 EXE 构建失败" }
  } finally { Pop-Location }
  Copy-Item (Join-Path $Dist "exe\litradar-engine.exe") (Join-Path $Dist "litradar-engine.exe") -Force
}
foreach ($name in @("litradar-engine.zip", "litradar-dsh-plugin-$Version.tgz")) {
  if (-not (Test-Path (Join-Path $Dist $name))) { throw "缺少 $name，请先跑 scripts\pack.ps1" }
}

Push-Location $Root
try {
  & $Py -m PyInstaller --noconfirm --clean --onefile --windowed --name "LitRadar-Setup-$Version" `
    --add-data "$(Join-Path $Dist 'litradar-engine.exe');assets" `
    --add-data "$(Join-Path $Dist 'litradar-engine.zip');assets" `
    --add-data "$(Join-Path $Dist "litradar-dsh-plugin-$Version.tgz");assets" `
    --distpath (Join-Path $Dist "setup") --workpath (Join-Path $Root "build") `
    packaging\install_exe.py
  if ($LASTEXITCODE -ne 0) { throw "安装器构建失败" }
} finally { Pop-Location }

$out = Join-Path $Dist "setup\LitRadar-Setup-$Version.exe"
Copy-Item $out (Join-Path $Dist "LitRadar-Setup-$Version.exe") -Force
Get-Item (Join-Path $Dist "LitRadar-Setup-$Version.exe") | Select-Object FullName, Length
