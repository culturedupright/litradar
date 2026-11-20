param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

# LitRadar 本地运行入口：固定把数据写到 D 盘，并走系统 Python（不依赖虚拟环境）
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:LITRADAR_HOME = Join-Path $Root "workspace"
& (Join-Path $Root "litradar.cmd") @Rest
