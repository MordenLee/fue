param([Parameter(ValueFromRemainingArguments = $true)][string[]]$FueArguments)
$ErrorActionPreference = 'Stop'
$registryPath = if ($env:FUE_REGISTRY_PATH) { $env:FUE_REGISTRY_PATH } else { Join-Path $env:APPDATA 'fue\installation.json' }
$localConnection = Join-Path (Split-Path $PSScriptRoot -Parent) 'connection.json'
if ($env:FUE_PYTHON) {
    $fuePython = $env:FUE_PYTHON
} elseif (Test-Path -LiteralPath $localConnection) {
    $connection = Get-Content -LiteralPath $localConnection -Raw -Encoding UTF8 | ConvertFrom-Json
    $fuePython = $connection.python
}
if (-not $fuePython -and (Test-Path -LiteralPath $registryPath)) {
    $installation = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $fuePython = $installation.runtimes.($installation.default_runtime).python
}
if (-not $fuePython -or -not (Test-Path -LiteralPath $fuePython)) {
    throw 'Registered Python is missing. Repair the FUE runtime; do not create a new workspace.'
}
& $fuePython (Join-Path $PSScriptRoot 'fue.py') @FueArguments
exit $LASTEXITCODE
