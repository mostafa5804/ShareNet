import pytest

from sharenet import service
from sharenet.engine import EngineError
from sharenet.routers.base import DhcpSettings, RouterError
from sharenet.service import Plan


def test_plan_is_explicitly_non_mutating():
    plan = Plan(
        current=DhcpSettings("0.0.0.0", "192.168.1.1"),
        pc_ip="192.168.1.250",
        router_ip="192.168.1.1",
        lan_cidr="192.168.1.0/24",
        socks="127.0.0.1:10808",
        proxy_ok=True,
    )
    text = plan.format_fa()
    assert "هیچ تغییری اعمال نشده" in text
    assert "192.168.1.250" in text


def test_enable_refuses_when_proxy_is_down(monkeypatch):
    plan = Plan(
        DhcpSettings("0.0.0.0", "192.168.1.1"),
        "192.168.1.250",
        "192.168.1.1",
        "192.168.1.0/24",
        "127.0.0.1:10808",
        False,
    )
    monkeypatch.setattr(service, "dry_run", lambda *_: plan)
    with pytest.raises(EngineError, match="SOCKS5"):
        service.enable({}, "example")


def test_router_failure_rolls_windows_back(monkeypatch):
    cfg = {
        "router": {
            "driver": "tp_link_archer_c80",
            "base_url": "http://192.168.1.1",
            "username": "admin",
        },
        "network": {
            "pc_ip": "192.168.1.250",
            "router_ip": "192.168.1.1",
            "lan_cidr": "192.168.1.0/24",
        },
        "proxy": {"address": "127.0.0.1", "port": 10808},
    }
    plan = Plan(
        DhcpSettings("0.0.0.0", "192.168.1.1"),
        "192.168.1.250",
        "192.168.1.1",
        "192.168.1.0/24",
        "127.0.0.1:10808",
        True,
    )
    actions = []

    class BrokenDriver:
        def apply_dhcp(self, *_):
            raise RouterError("save failed")

    monkeypatch.setattr(service, "dry_run", lambda *_: plan)
    monkeypatch.setattr(service, "save_router_backup", lambda *_: None)
    monkeypatch.setattr(service, "make_driver", lambda *_: BrokenDriver())
    monkeypatch.setattr(service, "run_engine", lambda action, _: actions.append(action) or "ok")

    with pytest.raises(RouterError, match="save failed"):
        service.enable(cfg, "example")
    assert actions == ["all-on", "all-off"]


def test_manual_dry_run_does_not_open_router(monkeypatch):
    cfg = {
        "router": {"driver": "manual"},
        "network": {
            "pc_ip": "192.168.1.250",
            "router_ip": "192.168.1.1",
            "lan_cidr": "192.168.1.0/24",
        },
        "proxy": {"address": "127.0.0.1", "port": 10808},
    }
    monkeypatch.setattr(service, "proxy_reachable", lambda *_: True)
    monkeypatch.setattr(
        service,
        "make_driver",
        lambda *_: pytest.fail("manual mode must not create an automatic router driver"),
    )
    plan = service.dry_run(cfg, None)
    assert plan.current.default_gateway == "تنظیم دستی"
    assert plan.proxy_ok is True


def test_manual_enable_only_changes_windows(monkeypatch):
    cfg = {
        "router": {"driver": "manual"},
        "network": {
            "pc_ip": "192.168.1.250",
            "router_ip": "192.168.1.1",
            "lan_cidr": "192.168.1.0/24",
        },
        "proxy": {"address": "127.0.0.1", "port": 10808},
    }
    plan = Plan(
        DhcpSettings("تنظیم دستی", "تنظیم دستی"),
        "192.168.1.250",
        "192.168.1.1",
        "192.168.1.0/24",
        "127.0.0.1:10808",
        True,
    )
    actions = []
    monkeypatch.setattr(service, "dry_run", lambda *_: plan)
    monkeypatch.setattr(service, "run_engine", lambda action, _: actions.append(action) or "ok")
    monkeypatch.setattr(
        service,
        "make_driver",
        lambda *_: pytest.fail("manual mode must not create an automatic router driver"),
    )
    output = service.enable(cfg, None)
    assert actions == ["all-on"]
    assert "Default Gateway: 192.168.1.250" in output


def test_manual_disable_restores_windows_only(monkeypatch):
    cfg = {"router": {"driver": "manual"}}
    actions = []
    monkeypatch.setattr(service, "run_engine", lambda action, _: actions.append(action) or "ok")
    output = service.disable(cfg, None)
    assert actions == ["all-off"]
    assert "تنظیمات DHCP مودم" in output
