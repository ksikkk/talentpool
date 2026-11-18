# Start the internal Talent Pool using this PC's actual LAN IPv4 address.
# Do not use on public networks. Remote clients must be explicitly approved by IT.
param(
    [string]$ServerIP = "",
    [string[]]$AllowedClientIPs = @(),
    [int]$Port = 8090
)
$ErrorActionPreference = "Stop"

function Test-PrivateIPv4([string]$Address) {
    $parsed = $null
    if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$parsed)) { return $false }
    if ($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { return $false }
    $octets = $parsed.GetAddressBytes()
    return ($octets[0] -eq 10) -or ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or ($octets[0] -eq 192 -and $octets[1] -eq 168)
}

if (-not $ServerIP) {
    $candidates = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.AddressState -eq "Preferred" -and (Test-PrivateIPv4 $_.IPAddress) } |
        Select-Object -ExpandProperty IPAddress -Unique)
    if ($candidates.Count -ne 1) {
        Write-Host "Unable to choose a single LAN address. Candidates: $($candidates -join ', ')" -ForegroundColor Yellow
        throw "Pass -ServerIP with your approved server PC private IPv4 address (see ipconfig)."
    }
    $ServerIP = $candidates[0]
}
if (-not (Test-PrivateIPv4 $ServerIP)) {
    throw "ServerIP must be a private IPv4 address (10.x, 172.16-31.x, 192.168.x)."
}
$allowed = @($ServerIP)
foreach ($address in $AllowedClientIPs) {
    if (-not (Test-PrivateIPv4 $address)) {
        throw "Only approved private IPv4 client addresses are supported: $address"
    }
    $allowed += $address
}
$env:INTERNAL_ALLOWED_CIDRS = (($allowed | Select-Object -Unique | ForEach-Object { "$_/32" }) -join ",")
Write-Host "Local Talent Pool URL: http://$($ServerIP):$Port" -ForegroundColor Green
if ($AllowedClientIPs.Count -eq 0) {
    Write-Host "Local-server-only access. To add another approved PC: .\start_lan.ps1 -AllowedClientIPs '10.1.2.3'"
} else {
    Write-Host "Approved remote client IP(s): $($AllowedClientIPs -join ', ')"
    Write-Host "IT-approved Windows Firewall TCP port $Port source-IP restriction is still required." -ForegroundColor Yellow
}
python -m uvicorn viewer:app --host $ServerIP --port $Port
