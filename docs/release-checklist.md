# Release checklist

1. Test `Dry Run`, enable, status and disable on the supported real router.
2. Confirm that Windows and router settings return to their original values.
3. Run `python -m pytest -q` and `python -m ruff check src tests`.
4. Run `tests\powershell_syntax.ps1` and `scripts\security-check.ps1`.
5. Inspect all tracked files with `git status` and `git diff --cached`.
6. Enable GitHub Secret Scanning and Push Protection in repository settings.
7. Push `main` and wait for the Test workflow to pass.
8. Create an annotated version tag, for example:

```bash
git tag -a v1.0.0 -m "ShareNet v1.0.0"
git push origin v1.0.0
```

9. Download the generated EXE from the draft/release page, verify
   `SHA256SUMS.txt`, and perform a clean Windows VM smoke test.
10. Publish or announce the release only after the clean VM test passes.

