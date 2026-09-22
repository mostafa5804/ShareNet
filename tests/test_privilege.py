from pathlib import Path

from sharenet import privilege


def test_source_elevation_target_contains_absolute_script(monkeypatch):
    monkeypatch.delattr(privilege.sys, "frozen", raising=False)
    monkeypatch.setattr(privilege.sys, "argv", ["launcher.py", "--example"])
    executable, parameters = privilege.elevation_target()
    assert executable == privilege.sys.executable
    assert str(Path("launcher.py").resolve()) in parameters
    assert "--example" in parameters


def test_non_windows_does_not_request_elevation(monkeypatch):
    monkeypatch.setattr(privilege.os, "name", "posix")
    assert privilege.relaunch_as_admin_if_needed() is False
