from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from .config import LOG_DIR, RUNTIME_DIR, ensure_dirs


class EngineError(RuntimeError):
    pass


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def install_runtime() -> Path:
    """Copy immutable bundled helpers to a durable per-user directory."""
    ensure_dirs()
    source = bundle_root() / "runtime"
    if not source.exists():
        raise EngineError(f"فایل‌های runtime پیدا نشدند: {source}")
    version_file = RUNTIME_DIR / "VERSION"
    wanted = (source / "VERSION").read_text(encoding="utf-8").strip()
    current = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else ""
    required = ("VERSION", "lan_share.ps1", "zeptun.exe", "wintun.dll")
    if current != wanted or any(not (RUNTIME_DIR / name).exists() for name in required):
        for item in source.iterdir():
            target = RUNTIME_DIR / item.name
            if item.is_file():
                shutil.copy2(item, target)
    return RUNTIME_DIR


def _ps_args(action: str, cfg: dict) -> list[str]:
    runtime = install_runtime()
    proxy = f"{cfg['proxy']['address']}:{int(cfg['proxy']['port'])}"
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        # The script is bundled with this application and extracted locally.
        # Process-scoped Bypass avoids machine/user policy changes and does not
        # relax execution policy outside this one PowerShell process.
        "Bypass",
        "-File",
        str(runtime / "lan_share.ps1"),
        action,
        "-LanCidr",
        cfg["network"]["lan_cidr"],
        "-RouterIp",
        cfg["network"]["router_ip"],
        "-PcIp",
        cfg["network"]["pc_ip"],
        "-SocksAddr",
        proxy,
        "-StateRoot",
        str(RUNTIME_DIR.parent),
    ]


def run_engine(action: str, cfg: dict, timeout: int = 150) -> str:
    if os.name != "nt":
        raise EngineError("موتور شبکه فقط روی Windows اجرا می‌شود.")
    completed = subprocess.run(
        _ps_args(action, cfg),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    log = LOG_DIR / "engine.log"
    log.write_text(output[-200_000:], encoding="utf-8")
    if completed.returncode:
        raise EngineError(output or f"موتور شبکه با کد {completed.returncode} متوقف شد.")
    return output


def proxy_reachable(cfg: dict, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(
            (cfg["proxy"]["address"], int(cfg["proxy"]["port"])), timeout=timeout
        ):
            return True
    except OSError:
        return False


def detect_windows_network() -> dict:
    if os.name != "nt":
        return {}
    command = (
        "$r=Get-NetRoute -DestinationPrefix '0.0.0.0/0' -AddressFamily IPv4 "
        "| Sort-Object RouteMetric | Select-Object -First 1;"
        "$i=Get-NetIPAddress -InterfaceIndex $r.InterfaceIndex -AddressFamily IPv4 "
        "| Where-Object {$_.IPAddress -notlike '169.254.*'} | Select-Object -First 1;"
        "[pscustomobject]@{gateway=$r.NextHop;ip=$i.IPAddress;prefix=$i.PrefixLength;"
        "adapter=$r.InterfaceAlias}|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        errors="replace",
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise EngineError("Default Gateway ویندوز شناسایی نشد.")
    return json.loads(result.stdout)
