# Security Policy

## Supported version

Only the latest v1 release receives security fixes.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or exposed credential. Use the
repository's private security advisory feature:

`Security` → `Advisories` → `Report a vulnerability`

Include the affected version, impact, reproduction steps and a proposed fix if
available. Never include real router credentials, API keys, public IPs, MAC
addresses, serial numbers or SSIDs.

If a secret was committed, revoke or rotate it immediately. Removing a string
from the latest source file does not remove it from Git history.

## Design notes

- Router passwords are stored through Windows Credential Manager.
- Non-secret settings and rollback state remain under `%LOCALAPPDATA%\ShareNet`.
- Diagnostic export redacts obvious credentials, IP addresses, MAC addresses
  and the user home path; users must still inspect it before sharing.
- Network-changing operations require elevation and retain rollback state.

