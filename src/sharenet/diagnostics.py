from __future__ import annotations

import json
import platform
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .config import CONFIG_PATH, LOG_DIR
from .sanitize import sanitize_text


def export_sanitized(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("system.json", json.dumps(report, indent=2))
        if CONFIG_PATH.exists():
            archive.writestr(
                "config.sanitized.json", sanitize_text(CONFIG_PATH.read_text(encoding="utf-8"))
            )
        if LOG_DIR.exists():
            for path in LOG_DIR.glob("*.log"):
                archive.writestr(
                    f"logs/{path.name}",
                    sanitize_text(path.read_text(encoding="utf-8", errors="replace")),
                )
    return destination
