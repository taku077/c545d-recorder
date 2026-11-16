# C545D GStreamer local settings (Windows PowerShell 5.1)
$settingsDir = Join-Path $env:LOCALAPPDATA 'C545D_GStreamer'
$configPath = Join-Path $settingsDir 'settings.json'
$secretPath = Join-Path $settingsDir 'camera_password.dpapi'

function Read-C545DSettings {
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw 'Recording settings do not exist. Run 01_SETTINGS.cmd.'
    }
    $s = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $ipObject = $null
    if (-not [System.Net.IPAddress]::TryParse([string]$s.camera_ip, [ref]$ipObject) -or
        $ipObject.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'Saved camera IP address is invalid. Run 01_SETTINGS.cmd.'
    }
    if ([string]::IsNullOrWhiteSpace([string]$s.camera_user) -or
        [string]::IsNullOrWhiteSpace([string]$s.output_folder)) {
        throw 'Saved settings are incomplete. Run 01_SETTINGS.cmd.'
    }
    return $s
}

function Read-C545DPassword {
    if (-not (Test-Path -LiteralPath $secretPath)) {
        throw 'Saved password is missing. Run 01_SETTINGS.cmd.'
    }
    try {
        $encrypted = (Get-Content -LiteralPath $secretPath -Raw -Encoding ASCII).Trim()
        return (ConvertTo-SecureString -String $encrypted)
    }
    catch {
        throw 'Cannot decrypt saved password. Use the same Windows user account, or run 01_SETTINGS.cmd.'
    }
}
