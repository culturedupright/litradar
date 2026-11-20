param(
  [ValidateSet("web", "desktop", "both")]
  [string]$Profile = "both",
  [switch]$PurgeData
)

$ErrorActionPreference = "Continue"
$HomeDsh = Join-Path $env:USERPROFILE ".dsh"

function Remove-Bundle([string]$Name) {
  $file = Join-Path $HomeDsh "profiles\$Name\package.json"
  if (-not (Test-Path $file)) { return }
  $json = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json
  $bundles = @($json.dsh.profile.bundles) | Where-Object { $_ -ne "litradar-dsh-plugin" }
  $json.dsh.profile.bundles = @($bundles)
  $json | ConvertTo-Json -Depth 10 | Set-Content -Path $file -Encoding UTF8
  Write-Host "   已从 profile $Name 的 bundles 移除"
}

Write-Host "卸载插件（profile：$Profile）"
if ($Profile -in @("web", "both")) {
  & dsh plugin --profile web remove litradar-dsh-plugin
  Remove-Bundle "web"
}
if ($Profile -in @("desktop", "both")) {
  $desktop = Join-Path $HomeDsh "profiles\desktop"
  if (Test-Path $desktop) {
    Push-Location $desktop
    try { pnpm remove litradar-dsh-plugin } finally { Pop-Location }
  }
  Remove-Bundle "desktop"
}

if ($PurgeData) {
  $SuiteDir = Join-Path $env:USERPROFILE ".litradar-suite"
  if (Test-Path $SuiteDir) { Remove-Item $SuiteDir -Recurse -Force }
  Write-Host "   已删除 ~/.litradar-suite（引擎路径配置）"
  Write-Host "   数据目录未删：如需清空，手动删除配置文件里 data 指向的目录"
}

Write-Host ""
Write-Host "完成后请完全退出并重开 DSH，左侧栏入口即消失。"
