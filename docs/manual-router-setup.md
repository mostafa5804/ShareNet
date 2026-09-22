# Other Router — Manual Setup

Use this mode when ShareNet does not have an automatic driver for the exact
router model and firmware.

## Requirement

The router DHCP server must allow the administrator to advertise a custom:

- Default Gateway (DHCP option 3), and
- DNS Server (DHCP option 6).

If the router exposes only DNS but not Default Gateway, this mode cannot route
all LAN devices through the ShareNet PC.

## Enable

1. Select `Other Router — تنظیم دستی`.
2. Run network detection and verify the proposed static PC address is outside
   the router DHCP pool.
3. Run Dry Run and confirm SOCKS5 is reachable.
4. Select Enable. ShareNet configures Windows and displays two values.
5. Open the router DHCP Server page and set:

```text
Default Gateway = the PC address shown by ShareNet
Primary DNS     = the router address shown by ShareNet
```

6. Save the router settings and renew the client lease by reconnecting Wi-Fi.

Do not change the router WAN gateway. The required field is the gateway that
the LAN DHCP server advertises to clients.

## Disable safely

The order matters:

1. In the router DHCP Server page, restore Default Gateway and DNS to their
   original values.
2. Save the router configuration.
3. Return to ShareNet and select Disable/Restore.
4. Renew Wi-Fi or DHCP leases on client devices.

Do not restore Windows first while the router is still advertising the PC as
the LAN gateway; doing so can temporarily disconnect every DHCP client.

