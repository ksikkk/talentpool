"""Start the existing internal talent dashboard with one click on Windows.

Network detection uses Windows local adapter configuration (no external requests).
Intentionally allows only the selected interface's /24 (or narrower) subnet.
Never opens Windows Firewall or forwards ports.
"""
import ipaddress
import json
import os
import subprocess
import sys

PORT = 8090
PS_COMMAND = r"""
$addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
  Where-Object { $_.AddressState -eq 'Preferred' -and
    $_.IPAddress -notmatch '^(127\.|169\.254\.)' })
$defaultIfs = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
  Sort-Object RouteMetric | Select-Object -ExpandProperty InterfaceIndex -Unique)
$items = @($addresses | ForEach-Object {
  $a = $_
  $profile = Get-NetConnectionProfile -InterfaceIndex $a.InterfaceIndex -ErrorAction SilentlyContinue
  [pscustomobject]@{
    ip = $a.IPAddress
    prefix = $a.PrefixLength
    alias = $a.InterfaceAlias
    gateway = ($defaultIfs -contains $a.InterfaceIndex)
    category = if ($profile) { [string]$profile.NetworkCategory } else { 'Unknown' }
  }
})
ConvertTo-Json -InputObject $items -Compress
"""

def get_adapters():
    try:
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PS_COMMAND],
            capture_output=True, text=True, errors="replace", timeout=18
        )
        if p.returncode:
            print("Windows network adapter lookup failed.")
            return []
        records = json.loads(p.stdout.lstrip("\ufeff").strip())
        if isinstance(records, dict):
            records = [records]
        result = []
        for row in records:
            try:
                addr = ipaddress.IPv4Address(row["ip"])
                prefix = int(row["prefix"])
                if addr.is_loopback or addr.is_link_local or not 1 <= prefix <= 32:
                    continue
                result.append({"ip": str(addr), "prefix": prefix,
                               "alias": str(row.get("alias", "")),
                               "gateway": bool(row.get("gateway")),
                               "category": str(row.get("category", "Unknown"))})
            except (KeyError, ValueError, TypeError):
                continue
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []

def pick_adapter(adapters):
    if not adapters:
        print("No active LAN IPv4 adapter was detected.")
        print("Check your network connection, or ask IT if your PC is managed.")
        return None
    adapters.sort(key=lambda a: (
        not a["gateway"],
        a["category"] not in ("DomainAuthenticated", "Private"),
        "Ethernet" not in a["alias"] and "이더넷" not in a["alias"],
        a["ip"]
    ))
    if len(adapters) == 1:
        return adapters[0]
    print("Available PC network addresses:")
    for i, a in enumerate(adapters, 1):
        print(f"  {i}. {a['alias']} - {a['ip']} ({a['category']})")
    preferred = adapters[0]
    answer = input(f"Press Enter for {preferred['ip']}, or enter number 1-{len(adapters)}: ").strip()
    if not answer:
        return preferred
    try:
        return adapters[int(answer) - 1] if 1 <= int(answer) <= len(adapters) else None
    except ValueError:
        return None

def main():
    print("=" * 56)
    print("Talent Pool | One-click PC Server")
    print("=" * 56)
    chosen = pick_adapter(get_adapters())
    if not chosen:
        print("No usable network adapter was selected.")
        return 1
    addr = ipaddress.IPv4Address(chosen["ip"])
    if addr.is_global and chosen["category"] != "DomainAuthenticated":
        print("This IP appears internet-routable and the PC is not on a Windows domain-authenticated network.")
        print("For safety, ask IT to configure an approved internal-only service.")
        return 1

    # The app remains passwordless for the approved test, so restrict remote
    # clients to a small local subnet instead of arbitrary private/public IPs.
    local_subnet = ipaddress.ip_network(
        f"{addr}/{max(chosen['prefix'], 24)}", strict=False
    )
    os.environ["TALENTPOOL_SHARE_SUBNET"] = str(local_subnet)
    print(f"\nThis PC: http://127.0.0.1:{PORT}")
    print(f"Share:   http://{chosen['ip']}:{PORT}")
    print(f"Allowed local subnet: {local_subnet}")
    print("Keep this window open. Only clients in the allowed subnet can access.")
    print("If a coworker cannot connect, company firewall/routing may require IT approval.")
    print("WARNING: allowed clients can view, edit and delete records without login.")
    print("For production, use company SSO and HTTPS.\n")
    try:
        return subprocess.call([
            sys.executable, "-m", "uvicorn", "viewer:app",
            "--host", chosen["ip"], "--port", str(PORT),
            "--no-proxy-headers"
        ])
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    sys.exit(main())
