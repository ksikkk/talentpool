# Launch Talent Pool on this PC's actual private IPv4.
# All clients on routed private networks can connect if company firewall permits.
# LAN testing only. No NAT forwarding, public tunnels, or unapproved networks.
param(
    [string]$ServerIP = "",
    [int]$Port = 8090
)
$ErrorActionPreference = "Stop"
function Test-PrivateIPv4([string]$Address) {
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed)) { return $false }
    if ($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $o = $parsed.GetAddressBytes()
    return ($o[0] -eq 10) -or ($o[0] -eq 172 -and $o[1] -ge 16 -and $o[1] -le 31) -or ($o[0] -eq 192 -and $o[1] -eq 168)
}
if (-not $ServerIP) {
    $candidates = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.AddressState -eq "Preferred" -and (Test-PrivateIPv4 $_.IPAddress) } |
        Select-Object -ExpandProperty IPAddress -Unique)
    if ($candidates.Count -ne 1) {
        Write-Host "Multiple/no private IPv4 adapters: $($candidates -join ', ')" -ForegroundColor Yellow
        throw "Use .\start_lan.ps1 -ServerIP 'your actual private IPv4' (see ipconfig)"
    }
    $ServerIP = $candidates[0]
}
if (-not (Test-PrivateIPv4 $ServerIP)) {
    throw "ServerIP must be a local private IPv4."
}
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Choose a TCP port between 1024 and 65535" }
$env:TALENTPOOL_LAN_SHARE = "1"
Write-Host ""
Write-Host "Talent Pool LAN URL: http://$($ServerIP):$Port" -ForegroundColor Green
Write-Host "Share this address only with approved internal coworkers."
Write-Host "No app password. Everyone who can reach the port from a private IPv4 can view/edit/delete data." -ForegroundColor Yellow
Write-Host "Windows Firewall or corporate network rules must permit inbound TCP $Port. This script does not modify firewall." -ForegroundColor Yellow
Write-Host ""
python -m uvicorn viewer:app --host $ServerIP --port $Port --no-proxy-headers
