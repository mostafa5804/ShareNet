$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tokens = $null
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
  (Join-Path $root 'runtime\lan_share.ps1'),
  [ref]$tokens,
  [ref]$errors
)
if ($errors.Count) {
  $errors | Format-List
  throw "PowerShell parser found $($errors.Count) error(s)."
}
Write-Host 'PowerShell syntax OK.' -ForegroundColor Green

