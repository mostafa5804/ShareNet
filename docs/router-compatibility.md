# Router compatibility guide

ShareNet automatic support is intentionally model-specific. Manual mode is
broader, but it still requires a configurable LAN DHCP gateway and DNS.

## Compatibility levels

| Platform/family | Automatic | Manual mode | Confidence |
|---|---:|---:|---|
| TP-Link Archer C80, English UI | Yes | Yes | Tested by the v1 maintainer |
| MikroTik RouterOS | No | Yes | Official DHCP documentation exposes gateway and DNS per network |
| OpenWrt with dnsmasq/odhcpd | No | Yes | DHCP options 3 and 6 are configurable |
| TP-Link TL-WR940N v6 | No | Likely | Official guide exposes Default Gateway and Primary DNS |
| TP-Link TL-WR902AC v3 | No | Likely | Official guide exposes Default Gateway and Primary DNS |
| TP-Link TL-WR841N v14 | No | Likely | Official guide exposes Default Gateway and DNS fields |
| TP-Link VX230v family | No | Likely | Official guide shows optional Default Gateway and Primary DNS |
| ASUS stock firmware | No | Verify first | DHCP/DNS controls vary; some official pages do not confirm an editable LAN gateway |
| ISP-locked modem/ONT | No | Unknown | Provider firmware commonly hides or locks DHCP options |
| Router with DNS-only DHCP settings | No | No | A custom DNS alone cannot redirect all traffic through the PC |

“Likely” is not a support guarantee. Hardware revision, operating mode,
firmware and UI language can change the available fields.

## How to check an unlisted router

Open its LAN/DHCP Server page and look for both of these editable fields:

```text
Default Gateway / Router / DHCP Option 3
Primary DNS / DNS Server / DHCP Option 6
```

The gateway field must be part of the **LAN DHCP server**, not the WAN/Internet
connection page. If both fields exist, the router is a candidate for Manual
Setup. Record the original values before changing anything.

## Primary references

- [MikroTik RouterOS DHCP](https://help.mikrotik.com/docs/spaces/ROS/pages/24805500/DHCP)
- [OpenWrt DHCP and DNS configuration](https://openwrt.org/docs/guide-user/base-system/dhcp)
- [OpenWrt DHCP option examples](https://openwrt.org/docs/guide-user/base-system/dhcp_configuration)
- [TP-Link TL-WR940N v6 guide](https://www.tp-link.com/us/user-guides/TL-WR940N_V6/chapter-5-configure-the-router-in-access-point-mode)
- [TP-Link TL-WR902AC v3 guide](https://www.tp-link.com/us/user-guides/tl-wr902ac_v3/chapter-5-configure-the-router-in-access-point-mode)
- [TP-Link TL-WR841N v14 guide](https://www.tp-link.com/us/user-guides/tl-wr841n_v14/chapter-4-configure-the-router-in-wireless-router-mode)

