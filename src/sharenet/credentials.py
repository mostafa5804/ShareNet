from __future__ import annotations

import os

import keyring

SERVICE = "ShareNet Gateway"


def credential_key(router_url: str, username: str) -> str:
    return f"{username}@{router_url}"


def get_password(router_url: str, username: str) -> str | None:
    env_value = os.environ.get("SHARENET_ROUTER_PASSWORD")
    if env_value:
        return env_value
    try:
        return keyring.get_password(SERVICE, credential_key(router_url, username))
    except keyring.errors.KeyringError:
        return None


def set_password(router_url: str, username: str, password: str) -> None:
    keyring.set_password(SERVICE, credential_key(router_url, username), password)


def delete_password(router_url: str, username: str) -> None:
    try:
        keyring.delete_password(SERVICE, credential_key(router_url, username))
    except keyring.errors.KeyringError:
        pass
