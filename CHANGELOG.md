# Changelog

## 1.0.0

- Added a Windows x64 GUI for configuration and status.
- Added TP-Link Archer C80 English-interface driver.
- Stored router credentials with Windows Credential Manager.
- Added automatic network detection, dry run, read-back and rollback state.
- Moved configuration, logs and runtime state to `%LOCALAPPDATA%\ShareNet`.
- Added sanitized diagnostic export.
- Added tests, Gitleaks CI, tagged GitHub Releases and SHA-256 output.
- Fixed automatic PC address selection after detecting a different LAN subnet.
- Allowed the bundled PowerShell helper to run with process-scoped ExecutionPolicy Bypass.
- Added automatic UAC elevation when running directly from Python source.
- Fixed direct launcher imports for the `src` project layout and added `RUN_APP.bat`.
- Added `Other Router — Manual Setup` with safe ordered enable/restore guidance.
- Added a documented router compatibility matrix based on DHCP option support.
