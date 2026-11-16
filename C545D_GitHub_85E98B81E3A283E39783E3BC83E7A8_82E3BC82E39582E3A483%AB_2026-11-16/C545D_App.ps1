# Tapo C545D lightweight Windows Forms control panel (PowerShell 5.1 / .NET Framework)
# GStreamer recording pipeline itself is unchanged from the previous release.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
. (Join-Path $PSScriptRoot 'CommonSettings.ps1')
. (Join-Path $PSScriptRoot 'SegmentNamer.ps1')

# This signal goes to a dedicated console created for RecordGUIWorker.ps1.
# Do NOT use Stop-Process/Kill: gst-launch -e needs Ctrl+C to finalize MP4.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class C545DConsoleSignal {
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint processId);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
}
'@

$script:worker = $null
$script:startedAt = $null
$script:stopRequested = $false
$script:stopRequestAt = $null
$script:stopSignalFailed = $false
$script:sessionId = ''
$script:stopFile = ''
$script:readyFile = ''
$script:namerWorker = $null
$script:namerFolder = ''
$script:namerReadyFile = ''
$script:namerStopFile = ''
$script:allowExit = $false
$script:lastLog = ''
$script:lastStatus = ''
$script:C545DLastGstSample = $null
$script:stopNoticed15 = $false
$script:stopNoticed60 = $false
$script:emergencyRequested = $false
$script:quitAfterStop = $false
$script:emergencyTask = $null

# Diagnostic journal independent of Start-Transcript. No camera passwords/RTSP URLs.
function Write-C545DStopLog([string]$message) {
    try {
        $dir=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
        if (-not (Test-Path -LiteralPath $dir)) { [void](New-Item -ItemType Directory -Force -Path $dir) }
        $path=Join-Path $dir 'Stop_Control.log'
        $sid=if ($script:sessionId) { $script:sessionId } else { '-' }
        $entry=('{0} [GUI {1}] [session {2}] {3}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'),$PID,$sid,$message)
        Add-Content -LiteralPath $path -Value $entry -Encoding UTF8
    } catch { }
}

function Show-Error([string]$msg) {
    [System.Windows.Forms.MessageBox]::Show($form,$msg,'C545D 録画アプリ',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}
function Make-Label([string]$text,[int]$x,[int]$y,[int]$w=150,[int]$h=24) {
    $v=New-Object System.Windows.Forms.Label
    $v.Text=$text; $v.Location=[System.Drawing.Point]::new($x,$y)
    $v.Size=[System.Drawing.Size]::new($w,$h)
    $v.TextAlign='MiddleLeft'; $form.Controls.Add($v);return $v
}
function Make-TextBox([int]$x,[int]$y,[int]$w,[bool]$password=$false) {
    $v=New-Object System.Windows.Forms.TextBox
    $v.Location=[System.Drawing.Point]::new($x,$y)
    $v.Size=[System.Drawing.Size]::new($w,27)
    if ($password) {$v.UseSystemPasswordChar=$true}
    $form.Controls.Add($v); return $v
}
function Make-Button([string]$text,[int]$x,[int]$y,[int]$w,[int]$h=34) {
    $v=New-Object System.Windows.Forms.Button
    $v.Text=$text; $v.Location=[System.Drawing.Point]::new($x,$y)
    $v.Size=[System.Drawing.Size]::new($w,$h)
    $v.FlatStyle='System'; $form.Controls.Add($v);return $v
}
function Is-Recording {
    if ($null -eq $script:worker) { return $false }
    try {return (-not $script:worker.HasExited)} catch {return $false}
}
function Refresh-Buttons {
    $active=Is-Recording
    $txtIP.Enabled=-not $active; $txtUser.Enabled=-not $active
    $txtPass.Enabled=-not $active; $txtOutput.Enabled=-not $active
    $btnBrowse.Enabled=-not $active; $btnSave.Enabled=-not $active
    $btnStart.Enabled=-not $active
    # Never send Ctrl+C twice while GStreamer waits for EOS: the second
    # interrupt can terminate gst-launch without finalizing the final MP4.
    $btnStop.Enabled=($active -and ((-not $script:stopRequested) -or $script:stopSignalFailed))
    if ($script:stopSignalFailed) { $btnStop.Text='■ 停止通知を再試行' }
    else { $btnStop.Text='■ 録画停止' }
    # A visible escape hatch even after a successful CTRL+C send; never automatic.
    $btnEmergency.Visible=($active -and $script:stopRequested)
    $btnEmergency.Enabled=($active -and $script:stopRequested -and (-not $script:emergencyRequested))
}
# Filename management is event-driven and runs in a dedicated PowerShell worker.
# It watches *new temp files*, not the entire directory every 5/60 seconds.
# The worker starts before recording to avoid missing the first file's event.
function Stop-C545DOptionalNamer {
    if ($script:namerStopFile) {
        try { [IO.File]::WriteAllText($script:namerStopFile,(Get-Date -Format 'o')) } catch { }
    }
    # No forced killing: the watcher may still be waiting for the last MP4
    # to close. It has a 180-second grace period after shutdown is requested.
    if ($script:namerWorker) { try { $script:namerWorker.Dispose() } catch { } }
    $script:namerWorker=$null
    $script:namerFolder=''
    $script:namerReadyFile=''
    $script:namerStopFile=''
}
function Start-C545DOptionalNamer {
    $folder=([string]$txtOutput.Text).Trim()
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { return }
    if ($null -ne $script:namerWorker) {
        try {
            if (-not $script:namerWorker.HasExited -and
                [string]::Equals($script:namerFolder,$folder,[StringComparison]::OrdinalIgnoreCase)) { return }
        } catch { }
        Stop-C545DOptionalNamer
    }
    try {
        $controlDir=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Control'
        [void](New-Item -ItemType Directory -Force -Path $controlDir)
        $id=[guid]::NewGuid().ToString('N')
        $script:namerReadyFile=Join-Path $controlDir ('namer_' + $id + '.ready')
        $script:namerStopFile=Join-Path $controlDir ('namer_' + $id + '.stop')
        $exe=Join-Path $PSHOME 'powershell.exe'
        $worker=Join-Path $PSScriptRoot 'SegmentNamerWorker.ps1'
        # Windows file paths cannot contain a literal double quote.
        $args='-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $worker + '" -OutputDirectory "' + $folder + '" -OwnerProcessId ' + $PID + ' -ReadyFile "' + $script:namerReadyFile + '" -StopFile "' + $script:namerStopFile + '"'
        $script:namerWorker=Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
        $script:namerFolder=$folder
        Write-C545DNamerLog ('Event watcher starting; PID=' + $script:namerWorker.Id)
    }
    catch {
        try { Write-C545DNamerLog ('Optional event watcher launch failed: ' + $_.Exception.Message) } catch { }
        $script:namerWorker=$null
    }
}
# Called ONLY at recording start. If event watcher fails, recording is still
# permitted but temporary names must be manually recovered afterwards.
function Wait-C545DNamerReady {
    Start-C545DOptionalNamer
    for ($i=0;$i -lt 50;$i++) {
        if ($script:namerReadyFile -and (Test-Path -LiteralPath $script:namerReadyFile -PathType Leaf)) { return $true }
        if ($script:namerWorker) { try { if ($script:namerWorker.HasExited) { break } } catch { break } }
        Start-Sleep -Milliseconds 100
    }
    Write-C545DNamerLog 'WARNING: event watcher not ready at recording start. Recording continues; temporary files may need manual rename.'
    return $false
}
function Remove-C545DSessionMarkers {
    foreach ($p in @($script:stopFile, $script:readyFile)) {
        if ($p) { try { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue } catch { } }
    }
    $script:stopFile=''; $script:readyFile=''; $script:sessionId=''
}
function Load-SettingsToForm {
    if ((Test-Path -LiteralPath $configPath) -and (Test-Path -LiteralPath $secretPath)) {
        try {
            $s=Read-C545DSettings
            $txtIP.Text=[string]$s.camera_ip
            $txtUser.Text=[string]$s.camera_user
            $txtOutput.Text=[string]$s.output_folder
            $txtPass.Text=''
            $lblPassword.Text='保存済み：空欄なら変更しません'
            return
        } catch {
            $lblPassword.Text='保存データを読めません。再入力してください。'
        }
    }
    $txtOutput.Text=[Environment]::GetFolderPath('MyDocuments')
    $lblPassword.Text='初回はパスワードを入力してください'
}
function Save-Settings {
    $ip=([string]$txtIP.Text).Trim()
    $user=([string]$txtUser.Text).Trim()
    $dir=([string]$txtOutput.Text).Trim()
    $newPass=[string]$txtPass.Text
    $ipObj=$null
    if (-not [System.Net.IPAddress]::TryParse($ip,[ref]$ipObj) -or
        $ipObj.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'カメラのIPv4アドレスを確認してください。'
    }
    if ([string]::IsNullOrWhiteSpace($user)) { throw 'カメラのユーザー名を入力してください。' }
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) { throw '保存先フォルダーが存在しません。' }
    if ([string]::IsNullOrEmpty($newPass) -and (-not (Test-Path -LiteralPath $secretPath))) {
        throw '初回はカメラのパスワードを入力してください。'
    }
    if ([string]::IsNullOrEmpty($newPass)) {
        # Do not overwrite a valid existing secret with an empty password.
        $old=Read-C545DPassword
        if ($old) { $old.Dispose() }
    }
    # Check write permission without overwriting or modifying existing videos.
    $check=Join-Path $dir ('.C545D_access_check_' + [guid]::NewGuid().ToString('N'))
    try { [IO.File]::WriteAllText($check,'ok') }
    finally { if (Test-Path -LiteralPath $check) { Remove-Item -LiteralPath $check -Force } }
    New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
    $cfg=[ordered]@{version=2;camera_ip=$ip;camera_user=$user;output_folder=$dir}
    $json=$cfg | ConvertTo-Json -Depth 4
    $tmpSettings=$configPath + '.new'
    $utf8=New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($tmpSettings,$json,$utf8)
    try {
        if (-not [string]::IsNullOrEmpty($newPass)) {
            $secure=ConvertTo-SecureString -String $newPass -AsPlainText -Force
            try { $encrypted=ConvertFrom-SecureString -SecureString $secure }
            finally { $secure.Dispose() }
            $tmpSecret=$secretPath+'.new'
            [IO.File]::WriteAllText($tmpSecret,$encrypted,[Text.Encoding]::ASCII)
            Move-Item -LiteralPath $tmpSecret -Destination $secretPath -Force
            $txtPass.Clear()
        }
        Move-Item -LiteralPath $tmpSettings -Destination $configPath -Force
    }
    finally {
        if (Test-Path -LiteralPath $tmpSettings) {Remove-Item -LiteralPath $tmpSettings -Force}
    }
    $lblPassword.Text='保存済み：空欄なら変更しません'
    $lblStatus.Text='設定を保存しました。録画開始できます。'
    return $true
}
function Request-Stop {
    if (-not (Is-Recording)) { return }
    if ($script:stopRequested -and (-not $script:stopSignalFailed)) { return }
    $again=$script:stopRequested
    $script:stopRequested=$true
    if (-not $again) { $script:stopRequestAt=Get-Date }
    Write-C545DStopLog ('Stop clicked; workerPID=' + $script:worker.Id + '; again=' + $again)
    # Durable stop intent first: even if Ctrl+C arrives too early or the
    # native process exits with an error, Record.ps1 must never reconnect.
    if ($script:stopFile) {
        try {
            [IO.File]::WriteAllText($script:stopFile, (Get-Date -Format 'o'))
            Write-C545DStopLog 'Stop marker written.'
        }
        catch {
            # Never signal if stop state cannot be persisted. Otherwise a
            # nonzero gst exit could trigger a new RTSP connection.
            $script:stopSignalFailed=$true
            Write-C545DStopLog ('ERROR stop marker write: ' + $_.Exception.Message)
            Show-Error ('停止要求の記録に失敗しました。録画は強制終了していません。' + [Environment]::NewLine + $_.Exception.Message)
            Refresh-Buttons
            return
        }
    }
    $lblStatus.Text='停止要求を記録しました。MP4確定を待機しています…'
    Refresh-Buttons
    # The worker installs its Ctrl+C handler before writing .ready.
    # Before .ready exists, the .stop marker is enough to prevent startup.
    if (-not $script:readyFile -or -not (Test-Path -LiteralPath $script:readyFile)) {
        $lblStatus.Text='録画準備中のため停止を予約しました。安全に終了します…'
        Write-C545DStopLog 'Worker not ready; stop marker will prevent recording startup.'
        return
    }
    $attached=$false
    try {
        [void][C545DConsoleSignal]::FreeConsole()
        $attached=[C545DConsoleSignal]::AttachConsole([uint32]$script:worker.Id)
        if (-not $attached) { throw ('録画プロセスのコンソールへ接続できませんでした。Win32=' + [Runtime.InteropServices.Marshal]::GetLastWin32Error()) }
        Write-C545DStopLog 'Attached to recording worker console.'
        if (-not [C545DConsoleSignal]::SetConsoleCtrlHandler([IntPtr]::Zero,$true)) {
            throw 'GUI側のCtrl+C保護を設定できませんでした。'
        }
        # CTRL_C_EVENT=0, process group=0: gst-launch and PowerShell both
        # receive it, but the worker has a handler which keeps it alive.
        $sent=[C545DConsoleSignal]::GenerateConsoleCtrlEvent(0,0)
        if (-not $sent) { throw ('Ctrl+C終了通知を送信できませんでした。Win32=' + [Runtime.InteropServices.Marshal]::GetLastWin32Error()) }
        Write-C545DStopLog 'CTRL_C_EVENT sent to worker console. Awaiting GStreamer EOS.'
        $script:stopSignalFailed=$false
        $lblStatus.Text='終了通知を送信しました。MP4確定処理中…'
    }
    catch {
        # Leave stop marker in place. Do not reset stop state and reconnect.
        $script:stopSignalFailed=$true
        Write-C545DStopLog ('ERROR stop signal: ' + $_.Exception.Message)
        $lblStatus.Text='終了通知に問題があります。停止要求は保持しています。'
        Show-Error ('停止要求は記録済みですが、Ctrl+C通知に失敗しました。' + [Environment]::NewLine +
            '録画を強制終了していません。状態・ログを確認してください。' + [Environment]::NewLine + $_.Exception.Message)
    }
    finally {
        if ($attached) { [void][C545DConsoleSignal]::FreeConsole() }
        [void][C545DConsoleSignal]::SetConsoleCtrlHandler([IntPtr]::Zero,$false)
        Refresh-Buttons
    }
}

# Last resort only. Do not automatically terminate a pipeline because doing so may
# leave the most recently opened MP4 unfinalized. /T targets only this worker
# process and its descendants, not every gst-launch process on the computer.
function Request-EmergencyStop {
    if (-not (Is-Recording)) { return }
    if (-not $script:stopRequested) {
        [System.Windows.Forms.MessageBox]::Show($form,
            'まず「録画停止」でMP4の正常確定を試してください。',
            'C545D 録画アプリ',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
        return
    }
    if ($script:emergencyRequested) { return }
    $warning=('通常停止で終了できない場合の最終手段です。' + [Environment]::NewLine +
        'GStreamerを含む、この録画セッションのプロセスを強制終了します。' + [Environment]::NewLine +
        '最後のMP4が再生できなくなる可能性があります。' + [Environment]::NewLine +
        'このPCで録画中の別のアプリ・別セッションは対象にしません。' + [Environment]::NewLine + [Environment]::NewLine +
        '緊急停止を実行しますか？')
    $choice=[System.Windows.Forms.MessageBox]::Show($form,$warning,'緊急停止の確認',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning,
        [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
    if ($choice -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    try {
        # Retain a durable stop marker if possible; taskkill /T /F kills both
        # the recorder PowerShell worker and its direct child gst-launch.
        if ($script:stopFile) {
            try { [IO.File]::WriteAllText($script:stopFile,(Get-Date -Format 'o')) }
            catch { Write-C545DStopLog ('WARNING: emergency marker write failed: ' + $_.Exception.Message) }
        }
        if (-not (Is-Recording)) { return }
        $workerPid=[int]$script:worker.Id
        $exe=Join-Path $env:SystemRoot 'System32\taskkill.exe'
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw ('taskkill.exe not found: ' + $exe) }
        Write-C545DStopLog ('EMERGENCY STOP CONFIRMED. taskkill /PID ' + $workerPid + ' /T /F')
        # Do not wait on the UI thread. The timer will report when the worker exits.
        $script:emergencyTask=Start-Process -FilePath $exe -ArgumentList ('/PID ' + $workerPid + ' /T /F') -WindowStyle Hidden -PassThru
        $script:emergencyRequested=$true
        $lblStatus.Text='緊急停止を要求しました。最終MP4の再生可否を確認してください。'
        Refresh-Buttons
    } catch {
        $script:emergencyRequested=$false
        Write-C545DStopLog ('ERROR emergency stop: ' + $_.Exception.Message)
        Show-Error ('緊急停止処理を起動できませんでした。' + [Environment]::NewLine + $_.Exception.Message)
        Refresh-Buttons
    }
}

function Request-AppExit {
    if (Is-Recording) {
        $question=('録画中です。通常停止を要求し、終了を確認できたらアプリも終了しますか？' + [Environment]::NewLine +
            '通常停止が進まない場合は「緊急停止」を使用できます。')
        $answer=[System.Windows.Forms.MessageBox]::Show($form,$question,'録画中の終了',
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question,
            [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
        if ($answer -eq [System.Windows.Forms.DialogResult]::Yes) {
            $script:quitAfterStop=$true
            Request-Stop
        }
        return
    }
    $script:allowExit=$true
    $form.Close()
}

$form=New-Object System.Windows.Forms.Form
$form.Text='C545D 録画アプリ'
$form.StartPosition='CenterScreen'
$form.ClientSize=[System.Drawing.Size]::new(730,600)
$form.MinimumSize=[System.Drawing.Size]::new(745,635)
$form.MaximizeBox=$false
$form.FormBorderStyle='FixedSingle'
$form.Font=[System.Drawing.Font]::new('Meiryo UI',9)
$form.BackColor=[Drawing.Color]::FromArgb(248,250,252)

$header=Make-Label 'Tapo C545D  2画面録画' 22 12 640 40
$header.Font=[System.Drawing.Font]::new('Meiryo UI',16,[Drawing.FontStyle]::Bold)
$caption=Make-Label '広角＋望遠を横並びでMP4保存  |  音声1系統  |  1時間分割' 24 57 670 26
$caption.ForeColor=[Drawing.Color]::FromArgb(80,88,102)

Make-Label 'カメラIPv4' 24 112 125 | Out-Null
$txtIP=Make-TextBox 160 110 225
Make-Label 'アカウント' 400 112 96 | Out-Null
$txtUser=Make-TextBox 500 110 200
Make-Label 'パスワード' 24 160 125 | Out-Null
$txtPass=Make-TextBox 160 158 225 $true
$lblPassword=Make-Label '' 398 160 308 27
$lblPassword.Font=[System.Drawing.Font]::new('Meiryo UI',8)
$lblPassword.ForeColor=[Drawing.Color]::FromArgb(85,95,112)
Make-Label 'MP4保存先' 24 210 125 | Out-Null
$txtOutput=Make-TextBox 160 208 420
$btnBrowse=Make-Button '参照…' 590 205 110
$btnSave=Make-Button '設定を保存' 160 257 170 38
$btnStart=Make-Button '● 録画開始' 24 322 215 48
$btnStop=Make-Button '■ 録画停止' 251 322 215 48
$btnStop.Enabled=$false
$btnOpen=Make-Button '保存先を開く' 478 322 222 48
$lblStatus=Make-Label '準備中' 24 395 670 35
$lblStatus.ForeColor=[Drawing.Color]::FromArgb(28,81,123)
$lblElapsed=Make-Label '録画時間：—' 24 432 235 28
$lblGstMem=Make-Label 'GStreamer メモリ：—' 255 432 285 28
$lblGstMem.Font=[System.Drawing.Font]::new('Meiryo UI',8)
$lblGstMem.ForeColor=[Drawing.Color]::FromArgb(80,88,102)
$btnLog=Make-Button 'ログを開く' 546 426 154 34
$btnEmergency=Make-Button '緊急停止（最後のMP4破損の可能性）' 24 482 445 42
$btnEmergency.Visible=$false
$btnEmergency.Enabled=$false
$btnEmergency.ForeColor=[Drawing.Color]::DarkRed
$btnQuit=Make-Button 'アプリを終了' 480 482 220 42
$lblFoot=Make-Label '最小化すると通知領域に格納します。映像プレビューなし・軽量動作。' 24 546 685 25
$lblFoot.ForeColor=[Drawing.Color]::FromArgb(96,101,108)
$lblFoot.Font=[System.Drawing.Font]::new('Meiryo UI',8)

$tray=New-Object System.Windows.Forms.NotifyIcon
$tray.Icon=[System.Drawing.SystemIcons]::Application
$tray.Text='C545D 録画アプリ'
$tray.Visible=$true
$trayMenu=New-Object System.Windows.Forms.ContextMenuStrip
$menuShow=$trayMenu.Items.Add('ウィンドウを表示')
$menuStop=$trayMenu.Items.Add('録画停止（MP4確定）')
$menuEmergency=$trayMenu.Items.Add('緊急停止（最終MP4破損の危険）')
$menuExit=$trayMenu.Items.Add('アプリを終了')
$tray.ContextMenuStrip=$trayMenu

$btnBrowse.Add_Click({
    $dlg=New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description='MP4を直接保存するフォルダーを選択してください。'
    $dlg.RootFolder=[Environment+SpecialFolder]::MyComputer
    $dlg.ShowNewFolderButton=$true
    if (Test-Path -LiteralPath $txtOutput.Text -PathType Container) { $dlg.SelectedPath=$txtOutput.Text }
    if ($dlg.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {
        $txtOutput.Text=$dlg.SelectedPath
    }
    $dlg.Dispose()
})
$btnSave.Add_Click({
    try {[void](Save-Settings)}
    catch {Show-Error $_.Exception.Message}
})
$btnStart.Add_Click({
    if (Is-Recording) {return}
    try {
        [void](Save-Settings)
        [void](Wait-C545DNamerReady)
        $workerScript=Join-Path $PSScriptRoot 'RecordGUIWorker.ps1'
        $powershellExe=Join-Path $PSHOME 'powershell.exe'
        $controlDir=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Control'
        New-Item -ItemType Directory -Force -Path $controlDir | Out-Null
        $script:sessionId=[guid]::NewGuid().ToString('N')
        $script:stopFile=Join-Path $controlDir ('session_' + $script:sessionId + '.stop')
        $script:readyFile=Join-Path $controlDir ('session_' + $script:sessionId + '.ready')
        # Unique session identifiers prevent an old recording's stop marker
        # from affecting a subsequent start/restart.
        $workerArgs='-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $workerScript + '" -SessionId ' + $script:sessionId
        # Start-Process with ShellExecute / a PRIVATE hidden Windows console.
        $script:worker=Start-Process -FilePath $powershellExe -ArgumentList $workerArgs -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
        if ($null -eq $script:worker) {throw '録画プロセスを開始できませんでした。'}
        $script:startedAt=Get-Date
        $script:stopRequested=$false
        $script:stopRequestAt=$null
        $script:stopSignalFailed=$false
        $script:stopNoticed15=$false
        $script:stopNoticed60=$false
        $script:emergencyRequested=$false
        $script:quitAfterStop=$false
        Write-C545DStopLog ('Recording worker launched; PID=' + $script:worker.Id)
        $lblStatus.Text='録画プロセスを起動しました。接続中…'
        Refresh-Buttons
    }
    catch {
        if (-not (Is-Recording)) { Remove-C545DSessionMarkers }
        Show-Error $_.Exception.Message;Refresh-Buttons
    }
})
$btnStop.Add_Click({Request-Stop})
$btnEmergency.Add_Click({Request-EmergencyStop})
$btnQuit.Add_Click({Request-AppExit})
$btnOpen.Add_Click({
    $path=([string]$txtOutput.Text).Trim()
    if (Test-Path -LiteralPath $path -PathType Container) {
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $path + '"') | Out-Null
    } else { Show-Error '保存先フォルダーが存在しません。' }
})
$btnLog.Add_Click({
    $logDir=Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
    if (Test-Path -LiteralPath $logDir -PathType Container) {
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $logDir + '"') | Out-Null
    } else {
        [System.Windows.Forms.MessageBox]::Show($form,'まだ録画ログはありません。','ログ') | Out-Null
    }
})
$menuShow.Add_Click({$form.Show();$form.WindowState='Normal';$form.Activate()})
$menuStop.Add_Click({Request-Stop})
$menuEmergency.Add_Click({$form.Show(); $form.WindowState='Normal'; $form.Activate(); Request-EmergencyStop})
$menuExit.Add_Click({$form.Show(); $form.WindowState='Normal'; Request-AppExit})
$tray.Add_DoubleClick({$form.Show();$form.WindowState='Normal';$form.Activate()})
$form.Add_Resize({if ($form.WindowState -eq [System.Windows.Forms.FormWindowState]::Minimized) {$form.Hide()}})
$form.Add_FormClosing({
    param($s,$e)
    if (Is-Recording) {
        $e.Cancel=$true
        # Do not silently hide on X. A visible exit path is essential when
        # normal MP4 finalization stalls; explicit emergency exit is available.
        $form.Show(); $form.WindowState='Normal'
        Request-AppExit
    }
})
$form.Add_FormClosed({$tray.Visible=$false;$tray.Dispose()})

# Read-only process health sampling. Never stop or restart the encoder here:
# forced termination can leave the current MP4 unfinished.
function Update-C545DGstHealth {
    $procs = @(Get-Process -Name 'gst-launch-1.0' -ErrorAction SilentlyContinue | Sort-Object Id)
    if ($procs.Count -eq 0) {
        $lblGstMem.Text='GStreamer メモリ：—'
        $lblGstMem.ForeColor=[Drawing.Color]::FromArgb(80,88,102)
        $script:C545DLastGstSample=$null
        return
    }
    [long]$working=0
    [long]$private=0
    [double]$totalCpu=0
    foreach ($p in $procs) {
        try {
            $working += [long]$p.WorkingSet64
            $private += [long]$p.PrivateMemorySize64
            $totalCpu += [double]$p.CPU
        } catch { }
    }
    $ids = ($procs | ForEach-Object { [string]$_.Id }) -join ';'
    $now = Get-Date
    $cpuText = ''
    $csvCpu = ''
    if ($null -ne $script:C545DLastGstSample -and
        $script:C545DLastGstSample.Ids -eq $ids) {
        $elapsedSecs = ($now - $script:C545DLastGstSample.Time).TotalSeconds
        if ($elapsedSecs -gt 1) {
            $cpuPercent = (($totalCpu - $script:C545DLastGstSample.Cpu) /
                ($elapsedSecs * [Environment]::ProcessorCount)) * 100.0
            $cpuPercent = [Math]::Max(0,[Math]::Min(100,$cpuPercent))
            $csvCpu = $cpuPercent.ToString('F1',[Globalization.CultureInfo]::InvariantCulture)
            $cpuText = (' / CPU {0:N0}%' -f $cpuPercent)
        }
    }
    $script:C545DLastGstSample = @{ Ids=$ids; Time=$now; Cpu=$totalCpu }
    $workingMB = [Math]::Round($working / 1MB,1)
    $privateMB = [Math]::Round($private / 1MB,1)
    $lblGstMem.Text = ('GStreamer {0:N0}MB{1}' -f $workingMB,$cpuText)
    if ($workingMB -ge 1536) {
        $lblGstMem.ForeColor = [Drawing.Color]::Firebrick
    } else {
        $lblGstMem.ForeColor = [Drawing.Color]::FromArgb(80,88,102)
    }
    # Very small time-series CSV, 1 line every 30 seconds. No camera secrets.
    try {
        $healthDir = Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
        if (-not (Test-Path -LiteralPath $healthDir)) {
            New-Item -ItemType Directory -Path $healthDir -Force | Out-Null
        }
        $healthPath = Join-Path $healthDir 'Memory_Trend.csv'
        if (-not (Test-Path -LiteralPath $healthPath)) {
            Add-Content -LiteralPath $healthPath -Value 'Timestamp,PID,WorkingSet_MB,Private_MB,CPU_Percent' -Encoding UTF8
        }
        $row = ('{0},{1},{2},{3},{4}' -f
            $now.ToString('yyyy-MM-dd HH:mm:ss'),$ids,
            $workingMB.ToString('F1',[Globalization.CultureInfo]::InvariantCulture),
            $privateMB.ToString('F1',[Globalization.CultureInfo]::InvariantCulture),$csvCpu)
        Add-Content -LiteralPath $healthPath -Value $row -Encoding UTF8
    } catch { }
}

$script:C545DNamerTick=0
$timer=New-Object System.Windows.Forms.Timer
$timer.Interval=1000
$timer.Add_Tick({
    $script:C545DNamerTick++
    if (($script:C545DNamerTick % 30) -eq 0) {
        try { Update-C545DGstHealth } catch { }
    }
    # Only check that the event watcher process is alive; no directory scan.
    if (($script:C545DNamerTick % 10) -eq 0) {
        Start-C545DOptionalNamer
    }
    if ($null -ne $script:emergencyTask) {
        try {
            if ($script:emergencyTask.HasExited) {
                $exitCode=[int]$script:emergencyTask.ExitCode
                Write-C545DStopLog ('Emergency taskkill exited with code ' + $exitCode)
                $script:emergencyTask.Dispose()
                $script:emergencyTask=$null
                if ((Is-Recording) -and $exitCode -ne 0) {
                    $script:emergencyRequested=$false
                    $lblStatus.Text='緊急停止が失敗しました。ログを確認し、必要なら再試行してください。'
                    Refresh-Buttons
                }
            }
        } catch { Write-C545DStopLog ('WARNING emergency helper status: ' + $_.Exception.Message) }
    }
    if ($null -ne $script:worker) {
        if (Is-Recording) {
            if ($script:startedAt) {
                $elapsed=(Get-Date)-$script:startedAt
                $lblElapsed.Text='起動経過：' + ('{0:00}:{1:00}:{2:00}' -f [int][math]::Floor($elapsed.TotalHours),$elapsed.Minutes,$elapsed.Seconds)
            }
            if ($script:stopRequested) {
                if ($script:stopRequestAt) {
                    $stopSecs=((Get-Date)-$script:stopRequestAt).TotalSeconds
                    if ($stopSecs -ge 60) {
                        $lblStatus.Text='停止が60秒以上続いています。ログを確認してください。再送は危険です。'
                        if (-not $script:stopNoticed60) {
                            Write-C545DStopLog 'WARNING: worker still alive 60s after stop request; not forcing termination.'
                            $script:stopNoticed60=$true
                        }
                    } elseif ($stopSecs -ge 15) {
                        $lblStatus.Text='MP4確定待ち（15秒以上）。再度Ctrl+Cを送らないでください。'
                        if (-not $script:stopNoticed15) {
                            Write-C545DStopLog 'WARNING: worker still alive 15s after stop request.'
                            $script:stopNoticed15=$true
                        }
                    }
                }
            } else {$lblStatus.Text='録画プロセス実行中（接続状況はログで確認）'}
            Refresh-Buttons
        } else {
            $exitCode=-1
            try {$exitCode=$script:worker.ExitCode} catch {}
            try {$script:worker.Dispose()} catch {}
            $script:worker=$null
            $wasStopping=$script:stopRequested
            Write-C545DStopLog ('Recording worker exited; exitCode=' + $exitCode + '; stopRequested=' + $wasStopping)
            $script:stopRequested=$false
            $script:stopRequestAt=$null
            $script:stopSignalFailed=$false
            $script:emergencyRequested=$false
            Remove-C545DSessionMarkers
            if ($wasStopping) {$lblStatus.Text='録画処理が終了しました。最後のMP4が再生できるか確認してください。'}
            else {$lblStatus.Text=('録画プロセスが終了しました（終了コード ' + $exitCode + '）。ログを確認してください。')}
            Refresh-Buttons
            if ($script:quitAfterStop) {
                $script:quitAfterStop=$false
                $script:allowExit=$true
                $form.Close()
                return
            }
        }
    }
})
$timer.Start()
Load-SettingsToForm
Start-C545DOptionalNamer
$lblStatus.Text='設定を確認し、「録画開始」を押してください。'
Refresh-Buttons
[void][System.Windows.Forms.Application]::Run($form)
$timer.Stop();$timer.Dispose()
Stop-C545DOptionalNamer
