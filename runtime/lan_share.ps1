<#
  lan_share.ps1 - turn this Windows PC into the internet gateway of the whole
  LAN, so every device behind the router (Wi-Fi and wired) is routed through
  the zeptun TUN tunnel that is fed by the local SOCKS5 proxy.

      .\lan_share.ps1 status        show the current state (no changes)
      .\lan_share.ps1 all-on        forwarding + static IP + clean DNS
      .\lan_share.ps1 all-off       back to a plain DHCP client
      .\lan_share.ps1 verify        connectivity checks while sharing

  Single steps: forward-on|forward-off ip-static|ip-dhcp dns-public|dns-dhcp
                clean-routes nat-on|nat-off

  Every change is remembered in _lan_share_state.json so all-off can put the
  machine back exactly as it was found. Needs an elevated PowerShell.
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('status', 'all-on', 'all-off', 'forward-on', 'forward-off',
               'ip-static', 'ip-dhcp', 'dns-public', 'dns-dhcp',
               'clean-routes', 'nat-on', 'nat-off', 'verify',
               'socks', 'uplinks', 'restart-nic', 'myip', 'selftest')]
  [string]$Action = 'status',

  [string]   $LanCidr   = '192.168.1.0/24',
  [string]   $RouterIp  = '192.168.1.1',
  # This must be inside LAN but outside the router DHCP pool.
  [string]   $PcIp      = '192.168.1.250',
  [string]   $TunName   = 'zeptun0',
  # zeptun gives its tunnel interface this address range (see zeptun.toml)
  [string]   $TunSubnet = '172.19.0.0/16',
  [string]   $SocksAddr = '127.0.0.1:10808',
  # Runtime data belongs under LocalAppData, never beside the source or EXE.
  [string]   $StateRoot = (Join-Path $env:LOCALAPPDATA 'ShareNet'),
  # The name servers that are used while sharing. They stay *outside* the tunnel
  # on purpose: this proxy chain carries no UDP (a plain UDP query gets no
  # answer), so a resolver that is asked over UDP would never answer and would
  # break every device behind this PC. Devices that want their DNS inside the
  # tunnel can use DNS over HTTPS (Android: "Private DNS" -> dns.google), which
  # travels over TCP 443 and works fine through the tunnel.
  [string[]] $PublicDns = @($RouterIp)
)

$script:Here      = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:LogDir    = Join-Path $StateRoot 'logs'
New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
$script:StateFile = Join-Path $StateRoot '_lan_share_state.json'
$script:LogFile   = Join-Path $script:LogDir 'share_log.txt'
# addresses of the proxy servers - they are kept out of the tunnel and are
# remembered here, because a run that loses them would kill its own upstream
$script:ExcludeFile = Join-Path $StateRoot '_proxy_excludes.txt'
$script:Uplinks     = @()
$script:Problems  = 0

# keep a log next to the scripts so every run can be inspected afterwards
try {
  if ((Test-Path $script:LogFile) -and (Get-Item $script:LogFile).Length -gt 200KB) {
    Remove-Item $script:LogFile -Force
  }
  Start-Transcript -Path $script:LogFile -Append -Force | Out-Null
} catch { }

function Info ($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Good ($m) { Write-Host "[+] $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "[!] $m" -ForegroundColor Yellow }
function Bad  ($m) { Write-Host "[x] $m" -ForegroundColor Red; $script:Problems++ }

function Assert-Admin {
  $p = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator rights are required - run the .bat as administrator.'
  }
}

function Test-InCidr([string]$Ip, [string]$Cidr) {
  $split = $Cidr.Split('/')
  $net   = [System.Net.IPAddress]::Parse($split[0]).GetAddressBytes()
  $len   = [int]$split[1]
  $addr  = [System.Net.IPAddress]::Parse($Ip).GetAddressBytes()
  $bytes = [math]::Floor($len / 8)
  $bits  = $len % 8
  for ($i = 0; $i -lt $bytes; $i++) { if ($addr[$i] -ne $net[$i]) { return $false } }
  if ($bits -gt 0) {
    $mask = [byte](0xFF -shl (8 - $bits))
    if (($addr[$bytes] -band $mask) -ne ($net[$bytes] -band $mask)) { return $false }
  }
  return $true
}

function Get-LanAdapter {
  $all = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -ne '127.0.0.1' -and (Test-InCidr $_.IPAddress $LanCidr) })
  if (-not $all.Count) { throw "No adapter with an IPv4 address inside $LanCidr was found." }
  if ($all.Count -gt 1) {
    $withGw = @($all | Where-Object {
      Get-NetRoute -InterfaceIndex $_.InterfaceIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue })
    if ($withGw.Count) { return $withGw[0] }
  }
  return $all[0]
}

function Get-TunAlias {
  # 1) the configured name
  $a = @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue |
         Where-Object { $_.Name -like "$TunName*" })
  if ($a.Count) { return $a[0].Name }
  $i = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
         Where-Object { $_.InterfaceAlias -like "$TunName*" })
  if ($i.Count) { return $i[0].InterfaceAlias }
  # 2) the adapter that carries zeptun's own tunnel address (172.19.0.1/30)
  $i = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
         Where-Object { $_.IPAddress -ne '127.0.0.1' -and (Test-InCidr $_.IPAddress $TunSubnet) })
  if ($i.Count) { return $i[0].InterfaceAlias }
  # 3) any wintun based adapter that is up
  $a = @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue |
         Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'wintun|userspace tunnel' })
  if ($a.Count) { return $a[0].Name }
  return $null
}

function Show-TunDebug {
  Warn 'diagnostics of the interfaces that exist right now:'
  foreach ($a in @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue)) {
    Info ("adapter : '{0}'  desc='{1}'  if={2}  {3}" -f $a.Name, $a.InterfaceDescription, $a.ifIndex, $a.Status)
  }
  foreach ($i in @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                   Where-Object { $_.IPAddress -ne '127.0.0.1' })) {
    Info ("ipv4    : '{0}'  if={1}  {2}/{3}" -f $i.InterfaceAlias, $i.InterfaceIndex, $i.IPAddress, $i.PrefixLength)
  }
  foreach ($r in @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)) {
    Info ("default : via {0}  if='{1}'  metric={2}" -f $r.NextHop, $r.InterfaceAlias, $r.RouteMetric)
  }
}

function Get-ForwardTargets {
  # forwarding must be switched on for the LAN card and for the tunnel card;
  # interface indexes are used because names with '*' break the CIM lookup
  $map = @{}
  try { $a = Get-LanAdapter; $map[[string]$a.InterfaceIndex] = $a.InterfaceAlias } catch { }
  $t = Get-TunAlias
  if ($t) {
    $ti = @(Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.InterfaceAlias -eq $t })
    if ($ti.Count) { $map[[string]$ti[0].InterfaceIndex] = $t }
  }
  foreach ($i in @(Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                   Where-Object { $_.ConnectionState -eq 'Connected' -and $_.InterfaceAlias -notmatch '\*' -and
                                  $_.InterfaceAlias -notmatch 'Loopback|Bluetooth|Wi-Fi Direct' })) {
    $map[[string]$i.InterfaceIndex] = $i.InterfaceAlias
  }
  foreach ($k in @($map.Keys)) {
    [pscustomobject]@{ Index = [int]$k; Alias = $map[$k] }
  }
}

function Read-StateFile {
  $h = @{}
  if (Test-Path $script:StateFile) {
    try {
      $o = Get-Content $script:StateFile -Raw | ConvertFrom-Json
      foreach ($p in $o.PSObject.Properties) { $h[$p.Name] = $p.Value }
    } catch { $h = @{} }
  }
  return , $h
}

function Save-State([string]$Name, $Value) {
  $s = Read-StateFile
  if (-not $s.ContainsKey($Name)) {
    $s[$Name] = $Value
    ($s | ConvertTo-Json) | Set-Content -Path $script:StateFile -Encoding UTF8
  }
}

function Read-State([string]$Name) {
  $s = Read-StateFile
  if ($s.ContainsKey($Name)) { return $s[$Name] }
  return $null
}

function Clear-State { if (Test-Path $script:StateFile) { Remove-Item $script:StateFile -Force } }

# --------------------------------------------------------------- small tests
function Test-SocksUp {
  $h, $port = $SocksAddr.Split(':')
  $c = New-Object System.Net.Sockets.TcpClient
  try { $c.Connect($h, [int]$port); return $true }
  catch { return $false }
  finally { $c.Dispose() }
}

function Test-IpInUse([string]$Ip) {
  $ping = Test-Connection -ComputerName $Ip -Count 1 -Quiet -ErrorAction SilentlyContinue
  $nb = @(Get-NetNeighbor -AddressFamily IPv4 -IPAddress $Ip -ErrorAction SilentlyContinue |
          Where-Object { $_.State -ne 'Unreachable' -and $_.LinkLayerAddress -and
                         $_.LinkLayerAddress -ne '00-00-00-00-00-00' })
  return [bool]($ping -or $nb.Count)
}

function Get-FreeLanIp([string[]]$Candidates) {
  foreach ($ip in $Candidates) {
    if (-not (Test-IpInUse $ip)) { return $ip }
    Warn "$ip is already used on the LAN"
  }
  throw "none of these addresses is free: $($Candidates -join ', ')"
}

# --------------------------------------------------------------- forwarding
function Set-RouterMode([bool]$Enable) {
  if ($Enable) {
    # a tunnel adapter may appear a moment after the start - and on Windows it
    # usually never appears at all, because the traffic is taken over with WFP
    # filters and the IP Helper API (README "Platform support"). So this is a
    # short wait, not a test.
    for ($i = 0; -not (Get-TunAlias) -and $i -lt 5; $i++) { Start-Sleep -Seconds 1 }
  }
  $key = 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
  $cur = (Get-ItemProperty -Path $key -Name IPEnableRouter -ErrorAction SilentlyContinue).IPEnableRouter
  if ($null -eq $cur) { $cur = 0 }
  Save-State 'IPEnableRouter' ([int]$cur)
  Set-ItemProperty -Path $key -Name IPEnableRouter -Value ([int]$Enable) -Type DWord
  Info "IPEnableRouter set to $([int]$Enable) (was $cur)"

  $want = if ($Enable) { 'Enabled' } else { 'Disabled' }
  foreach ($t in Get-ForwardTargets) {
    try {
      Set-NetIPInterface -InterfaceIndex $t.Index -AddressFamily IPv4 -Forwarding $want -ErrorAction Stop
      Good "IPv4 forwarding $want on '$($t.Alias)'"
    } catch { Warn "forwarding on '$($t.Alias)' skipped: $($_.Exception.Message)" }
  }
  if ($Enable) {
    Add-ProxyBypassRoutes
    $t = Get-TunAlias
    if ($t) { Good "tunnel interface '$t' exists" }
    else { Info 'no separate tunnel adapter shows up - this build redirects with WFP filters, that is normal' }
  }
}

# --------------------------------------------------------------- address
function Set-PcIpMode([bool]$Static) {
  $a = Get-LanAdapter
  $idx = $a.InterfaceIndex
  Save-State 'LanAlias' $a.InterfaceAlias

  if (-not $Static) {
    Info "returning '$($a.InterfaceAlias)' to DHCP"
    Set-NetIPInterface -InterfaceIndex $idx -Dhcp Enabled -ErrorAction SilentlyContinue
    Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object { $_.PrefixOrigin -eq 'Manual' } |
      Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    # a manual gateway that came with the static address has to go as well,
    # otherwise the next static run reports "DefaultGateway already exists"
    Get-NetRoute -InterfaceIndex $idx -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' `
      -ErrorAction SilentlyContinue |
      Where-Object { $_.Protocol -eq 'NetMgmt' } |
      Remove-NetRoute -Confirm:$false -ErrorAction SilentlyContinue
    ipconfig /renew | Out-Null
    Good 'the adapter asks the router for an address again'
    return
  }

  $cur = Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue |
         Where-Object { $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1

  $target = $PcIp
  $mine = [bool]($cur -and $cur.IPAddress -eq $target)
  if (-not $mine -and (Test-IpInUse $target)) {
    throw "$target is already used by another device. Choose an unused address outside the DHCP pool."
  }
  Save-State 'PcIp' $target

  if ($cur -and $cur.IPAddress -eq $target -and $cur.PrefixOrigin -eq 'Manual') {
    # the address is fine - but a broken earlier run may have left this adapter
    # without any name servers, which would make the whole PC look offline
    $dnsNow = @((Get-DnsClientServerAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses)
    if (-not $dnsNow.Count) {
      Set-DnsClientServerAddress -InterfaceIndex $idx -ServerAddresses @($RouterIp) -ErrorAction SilentlyContinue
      Warn "the adapter had no name servers - $RouterIp is used again"
    }
    Good "address $target is already static on '$($a.InterfaceAlias)'"
    return
  }
  Save-State 'WasDhcp' ([bool]($cur -and $cur.PrefixOrigin -eq 'Dhcp'))

  $prefixLength = [int]$LanCidr.Split('/')[1]
  Info "binding static $target/$prefixLength (gateway $RouterIp) to '$($a.InterfaceAlias)'"
  # the name servers of the adapter survive a DHCP -> static switch poorly, so
  # they are read first and put back afterwards - this PC must never be left
  # without DNS, not even when a later step fails
  $dnsNow = @((Get-DnsClientServerAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses)
  if (-not $dnsNow.Count) { $dnsNow = @($RouterIp) }
  # every default route of this adapter is cleared first: a manual gateway that
  # an interrupted run left behind would make Windows refuse the new one with
  # "Instance DefaultGateway already exists"
  Remove-NetRoute -InterfaceIndex $idx -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' `
    -Confirm:$false -ErrorAction SilentlyContinue
  Set-NetIPInterface -InterfaceIndex $idx -Dhcp Disabled -ErrorAction SilentlyContinue
  Get-NetIPAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.PrefixOrigin -ne 'WellKnown' } |
    Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
  New-NetIPAddress -InterfaceIndex $idx -IPAddress $target -PrefixLength $prefixLength `
    -DefaultGateway $RouterIp -ErrorAction Stop | Out-Null
  Set-DnsClientServerAddress -InterfaceIndex $idx -ServerAddresses $dnsNow -ErrorAction SilentlyContinue
  Good "static address $target is live (name servers: $($dnsNow -join ', '))"
}

# --------------------------------------------------------------- DNS
function Set-PcDnsMode([bool]$Public) {
  $a = Get-LanAdapter
  if ($Public) {
    $was = @(Get-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4).ServerAddresses
    Save-State 'DnsWas' ($was -join ',')
    Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ServerAddresses $PublicDns -ErrorAction Stop
    Good "DNS on '$($a.InterfaceAlias)' -> $($PublicDns -join ', ')"
  } else {
    Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ResetServerAddresses -ErrorAction Stop
    ipconfig /renew | Out-Null
    Good 'DNS back to the DHCP value'
  }
}

# --------------------------------------------------------------- routes
function Clear-TunnelRoutes {
  $t = Get-TunAlias
  $n = 0
  foreach ($r in @(Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                   Where-Object { $_.NextHop -like '172.19.*' -or ($t -and $_.InterfaceAlias -eq $t) })) {
    try {
      Remove-NetRoute -DestinationPrefix $r.DestinationPrefix -InterfaceIndex $r.InterfaceIndex `
        -Confirm:$false -ErrorAction Stop
      $n++
    } catch { }
  }
  if ($n) { Good "removed $n leftover route(s) of the tunnel" }
  if (-not @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue).Count) {
    $a = Get-LanAdapter
    New-NetRoute -DestinationPrefix '0.0.0.0/0' -InterfaceIndex $a.InterfaceIndex `
      -NextHop $RouterIp -ErrorAction Stop | Out-Null
    Good "default route restored through $RouterIp"
  }
  if (Get-NetNat -Name 'LanShare' -ErrorAction SilentlyContinue) {
    Remove-NetNat -Name 'LanShare' -Confirm:$false
    Good 'WinNAT rule removed'
  }
}

# --------------------------------------------------------------- WinNAT fallback
function Set-LanNat([bool]$Enable) {
  try {
    if ($Enable) {
      if (-not (Get-NetNat -Name 'LanShare' -ErrorAction SilentlyContinue)) {
        New-NetNat -Name 'LanShare' -InternalIPInterfaceAddressPrefix $LanCidr -ErrorAction Stop | Out-Null
      }
      Good "WinNAT 'LanShare' translates $LanCidr into the tunnel"
    } else {
      Get-NetNat -Name 'LanShare' -ErrorAction SilentlyContinue | Remove-NetNat -Confirm:$false
      Good 'WinNAT rule removed'
    }
  } catch { Warn "WinNAT is not available here: $($_.Exception.Message)" }
}

# --------------------------------------------------------------- status
function Show-Status {
  try {
    $a = Get-LanAdapter
    $ip = Get-NetIPAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
          Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1
    Info "adapter       : $($a.InterfaceAlias)   $($ip.IPAddress)/$($ip.PrefixLength)   origin=$($ip.PrefixOrigin)"
    $dns = (@(Get-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4).ServerAddresses) -join ', '
    Info "DNS servers   : $dns"
    $fw = (Get-NetIPInterface -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).Forwarding
    Info "IPv4 forward  : $fw   (adapter)"
  } catch { Bad "no LAN adapter found in $LanCidr : $($_.Exception.Message)" }

  $reg = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters' -Name IPEnableRouter -ErrorAction SilentlyContinue).IPEnableRouter
  Info "IPEnableRouter: $reg"

  $t = Get-TunAlias
  if ($t) {
    $tip = (@(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias $t -ErrorAction SilentlyContinue).IPAddress) -join ','
    $tfw = (Get-NetIPInterface -InterfaceIndex (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias $t -ErrorAction SilentlyContinue | Select-Object -First 1).InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).Forwarding
    Good "tunnel iface  : $t   addr=$tip   forward=$tfw"
  } else {
    if (@(Get-Process zeptun -ErrorAction SilentlyContinue).Count) {
      Info 'tunnel iface  : none (this build redirects with WFP filters, zeptun is running)'
    } else { Warn 'tunnel iface  : none and zeptun is not running' }
  }

  Info "zeptun procs  : $(@(Get-Process zeptun -ErrorAction SilentlyContinue).Count)"
  if (Test-SocksUp) { Good "SOCKS5 $SocksAddr : reachable" } else { Bad "SOCKS5 $SocksAddr : not reachable" }

  foreach ($r in @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)) {
    Info "default route : via $($r.NextHop)  if=$($r.InterfaceAlias)  metric=$($r.RouteMetric)"
  }
  if (Get-NetNat -Name 'LanShare' -ErrorAction SilentlyContinue) { Info 'WinNAT        : LanShare is active' }
}

# --------------------------------------------------------------- verification
function Get-Url([string]$Url) {
  try { return (Invoke-WebRequest -Uri $Url -TimeoutSec 15 -UseBasicParsing).Content.Trim() } catch { return $null }
}

function Get-UrlViaProxy([string]$Url) {
  # asks the proxy itself. It only answers while the engine can still reach its
  # own server - so this detects a tunnel that has taken over its own upstream.
  # --socks5-hostname: the name is resolved by the proxy, because the resolver
  # of this PC asks over UDP, which this tunnel does not carry.
  $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
  if (-not (Test-Path $curl)) { $curl = 'curl.exe' }
  try {
    $r = & $curl --socks5-hostname $SocksAddr -s -m 20 -o - $Url 2>$null
    if ($r) { return (@($r) -join "`n").Trim() }
  } catch { }
  return $null
}

function Test-UdpDns([string]$ServerIp, [string]$Name) {
  # a plain socket instead of the resolver of Windows: its cache would answer
  # (or fail) instantly and hide whether the tunnel really carries UDP
  $q = New-Object System.Collections.Generic.List[byte]
  $q.Add(0x12); $q.Add(0x34)                 # transaction id
  $q.Add(0x01); $q.Add(0x00)                 # standard query, recursion desired
  $q.Add(0); $q.Add(1)                       # one question
  0..5 | ForEach-Object { $q.Add(0) }        # no answer/authority/additional records
  foreach ($part in $Name.Split('.')) {
    $q.Add([byte]$part.Length)
    foreach ($ch in $part.ToCharArray()) { $q.Add([byte][int][char]$ch) }
  }
  $q.Add(0)                                  # end of the name
  $q.Add(0); $q.Add(1)                       # type A
  $q.Add(0); $q.Add(1)                       # class IN
  $c = New-Object System.Net.Sockets.UdpClient
  $c.Client.ReceiveTimeout = 8000
  $c.Client.SendTimeout    = 8000
  $target = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($ServerIp)), 53
  try {
    $null = $c.Send($q.ToArray(), $q.Count, $target)
    $from = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any), 0
    $ans = $c.Receive([ref]$from)
    # the transaction id has to come back and the answer must carry at least one
    # record - an empty or refused reply does not resolve anything
    return ($ans.Length -gt 12 -and $ans[0] -eq 0x12 -and $ans[1] -eq 0x34 -and
            ([int]$ans[6] * 256 + [int]$ans[7]) -gt 0)
  } catch { return $false } finally { $c.Close() }
}

function Invoke-Verify {
  Info '----------------------------------------'
  Info 'connectivity checks'
  if (Test-SocksUp) { Good "SOCKS5 $SocksAddr accepts connections" }
  else { Bad "SOCKS5 $SocksAddr is not reachable - is PattN connected?" }

  # the tunnel of this build is held by WFP filters and the IP Helper API, so
  # the process has to run - a missing adapter is not a problem by itself
  $ztn = @(Get-Process -Name zeptun -ErrorAction SilentlyContinue)
  $tun = Get-TunAlias
  if (-not $ztn.Count) { Bad 'zeptun.exe is not running - the tunnel is down'; Show-TunDebug }
  elseif ($tun) { Good "zeptun.exe runs (pid $($ztn.Id -join ', ')) and adapter '$tun' is up" }
  else { Good "zeptun.exe runs (pid $($ztn.Id -join ', ')) - redirection is active, no adapter needed" }

  $reg = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters' -Name IPEnableRouter -ErrorAction SilentlyContinue).IPEnableRouter
  $lan = $null
  try { $lan = Get-LanAdapter } catch { }
  $fw = $null
  if ($lan) {
    $fw = (Get-NetIPInterface -InterfaceIndex $lan.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue).Forwarding
  }
  if ($reg -eq 1 -and $fw -eq 'Enabled') {
    Good "IP forwarding is on (IPEnableRouter=1, '$($lan.InterfaceAlias)' forward=$fw)"
  } else {
    Bad "IP forwarding is NOT fully on (IPEnableRouter=$reg, adapter forward=$fw) - devices of the LAN would have no internet"
  }

  $trace = Get-Url 'https://www.cloudflare.com/cdn-cgi/trace'
  if (-not $trace) {
    Info 'the first HTTPS attempt failed, trying once more in 5 s...'
    Start-Sleep -Seconds 5
    $trace = Get-Url 'https://www.cloudflare.com/cdn-cgi/trace'
  }
  if ($trace) {
    $exitIp = ($trace -split "`n" | Where-Object { $_ -like 'ip=*' } | Select-Object -First 1) -replace '^ip=', ''
    Good 'HTTPS inside the tunnel works (public address intentionally omitted from logs)'
  } else { Bad 'no HTTPS inside the tunnel' }

  # A status code alone proves nothing: the block page of the ISPs answers with
  # HTTP 200 as well. So the body is fetched and searched for the real page.
  # The name is very likely answered with the block address (10.10.34.x) - the
  # engine sniffs the name out of the TLS handshake and asks the exit server
  # for the real address, so a poisoned answer still ends in the real page as
  # long as the traffic goes through the tunnel.
  $dq = @(Resolve-DnsName -Name 'www.youtube.com' -Type A -QuickTimeout -ErrorAction SilentlyContinue |
          Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress)
  if ($dq.Count -and (($dq -join ',') -match '^10\.10\.34\.')) {
    Info "the resolver gives the block address $($dq -join ', ') for youtube.com - the tunnel re-resolves it"
  }
  $page = $null
  try {
    $page = (Invoke-WebRequest -Uri 'https://www.youtube.com/' -TimeoutSec 25 -UseBasicParsing -ErrorAction Stop).Content
  } catch { Warn "blocked-site check failed: $($_.Exception.Message)" }
  if ($page -match '<title>YouTube') {
    Good 'blocked-site check : the real youtube.com page came through the tunnel'
  } elseif ($page) {
    Bad 'youtube.com answered - but the body is not the real page (a block page?)'
  }

  # the engine of the proxy must keep reaching its own server. Right after the
  # address of this PC has changed the engine still re-connects, so a first
  # failure proves nothing - it is tried once more.
  $p = Get-UrlViaProxy 'https://www.cloudflare.com/cdn-cgi/trace'
  if (-not $p) { Start-Sleep -Seconds 5; $p = Get-UrlViaProxy 'https://www.cloudflare.com/cdn-cgi/trace' }
  if ($p -match 'ip=') {
    Good 'the proxy itself still reaches its server (its upstream stays outside the tunnel)'
  } else {
    Bad 'the proxy can no longer reach its server - the tunnel has taken over its own upstream'
  }

  # UDP: this chain does not carry it (measured with a plain socket, so the
  # cache of the resolver cannot cheat). QUIC and UDP apps fall back to TCP, so
  # this is no defect - but it is the reason why the devices of the LAN get the
  # router as their name server instead of a public resolver.
  $udp = Test-UdpDns '8.8.8.8' 'www.youtube.com'
  if (-not $udp) { Start-Sleep -Seconds 4; $udp = Test-UdpDns '8.8.8.8' 'www.youtube.com' }
  if ($udp) { Good 'UDP inside the tunnel works (a plain UDP query to 8.8.8.8 was answered)' }
  else { Info 'this chain carries no UDP - QUIC falls back to TCP, so nothing breaks' }

  # the resolver of this PC has to answer, because the devices of the LAN are
  # sent to the very same one - if it fails, every device would fail
  $rn = @(Resolve-DnsName -Name 'www.youtube.com' -Type A -QuickTimeout -ErrorAction SilentlyContinue |
          Where-Object { $_.IPAddress })
  if (-not $rn.Count) {
    Bad 'this PC cannot resolve names - the devices of the LAN would not either'
  } elseif (($rn | Where-Object { $_.IPAddress -notlike '10.10.34.*' }).Count) {
    Good "names are resolved ($($rn[0].IPAddress) for www.youtube.com)"
  } else {
    # an ISP that answers with the block address is fine: the device asks the
    # router over the LAN, so it always gets an answer, and the name of the site
    # is read out of the TLS handshake inside the tunnel anyway
    Good "the resolver answers ($($rn[0].IPAddress)) - blocked names get the block address, that is expected here"
  }

  Info 'device test: from a phone on the Wi-Fi open https://www.youtube.com'
}

# --------------------------------------------------------------- proxy uplinks
# The proxy must never be tunnelled through its own tunnel: the engine would
# then need the tunnel to reach its own server. So the addresses the proxy
# talks to are read from its configuration and from its live connections - and
# they are remembered in _proxy_excludes.txt, because a run that loses them
# kills its own upstream (this happened once: the address of the PC changed
# before the scan and every connection of the proxy was gone).
function Expand-Uplink([string]$HostOrIp) {
  if (-not $HostOrIp) { return @() }
  if ($HostOrIp -match '^\d{1,3}(\.\d{1,3}){3}$') { return @($HostOrIp) }
  try {
    return @(Resolve-DnsName -Name $HostOrIp -Type A -ErrorAction Stop |
             Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress)
  } catch { return @() }
}

function Add-Uplink($List, [string]$HostOrIp) {
  foreach ($a in Expand-Uplink $HostOrIp) {
    if (-not $a -or $a -match ':' -or $a -match '^127\.' -or $a -eq '0.0.0.0') { continue }
    if (Test-InCidr $a $LanCidr) { continue }
    if (-not $List.Contains($a)) { $List.Add($a) }
  }
}

function Get-ProxyServerAddresses {
  # every server written down in the configuration of the proxy, names as well
  # as plain addresses
  $port = [int]$SocksAddr.Split(':')[1]
  $listen = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
  if (-not $listen) { return @() }
  $exe = (Get-Process -Id $listen[0].OwningProcess -ErrorAction SilentlyContinue).Path
  if (-not $exe) { return @() }
  $dir = Split-Path -Parent $exe
  for ($i = 0; $i -lt 4 -and $dir; $i++) {
    $cfg = Join-Path $dir 'binConfigs\config.json'
    if (Test-Path $cfg) {
      try {
        $j = Get-Content $cfg -Raw | ConvertFrom-Json
        return @($j.outbounds | Where-Object { $_.settings.address } |
                 ForEach-Object { $_.settings.address } |
                 Where-Object { $_ } | Sort-Object -Unique)
      } catch { return @() }
    }
    $dir = Split-Path -Parent $dir
  }
  return @()
}

function Get-ProxyUplinks {
  $port = [int]$SocksAddr.Split(':')[1]
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($name in Get-ProxyServerAddresses) { Add-Uplink $out $name }
  $procs = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique)
  foreach ($procId in $procs) {
    foreach ($c in @(Get-NetTCPConnection -OwningProcess $procId -State Established -ErrorAction SilentlyContinue)) {
      Add-Uplink $out $c.RemoteAddress
    }
  }
  if (Test-Path $script:ExcludeFile) {
    foreach ($line in @(Get-Content $script:ExcludeFile -ErrorAction SilentlyContinue)) { Add-Uplink $out $line.Trim() }
  }
  $out | Where-Object { $_ } | ForEach-Object { "$_/32" }
}

function Save-ProxyUplinks([string[]]$Cidrs) {
  $ips = @($Cidrs | ForEach-Object { $_ -replace '/32$', '' } | Where-Object { $_ })
  if (-not $ips.Count) { return }
  $old = @()
  if (Test-Path $script:ExcludeFile) { $old = @(Get-Content $script:ExcludeFile -ErrorAction SilentlyContinue) }
  $all = @(@($old) + @($ips) | ForEach-Object { $_.Trim() } | Where-Object { $_ } |
           Select-Object -Unique | Select-Object -Last 12)
  Set-Content -Path $script:ExcludeFile -Value $all -Encoding ASCII
  Info "proxy addresses remembered: $($all -join ', ')"
}

function Add-ProxyBypassRoutes {
  # This build cannot install the routes of --exclude on Windows: its log says
  # "no existing route for excluded prefix ... (error 1232)" for every one of
  # them, and then the tunnel swallows those addresses. The proxy would have to
  # reach its own server through the tunnel it feeds - a dead-lock that leaves
  # the whole machine without internet. So the routes are put in here, over the
  # ordinary LAN interface, and they win because they are the most specific.
  $lan = $null
  try { $lan = Get-LanAdapter } catch { return }
  if (-not $lan) { return }
  $tun = Get-TunAlias
  $tunIdx = -1
  if ($tun) {
    $a = @(Get-NetAdapter -IncludeHidden -Name $tun -ErrorAction SilentlyContinue)
    if ($a.Count) { $tunIdx = $a[0].ifIndex }
  }
  $ips = @($script:Uplinks)
  if (-not $ips.Count) { $ips = @(Get-ProxyUplinks) }
  if (-not $ips.Count) { return }
  $done = 0
  foreach ($cidr in $ips) {
    foreach ($r in @(Get-NetRoute -DestinationPrefix $cidr -ErrorAction SilentlyContinue)) {
      if ($r.InterfaceIndex -ne $lan.InterfaceIndex -and
          ($r.NextHop -like '172.19.*' -or $r.InterfaceIndex -eq $tunIdx)) {
        Remove-NetRoute -DestinationPrefix $cidr -InterfaceIndex $r.InterfaceIndex -Confirm:$false -ErrorAction SilentlyContinue
      }
    }
    $keep = @(Get-NetRoute -DestinationPrefix $cidr -ErrorAction SilentlyContinue |
              Where-Object { $_.InterfaceIndex -eq $lan.InterfaceIndex })
    if ($keep.Count) { $done++; continue }
    try {
      New-NetRoute -DestinationPrefix $cidr -InterfaceIndex $lan.InterfaceIndex -NextHop $RouterIp `
        -RouteMetric 1 -ErrorAction Stop | Out-Null
      $done++
    } catch { Warn "could not keep $cidr out of the tunnel: $($_.Exception.Message)" }
  }
  if ($done) { Good "$done proxy address(es) go straight over the router instead of through the tunnel" }
}

# --------------------------------------------------------------- orchestration
function Start-ZeptunIfNeeded {
  $script:ZeptunStarted = $false
  if (Get-Process zeptun -ErrorAction SilentlyContinue) {
    Info 'zeptun.exe is already running - left untouched'
    return
  }
  $exe = Join-Path $script:Here 'zeptun.exe'
  if (-not (Test-Path $exe)) { throw 'zeptun.exe was not found next to this script' }
  # the two file names are quoted: this folder lives under "MY PC" and
  # Start-Process does not protect arguments that contain spaces
  # --dns-hijack: zeptun answers the DNS queries that travel through the tunnel
  # itself. That is what makes the name servers handed to the devices of the LAN
  # work, although raw UDP datagrams do not survive this proxy chain.
  $ztArgs = @('run', '--socks5', $SocksAddr, '--auto-route', '--exclude', $LanCidr,
              '--dns-hijack', '--dns-upstream', '1.1.1.1:53',
              '--mtu', '1500', '--log-level', 'info',
              '--log-file', ('"{0}"' -f (Join-Path $script:LogDir 'zeptun_run.log')),
              '--pid-file', ('"{0}"' -f (Join-Path $StateRoot 'zeptun.pid')))
  $ups = @($script:Uplinks)
  if (-not $ups.Count) { $ups = @(Get-ProxyUplinks) }   # when started from the menu, nothing was scanned yet
  foreach ($cidr in $ups) { $ztArgs += @('--exclude', $cidr) }
  Save-ProxyUplinks $ups
  if (-not $ups.Count) { Warn 'no upstream address of the proxy is known - if the tunnel then fails, its excludes are missing' }
  Info ('starting: zeptun.exe ' + ($ztArgs -join ' '))
  Start-Process -FilePath $exe -ArgumentList $ztArgs -WorkingDirectory $script:Here `
    -WindowStyle Minimized | Out-Null
  $script:ZeptunStarted = $true
}

function Invoke-AllOn {
  if (-not (Test-SocksUp)) {
    throw "nothing is listening on $SocksAddr - open PattN and connect first."
  }
  # the upstream addresses of the proxy are collected FIRST, while the PC still
  # has its old address: changing the address drops every connection of the
  # proxy, and a tunnel started without their excludes eats its own upstream
  $script:Uplinks = @(Get-ProxyUplinks)
  if ($script:Uplinks.Count) { Info "kept out of the tunnel: $($script:Uplinks -join ' ')" }
  else { Warn 'the proxy has no live upstream connection - the tunnel could swallow its own upstream' }
  Set-PcIpMode $true
  Start-ZeptunIfNeeded
  Set-PcDnsMode $true
  Set-RouterMode $true
  Start-Sleep -Seconds 5
  Set-RouterMode $true   # the TUN device may only appear after a moment
  Invoke-Verify
}

# --------------------------------------------------------------- undo
function Undo-Everything {
  # back to "plain client of the router": no tunnel, no forwarding, DHCP
  # address, DHCP name servers, no state file. Every step is attempted even
  # when an earlier one fails, so the PC is never left half-configured.
  $steps = @(
    @{ n = 'stop the tunnel';         f = { Stop-Process -Name zeptun -Force -ErrorAction SilentlyContinue } }
    @{ n = 'remove tunnel routes';    f = { Clear-TunnelRoutes } }
    @{ n = 'disable forwarding';      f = { Set-RouterMode $false } }
    @{ n = 'restore the DNS servers'; f = { Set-PcDnsMode $false } }
    @{ n = 'return to DHCP';          f = { Set-PcIpMode $false } }
    @{ n = 'forget the saved values'; f = { Clear-State } }
  )
  foreach ($s in $steps) {
    try { & $s.f }
    catch { Warn "$($s.n) failed: $($_.Exception.Message)" }
    Start-Sleep -Milliseconds 500
  }
  Good 'this PC is a plain client of the router again'
}

# --------------------------------------------------------------- entry point
try {
  switch ($Action) {
  'status'       { Show-Status }
  'verify'       { Invoke-Verify }
  'forward-on'   { Assert-Admin; Set-RouterMode $true }
  'forward-off'  { Assert-Admin; Set-RouterMode $false }
  'ip-static'    { Assert-Admin; Set-PcIpMode $true }
  'ip-dhcp'      { Assert-Admin; Set-PcIpMode $false }
  'dns-public'   { Assert-Admin; Set-PcDnsMode $true }
  'dns-dhcp'     { Assert-Admin; Set-PcDnsMode $false }
  'nat-on'       { Assert-Admin; Set-LanNat $true }
  'nat-off'      { Assert-Admin; Set-LanNat $false }
  'clean-routes' { Assert-Admin; Clear-TunnelRoutes }
  'myip'         { Write-Host ((Get-LanAdapter).IPAddress) }
  'socks'        { if (Test-SocksUp) { Write-Host "$SocksAddr is up"; exit 0 }
                   else { Write-Host "$SocksAddr is down"; exit 1 } }
  'uplinks'      { Get-ProxyUplinks }
  'restart-nic'  { Assert-Admin; $a = Get-LanAdapter
                   Restart-NetAdapter -Name $a.InterfaceAlias
                   Start-Sleep -Seconds 8
                   Show-Status }
  'selftest' {
    Assert-Admin
    $before = $script:Problems
    Invoke-AllOn
    if ($script:Problems -gt $before) {
      Warn 'checks failed - rolling everything back so this PC keeps working'
      Undo-Everything
      Bad 'rolled back - the network of this PC is untouched again'
    } else {
      Good 'the PC side works - now run SHARE_ON.bat to point the router here'
    }
  }
  'all-on' {
    Assert-Admin
    Invoke-AllOn
  }
  'all-off' {
    Assert-Admin
    Undo-Everything
  }
  }
} catch {
  Bad "unexpected error: $($_.Exception.Message)"
  if ($Action -eq 'all-on' -or $Action -eq 'selftest') {
    Warn 'emergency rollback so this PC keeps working'
    try { Undo-Everything } catch { Bad "the rollback also failed: $($_.Exception.Message)" }
  }
  $script:Problems++
}

if ($script:Problems -gt 0) {
  Warn "$($script:Problems) check(s) failed - read the messages above"
  try { Stop-Transcript | Out-Null } catch { }
  exit 1
}
try { Stop-Transcript | Out-Null } catch { }
