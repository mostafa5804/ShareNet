from __future__ import annotations

import pytest

from sharenet.config import DEFAULT_CONFIG, recommend_pc_ip, validate_config


def test_default_config_is_valid():
    validate_config(DEFAULT_CONFIG)


def test_router_and_pc_cannot_be_same():
    cfg = {
        **DEFAULT_CONFIG,
        "router": dict(DEFAULT_CONFIG["router"]),
        "network": dict(DEFAULT_CONFIG["network"], pc_ip="192.168.1.1"),
        "proxy": dict(DEFAULT_CONFIG["proxy"]),
    }
    with pytest.raises(ValueError, match="یکسان"):
        validate_config(cfg)


def test_addresses_must_be_inside_lan():
    cfg = {
        **DEFAULT_CONFIG,
        "router": dict(DEFAULT_CONFIG["router"]),
        "network": dict(DEFAULT_CONFIG["network"], pc_ip="192.168.50.10"),
        "proxy": dict(DEFAULT_CONFIG["proxy"]),
    }
    with pytest.raises(ValueError, match="LAN"):
        validate_config(cfg)


def test_recommended_ip_follows_detected_subnet():
    assert recommend_pc_ip("192.168.0.0/24", "192.168.0.1") == "192.168.0.250"
    assert recommend_pc_ip("10.20.16.0/20", "10.20.16.1") == "10.20.31.250"
