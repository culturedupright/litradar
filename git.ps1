param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

# 优先用系统 Git；没装则回退到 D 盘便携版
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$systemGit = "C:\Program Files\Git\cmd\git.exe"
$portableGit = "D:\Projects\_tools\MinGit\cmd\git.exe"

if (Test-Path $systemGit) {
    $git = $systemGit
} elseif (Test-Path $portableGit) {
    $git = $portableGit
} else {
    Write-Error "没有找到 git.exe"
    exit 1
}
& $git -C $Root @Rest
