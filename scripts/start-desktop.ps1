param([switch]$NoBrain)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$uv = if (Get-Command uv -ErrorAction SilentlyContinue) { 'uv' } else { Join-Path $repo '.tools\uv\uv.exe' }
if (-not (Get-Command $uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' }
$env:PYTHONUTF8 = '1'
$arguments = @('run', '--project', (Join-Path $repo 'brain'), '--extra', 'desktop', 'milo-desktop')
if ($NoBrain) { $arguments += '--no-brain' }
& $uv @arguments
exit $LASTEXITCODE
