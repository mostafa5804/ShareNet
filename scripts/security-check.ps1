[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$patterns = @(
  '(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*[^\s"'']+',
  'C:\\Users\\[^\\\s]+',
  '(?i)(ssid|serial|mac.?address)\s*[=:]\s*[^\s]+'
)

$files = Get-ChildItem -Recurse -File | Where-Object {
  $_.FullName -notmatch '\\(\.git|build|dist|\.venv|__pycache__)\\' -and
  $_.FullName -notmatch '\\tests\\' -and
  $_.Name -notin '.env.example', 'security-check.ps1' -and
  $_.Extension -notin '.exe', '.dll', '.pyc', '.png', '.ico'
}
$hits = foreach ($file in $files) {
  foreach ($pattern in $patterns) {
    Select-String -Path $file.FullName -Pattern $pattern -AllMatches -ErrorAction SilentlyContinue
  }
}
if ($hits) {
  $hits | ForEach-Object { "{0}:{1}: {2}" -f $_.Path, $_.LineNumber, $_.Line.Trim() }
  throw 'Potential sensitive values were found. Review the matches before publishing.'
}
Write-Host 'No obvious sensitive values found.' -ForegroundColor Green
