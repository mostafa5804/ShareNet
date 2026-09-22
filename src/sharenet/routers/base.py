from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DhcpSettings:
    default_gateway: str
    primary_dns: str
    pool_start: str = ""
    pool_end: str = ""

    def as_dict(self) -> dict:
        return {
            "default_gateway": self.default_gateway,
            "primary_dns": self.primary_dns,
            "pool_start": self.pool_start,
            "pool_end": self.pool_end,
        }


class RouterError(RuntimeError):
    pass
