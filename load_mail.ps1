# Called by the local Python server. Never echo credentials in diagnostic logs.
$ErrorActionPreference="Stop"
$path=Join-Path $PSScriptRoot "mail_credentials.local.json"
if (-not (Test-Path -LiteralPath $path)) { exit 2 }
$config=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
function Read-Dpapi($value) {
  $secure=ConvertTo-SecureString -String $value
  $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
@{
  POP3_USER=[string]$config.pop3_user
  POP3_PASSWORD=(Read-Dpapi $config.pop3_password_dpapi)
  TRUSTED_SENDER=[string]$config.trusted_sender
  POP3_HOST=[string]$config.pop3_host
  HANDOFF_SECRET=(Read-Dpapi $config.handoff_secret_dpapi)
} | ConvertTo-Json -Compress -Depth 3
