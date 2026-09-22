from __future__ import annotations

from dataclasses import dataclass

from .config import (
    delete_router_backup,
    load_router_backup,
    save_router_backup,
)
from .engine import EngineError, proxy_reachable, run_engine
from .routers.base import DhcpSettings, RouterError
from .routers.c80 import ArcherC80Driver


@dataclass
class Plan:
    current: DhcpSettings
    pc_ip: str
    router_ip: str
    lan_cidr: str
    socks: str
    proxy_ok: bool

    def format_fa(self) -> str:
        proxy_state = "در دسترس" if self.proxy_ok else "در دسترس نیست"
        if self.current.default_gateway == "تنظیم دستی":
            final_note = (
                "در مرحله اجرا فقط بخش Windows و تونل فعال می‌شود؛ سپس باید Gateway و DNS "
                "نمایش‌داده‌شده را دستی در DHCP Server مودم وارد کنید."
            )
        else:
            final_note = (
                "در مرحله اجرا، ابتدا وضعیت فعلی ذخیره می‌شود. اگر تنظیم مودم شکست بخورد، "
                "تغییرات ویندوز به‌طور خودکار بازگردانده خواهد شد."
            )
        return (
            "پیش‌نمایش تغییرات — هنوز هیچ تغییری اعمال نشده است\n\n"
            f"Gateway فعلی DHCP مودم: {self.current.default_gateway or '(خالی)'}\n"
            f"DNS فعلی DHCP مودم: {self.current.primary_dns or '(خالی)'}\n"
            f"Gateway جدید دستگاه‌ها: {self.pc_ip}\n"
            f"DNS جدید دستگاه‌ها: {self.router_ip}\n"
            f"محدوده LAN: {self.lan_cidr}\n"
            f"SOCKS5: {self.socks} — {proxy_state}\n\n" + final_note
        )


def make_driver(cfg: dict, password: str) -> ArcherC80Driver:
    if cfg["router"]["driver"] != "tp_link_archer_c80":
        raise ValueError("در نسخه ۱ فقط TP-Link Archer C80 پشتیبانی می‌شود.")
    return ArcherC80Driver(
        cfg["router"]["base_url"], cfg["router"].get("username", "admin"), password
    )


def dry_run(cfg: dict, password: str | None) -> Plan:
    if cfg["router"]["driver"] == "manual":
        current = DhcpSettings("تنظیم دستی", "تنظیم دستی")
    else:
        current = make_driver(cfg, password).read_dhcp()
    socks = f"{cfg['proxy']['address']}:{cfg['proxy']['port']}"
    return Plan(
        current=current,
        pc_ip=cfg["network"]["pc_ip"],
        router_ip=cfg["network"]["router_ip"],
        lan_cidr=cfg["network"]["lan_cidr"],
        socks=socks,
        proxy_ok=proxy_reachable(cfg),
    )


def enable(cfg: dict, password: str | None) -> str:
    plan = dry_run(cfg, password)
    if not plan.proxy_ok:
        raise EngineError("پروکسی SOCKS5 در دسترس نیست؛ ابتدا VPN/Proxy را متصل کنید.")
    manual = cfg["router"]["driver"] == "manual"
    if not manual:
        save_router_backup(plan.current.as_dict())
    windows_changed = False
    try:
        engine_output = run_engine("all-on", cfg)
        windows_changed = True
        if manual:
            return (
                engine_output
                + "\n\nبخش Windows فعال شد. اکنون در DHCP Server مودم این مقادیر را وارد کنید:\n"
                + f"Default Gateway: {cfg['network']['pc_ip']}\n"
                + f"Primary DNS: {cfg['network']['router_ip']}\n"
                + "سپس Save کنید و Wi-Fi دستگاه مقصد را یک‌بار قطع و وصل کنید."
            )
        make_driver(cfg, password).apply_dhcp(cfg["network"]["pc_ip"], cfg["network"]["router_ip"])
        return engine_output + "\nمودم نیز تنظیم و read-back شد."
    except (EngineError, RouterError, OSError, ValueError) as primary:
        if windows_changed:
            try:
                run_engine("all-off", cfg)
            except EngineError as rollback:
                raise EngineError(
                    f"فعال‌سازی شکست خورد: {primary}\nبازگردانی Windows نیز کامل نشد: {rollback}"
                ) from primary
        raise


def disable(cfg: dict, password: str | None) -> str:
    if cfg["router"]["driver"] == "manual":
        return (
            run_engine("all-off", cfg)
            + "\nWindows به حالت عادی برگشت. تنظیمات DHCP مودم باید قبلاً دستی بازگردانده شده باشد."
        )
    messages: list[str] = []
    error: Exception | None = None
    backup = load_router_backup()
    try:
        gateway = backup.get("default_gateway", "0.0.0.0") if backup else "0.0.0.0"
        dns = backup.get("primary_dns", "0.0.0.0") if backup else "0.0.0.0"
        make_driver(cfg, password).apply_dhcp(gateway or "0.0.0.0", dns or "0.0.0.0")
        messages.append("تنظیم DHCP مودم بازگردانده شد.")
    except RouterError as exc:
        error = exc
        messages.append(f"بازگردانی مودم ناموفق بود: {exc}")
    try:
        messages.append(run_engine("all-off", cfg))
    except EngineError as exc:
        error = error or exc
        messages.append(f"بازگردانی ویندوز ناموفق بود: {exc}")
    if error:
        raise EngineError("\n".join(messages)) from error
    delete_router_backup()
    return "\n".join(messages)
