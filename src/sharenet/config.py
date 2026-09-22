from __future__ import annotations

import ipaddress
import json
import os
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ShareNet"
CONFIG_PATH = APP_DIR / "config.json"
BACKUP_PATH = APP_DIR / "router_backup.json"
LOG_DIR = APP_DIR / "logs"
RUNTIME_DIR = APP_DIR / "runtime"

DEFAULT_CONFIG = {
    "schema_version": 1,
    "router": {
        "driver": "tp_link_archer_c80",
        "base_url": "http://192.168.1.1",
        "username": "admin",
    },
    "network": {
        "lan_cidr": "192.168.1.0/24",
        "pc_ip": "192.168.1.250",
        "router_ip": "192.168.1.1",
    },
    "proxy": {"address": "127.0.0.1", "port": 10808},
}


def ensure_dirs() -> None:
    for path in (APP_DIR, LOG_DIR, RUNTIME_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    cfg = deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for section in ("router", "network", "proxy"):
            cfg[section].update(data.get(section, {}))
    apply_env(cfg)
    return cfg


def apply_env(cfg: dict) -> None:
    mapping = {
        "SHARENET_ROUTER_URL": ("router", "base_url"),
        "SHARENET_ROUTER_USERNAME": ("router", "username"),
        "SHARENET_PC_IP": ("network", "pc_ip"),
        "SHARENET_LAN_CIDR": ("network", "lan_cidr"),
    }
    for name, (section, key) in mapping.items():
        if os.environ.get(name):
            cfg[section][key] = os.environ[name]
    if os.environ.get("SHARENET_SOCKS_ADDR"):
        host, port = os.environ["SHARENET_SOCKS_ADDR"].rsplit(":", 1)
        cfg["proxy"].update(address=host, port=int(port))


def validate_config(cfg: dict) -> None:
    parsed = urlparse(cfg["router"]["base_url"])
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("آدرس مودم باید با http:// یا https:// شروع شود.")
    router_ip = ipaddress.ip_address(cfg["network"]["router_ip"])
    pc_ip = ipaddress.ip_address(cfg["network"]["pc_ip"])
    lan = ipaddress.ip_network(cfg["network"]["lan_cidr"], strict=False)
    if router_ip not in lan or pc_ip not in lan:
        raise ValueError("IP مودم و IP کامپیوتر باید داخل محدوده LAN باشند.")
    if router_ip == pc_ip:
        raise ValueError("IP مودم و IP کامپیوتر نمی‌توانند یکسان باشند.")
    port = int(cfg["proxy"]["port"])
    if not 1 <= port <= 65535:
        raise ValueError("پورت SOCKS5 معتبر نیست.")


def recommend_pc_ip(lan_cidr: str, router_ip: str) -> str:
    """Suggest a high usable address in the detected subnet.

    The address is only a proposal; collision checking still happens before
    the network is changed because the DHCP pool is router-specific.
    """
    lan = ipaddress.ip_network(lan_cidr, strict=False)
    gateway = ipaddress.ip_address(router_ip)
    if lan.version != 4 or lan.num_addresses < 8:
        raise ValueError("محدوده شناسایی‌شده برای انتخاب خودکار IP مناسب نیست.")
    for offset in range(5, min(32, lan.num_addresses - 1)):
        candidate = lan.broadcast_address - offset
        if candidate != gateway and candidate not in {lan.network_address, lan.broadcast_address}:
            return str(candidate)
    raise ValueError("IP پیشنهادی مناسبی در محدوده LAN پیدا نشد.")


def save_config(cfg: dict) -> None:
    validate_config(cfg)
    ensure_dirs()
    clean = deepcopy(cfg)
    clean.pop("password", None)
    clean.get("router", {}).pop("password", None)
    CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def save_router_backup(data: dict) -> None:
    ensure_dirs()
    BACKUP_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_router_backup() -> dict | None:
    if not BACKUP_PATH.exists():
        return None
    return json.loads(BACKUP_PATH.read_text(encoding="utf-8"))


def delete_router_backup() -> None:
    BACKUP_PATH.unlink(missing_ok=True)
