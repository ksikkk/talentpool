# Run once on the server PC as the Windows user who will start Talent Pool.
# Windows DPAPI encrypts credentials for this user account only.
$ErrorActionPreference="Stop"
Set-Location $PSScriptRoot
$user=(Read-Host "POP3 mail account (Single ID)").Trim()
$sender=(Read-Host "Approved external sender email").Trim()
$password=Read-Host "POP3 password (hidden)" -AsSecureString
$secret=Read-Host "HANDOFF_SECRET used by Talent Scout (hidden)" -AsSecureString
if (-not $user -or -not $sender -or -not $password.Length -or -not $secret.Length) { throw "Missing required setting" }
$obj=@{
  pop3_user=$user
  trusted_sender=$sender
  pop3_host="pop3.samsung.net"
  pop3_password_dpapi=ConvertFrom-SecureString $password
  handoff_secret_dpapi=ConvertFrom-SecureString $secret
}
$target=Join-Path $PSScriptRoot "mail_credentials.local.json"
$obj | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $target -Encoding UTF8
Write-Host "Mail receiver settings saved for this Windows account." -ForegroundColor Green
Write-Host "Close this window and start Talent Pool with python app.py."
