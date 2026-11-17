# PowerShell 5.1 worker with a shared private console for gst-launch -e.
# A Ctrl+C from the GUI MUST NOT terminate this PowerShell worker before the
# GStreamer process has had a chance to finalize its active MP4 fragment.
param([Parameter(Mandatory=$true)][string]$SessionId)
$ErrorActionPreference = 'Stop'
$validGuid = [guid]::Empty
if (-not [guid]::TryParse($SessionId, [ref]$validGuid)) {
    throw 'Invalid recording session ID.'
}
$SessionId = $validGuid.ToString('N')
$controlDir = Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Control'
New-Item -ItemType Directory -Force -Path $controlDir | Out-Null
$stopFile = Join-Path $controlDir ('session_' + $SessionId + '.stop')
$readyFile = Join-Path $controlDir ('session_' + $SessionId + '.ready')

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
public static class C545DWorkerStopSignal {
    private delegate bool ConsoleHandler(uint controlType);
    private static ConsoleHandler _handler;
    private static int _requested;
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool SetConsoleCtrlHandler(ConsoleHandler handler, bool add);
    private static bool Handle(uint controlType) {
        if (controlType == 0) { // CTRL_C_EVENT
            Interlocked.Increment(ref _requested);
            return true;  // Do not let PowerShell abort gst-launch prematurely.
        }
        return false;
    }
    public static bool StopRequested { get { return Interlocked.CompareExchange(ref _requested, 0, 0) != 0; } }
    // Record.ps1 reads a count after gst-launch returns. No I/O is performed
    // on the Windows console control callback thread.
    public static int TakeCtrlCSignals() { return Interlocked.Exchange(ref _requested, 0); }
    public static bool Install() {
        _handler = new ConsoleHandler(Handle); // rooted for process lifetime
        return SetConsoleCtrlHandler(_handler, true);
    }
}
'@
if (-not [C545DWorkerStopSignal]::Install()) {
    throw 'Cannot install the PowerShell console stop handler.'
}
# Only after the handler is installed can the GUI safely signal this console.
[IO.File]::WriteAllText($readyFile, [string]$PID)
$logDir = Join-Path $env:LOCALAPPDATA 'C545D_GStreamer\Logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir ('Recording_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + $PID + '.txt')
try { Start-Transcript -LiteralPath $logPath -ErrorAction Stop | Out-Null }
catch { $logPath = $null }
Write-Host ('Worker initialized. PID=' + $PID + '; stop session=' + $SessionId)
try {
    if (Test-Path -LiteralPath $stopFile) {
        Write-Host 'Stop requested before recording startup.'
    } else {
        & (Join-Path $PSScriptRoot 'Record.ps1') -StopFile $stopFile
        Write-Host ('Record.ps1 returned; stopMarker=' + (Test-Path -LiteralPath $stopFile) +
            '; pendingCtrlCEvents=' + [C545DWorkerStopSignal]::TakeCtrlCSignals())
    }
}
catch {
    Write-Host ('RECORD ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    if ($logPath) { try { Stop-Transcript | Out-Null } catch {} }
    try { Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue } catch {}
}
