# Native WinForms settings bridge: DPAPI on the same Windows user.
# Receives JSON ONLY on standard input; NEVER accepts password on command line.
# Existing CommonSettings.ps1/Record.ps1 remain authoritative consumers.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'CommonSettings.ps1')
try {
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $ip = ([string]$request.camera_ip).Trim()
    $user = ([string]$request.camera_user).Trim()
    $folder = ([string]$request.output_folder).Trim()
    $password = [string]$request.new_password
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($ip, [ref]$parsed) -or
        $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'Invalid IPv4.'
    }
    if ([string]::IsNullOrWhiteSpace($user)) { throw 'Missing camera user.' }
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { throw 'Missing output folder.' }
    if ([string]::IsNullOrEmpty($password) -and
        -not (Test-Path -LiteralPath $secretPath -PathType Leaf)) {
        throw 'First-time camera password required.'
    }
    if ([string]::IsNullOrEmpty($password)) {
        # Verify the existing user-scoped DPAPI secret is actually readable;
        # never silently retain a broken secret.
        $old = Read-C545DPassword
        if ($old) { $old.Dispose() }
    }
    $probe = Join-Path $folder ('.C545D_access_check_' + [guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($probe, 'ok') }
    finally { if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Force } }
    New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
    $data = [ordered]@{ version=2;camera_ip=$ip;camera_user=$user;output_folder=$folder }
    $tmpSettings = $configPath + '.new'
    $json = $data | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText($tmpSettings, $json, (New-Object Text.UTF8Encoding($false)))
    try {
        if (-not [string]::IsNullOrEmpty($password)) {
            $sec = ConvertTo-SecureString -String $password -AsPlainText -Force
            try { $ciphertext = ConvertFrom-SecureString -SecureString $sec }
            finally { $sec.Dispose() }
            $tmpSecret = $secretPath + '.new'
            [IO.File]::WriteAllText($tmpSecret, $ciphertext, [Text.Encoding]::ASCII)
            Move-Item -LiteralPath $tmpSecret -Destination $secretPath -Force
            $ciphertext = $null
        }
        Move-Item -LiteralPath $tmpSettings -Destination $configPath -Force
    }
    finally {
        if (Test-Path -LiteralPath $tmpSettings) {
            Remove-Item -LiteralPath $tmpSettings -Force
        }
    }
    $password = $null
    Write-Output 'OK'
    exit 0
}
catch {
    # Do not echo request content or passwords into UI, logs or public CI.
    [Console]::Error.WriteLine('C545D settings save failed.')
    exit 1
}
