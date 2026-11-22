param(
  [ValidateSet("web", "desktop", "both")]
  [string]$Profile = "both",
  [string]$EngineDir = "$env:LOCALAPPDATA\LitRadar\engine",
  [string]$DataDir = "",
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tgz = Get-ChildItem $Here -Filter "litradar-dsh-plugin-*.tgz" | Sort-Object Name -Descending | Select-Object -First 1
if (-not $Tgz) { throw "同目录下找不到 litradar-dsh-plugin-*.tgz" }
$EngineZip = Join-Path $Here "litradar-engine.zip"
if (-not (Test-Path $EngineZip)) { throw "同目录下找不到 litradar-engine.zip" }

Write-Host "1/4 解压引擎到 $EngineDir"
New-Item -ItemType Directory -Force -Path $EngineDir | Out-Null
Expand-Archive -Path $EngineZip -DestinationPath $EngineDir -Force

if (-not $Python) {
  $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $Python -or $Python -like "*WindowsApps*") {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending | Select-Object -First 1
    if ($found) { $Python = $found.FullName }
  }
  if (-not $Python -or $Python -like "*WindowsApps*") {
    throw "没找到可用的 Python。请先装 Python 3.10+ 并勾选 Add to PATH，或重跑：.\install.ps1 -Python `"C:\你的\python.exe`""
  }
}

& $Python -c "import docx" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "提示：未装 python-docx，Word 版开题报告会跳过。要 Word 版请执行："
  Write-Host "  `"$Python`" -m pip install python-docx"
}

Write-Host "2/4 写入引擎配置 ~/.litradar-suite/config.json"
$SuiteDir = Join-Path $env:USERPROFILE ".litradar-suite"
New-Item -ItemType Directory -Force -Path $SuiteDir | Out-Null
if (-not $DataDir) { $DataDir = Join-Path $SuiteDir "data" }
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$Config = [ordered]@{
  engine = $EngineDir
  python = $Python
  data   = $DataDir
}
$Config | ConvertTo-Json | Set-Content -Path (Join-Path $SuiteDir "config.json") -Encoding UTF8

function Add-Bundle([string]$Name) {
  $file = Join-Path $env:USERPROFILE ".dsh\profiles\$Name\package.json"
  if (-not (Test-Path $file)) { Write-Host "跳过：profile $Name 不存在"; return }
  $json = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json
  $bundles = @($json.dsh.profile.bundles)
  if ($bundles -notcontains "litradar-dsh-plugin") {
    $json.dsh.profile.bundles = @($bundles + "litradar-dsh-plugin")
    $json | ConvertTo-Json -Depth 10 | Set-Content -Path $file -Encoding UTF8
    Write-Host "   已把 litradar-dsh-plugin 追加到 profile $Name 的 bundles"
  }
}

Write-Host "3/4 安装插件到 profile：$Profile"
if ($Profile -in @("web", "both")) {
  & dsh plugin --profile web add $Tgz.FullName
  if ($LASTEXITCODE -ne 0) { throw "web profile 安装失败" }
  Add-Bundle "web"
}
if ($Profile -in @("desktop", "both")) {
  $desktop = Join-Path $env:USERPROFILE ".dsh\profiles\desktop"
  if (-not (Test-Path $desktop)) { throw "桌面版 profile 不存在：$desktop" }
  Push-Location $desktop
  try {
    pnpm add "$($Tgz.FullName)"
    if ($LASTEXITCODE -ne 0) { throw "桌面版 profile 安装失败（先完全退出 DSH 再试）" }
  } finally { Pop-Location }
  Add-Bundle "desktop"
}

Write-Host "4/4 完成"
Write-Host ""
Write-Host "验证："
Write-Host "  dsh --profile web --dump-config | Select-String litradar"
Write-Host "  打开 DSH → 左侧栏「题眼 LitRadar」→ 状态点应为绿色"
Write-Host "  引擎地址：http://127.0.0.1:8899/api/health"
