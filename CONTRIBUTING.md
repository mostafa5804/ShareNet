# Contributing

1. Open an issue before implementing a new router driver.
2. Identify the exact manufacturer, model, hardware revision, firmware version
   and UI language. A brand-level claim such as “all TP-Link routers” is not
   acceptable.
3. Never commit captured pages or logs containing credentials, IP addresses,
   MAC addresses, serial numbers, SSIDs or customer/company information.
4. Add unit tests and preserve the dry-run, read-back and rollback contract.
5. Run before submitting:

```powershell
python -m pytest -q
python -m ruff check src tests
.\scripts\security-check.ps1
```

Pull requests must explain what was tested on a real device and which behavior
was simulated or mocked.

