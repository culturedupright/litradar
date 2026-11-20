param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

# 使用 D 盘内的便携版 Git，不依赖系统安装
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$git = "D:\Projects\_tools\MinGit\cmd\git.exe"
& $git -C $Root @Rest
