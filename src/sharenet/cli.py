from __future__ import annotations

import argparse
import getpass
import json

from .config import load_config
from .credentials import get_password
from .engine import detect_windows_network, run_engine
from .service import disable, dry_run, enable


def main() -> int:
    parser = argparse.ArgumentParser(prog="sharenet")
    parser.add_argument("action", choices=["detect", "dry-run", "status", "enable", "disable"])
    args = parser.parse_args()
    cfg = load_config()
    if args.action == "detect":
        print(json.dumps(detect_windows_network(), ensure_ascii=False, indent=2))
        return 0
    if args.action == "status":
        print(run_engine("status", cfg))
        return 0
    password = None
    if cfg["router"].get("driver") != "manual":
        password = get_password(cfg["router"]["base_url"], cfg["router"].get("username", "admin"))
        if not password:
            password = getpass.getpass("Router password: ")
    if args.action == "dry-run":
        print(dry_run(cfg, password).format_fa())
    elif args.action == "enable":
        print(enable(cfg, password))
    else:
        print(disable(cfg, password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
