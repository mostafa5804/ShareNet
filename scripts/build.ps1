[CmdletBinding()]
param([switch]$Clean)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Clean) {
  Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check src tests
python -m PyInstaller --noconfirm --clean ShareNet.spec

$exe = Join-Path $root 'dist\ShareNet-v1.0.0-Windows-x64.exe'
if (-not (Test-Path $exe)) { throw "Build completed but EXE was not found: $exe" }
Get-FileHash $exe -Algorithm SHA256 | Format-List

