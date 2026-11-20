param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

# LitRadar 本地运行入口：固定把数据写到 D 盘，不落 C 盘用户目录
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:LITRADAR_HOME = Join-Path $Root "workspace"
$exe = Join-Path $Root ".venv\Scripts\litradar.exe"

if (-not (Test-Path $exe)) {
    Write-Error "找不到 $exe，请先运行 setup.ps1"
    exit 1
}
& $exe @Rest
