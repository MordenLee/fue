param([Parameter(ValueFromRemainingArguments = $true)][string[]]$InstallArguments)
$ErrorActionPreference = 'Stop'
$bundledPython = Join-Path $PSScriptRoot 'python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython (Join-Path $PSScriptRoot 'install.py') @InstallArguments
} else {
    & python (Join-Path $PSScriptRoot 'install.py') @InstallArguments
}
exit $LASTEXITCODE
