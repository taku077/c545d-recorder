# Event-based C545D MP4 renamer (PowerShell 5.1, Windows 10).
# No periodic Get-ChildItem and no modifications to the GStreamer pipeline.
param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][int]$OwnerProcessId,
    [Parameter(Mandatory=$true)][string]$ReadyFile,
    [Parameter(Mandatory=$true)][string]$StopFile,
    [switch]$EnableMetadataDiagnostics,
    [string]$MetadataProbeSha256
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'SegmentNamer.ps1')

# C# callbacks do NOT run PowerShell. They only enqueue paths for the single
# PowerShell loop, so FileSystemWatcher event delivery is never blocked by ffprobe.
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Concurrent;
using System.Threading;
public sealed class C545DFileEvents : IDisposable {
    private readonly FileSystemWatcher watcher;
    private readonly ConcurrentQueue<string> paths = new ConcurrentQueue<string>();
    private readonly AutoResetEvent wake = new AutoResetEvent(false);
    private int errors = 0;
    public C545DFileEvents(string folder) {
        watcher = new FileSystemWatcher(folder, "*.mp4");
        watcher.IncludeSubdirectories = false;
        watcher.NotifyFilter = NotifyFilters.FileName | NotifyFilters.CreationTime;
        watcher.InternalBufferSize = 16384;
        watcher.Created += OnCreated;
        watcher.Renamed += OnRenamed;
        watcher.Error += OnError;
        watcher.EnableRaisingEvents = true;
    }
    private void OnCreated(object sender, FileSystemEventArgs e) { Enqueue(e.FullPath); }
    private void OnRenamed(object sender, RenamedEventArgs e) { Enqueue(e.FullPath); }
    private void OnError(object sender, ErrorEventArgs e) {
        Interlocked.Increment(ref errors);
        wake.Set();
    }
    private void Enqueue(string path) {
        paths.Enqueue(path);
        wake.Set();
    }
    public bool TryTake(out string path) { return paths.TryDequeue(out path); }
    public int TakeErrors() { return Interlocked.Exchange(ref errors, 0); }
    public bool Wait(int milliseconds) { return wake.WaitOne(milliseconds); }
    public void Dispose() {
        watcher.EnableRaisingEvents = false;
        watcher.Dispose();
        wake.Dispose();
    }
}
'@ -ErrorAction Stop

$events=$null
$pending=New-Object 'System.Collections.Generic.Dictionary[string,datetime]' ([StringComparer]::OrdinalIgnoreCase)
$lastAttempt=New-Object 'System.Collections.Generic.Dictionary[string,datetime]' ([StringComparer]::OrdinalIgnoreCase)
$closingSince=$null
$loopCount=0
try {
    if($EnableMetadataDiagnostics){
        $metaState='initialization_failed'
        try{
            . (Join-Path $PSScriptRoot 'diagnostics/C545D-MetadataIntegrationV04.ps1')
            . (Join-Path $PSScriptRoot 'diagnostics/C545D-MetadataClassifierV04.ps1')
            $metaState=Initialize-C545DMetadataV04 $OutputDirectory $MetadataProbeSha256
        }catch{}
        Write-C545DNamerLog ('Metadata v0.4 initialization: '+$metaState)
    }
    $events=New-Object C545DFileEvents $OutputDirectory
    [System.IO.File]::WriteAllText($ReadyFile, (Get-Date -Format 'o'))
    Write-C545DNamerLog ('EVENT WATCHER READY; folder=' + $OutputDirectory + '; ownerPID=' + $OwnerProcessId)
    while ($true) {
        # FileSystemWatcher events are queued, not polled from the directory.
        [string]$path=''
        while ($events.TryTake([ref]$path)) {
            $name=[System.IO.Path]::GetFileName($path)
            if (Test-C545DTempName $name) {
                if (-not $pending.ContainsKey($path)) {
                    $pending[$path]=Get-Date
                    Write-C545DNamerLog ('Event: new temporary MP4 ' + $name)
                }
            }
        }
        $errors=$events.TakeErrors()
        if ($errors -gt 0) {
            # Do NOT scan directory automatically, as requested. Files are
            # preserved as-is and can be recovered with manual tool.
            Write-C545DNamerLog ('WARNING: FileSystemWatcher lost events (' + $errors + '). Run 手動_未改名MP4整理.cmd if needed.')
        }
        $now=Get-Date
        foreach ($key in @($pending.Keys)) {
            if ($lastAttempt.ContainsKey($key) -and (($now - $lastAttempt[$key]).TotalSeconds -lt 5)) { continue }
            $lastAttempt[$key]=$now
            $state=Invoke-C545DRenameOne -FullPath $key -OutputDirectory $OutputDirectory
            if ($state -eq 'done' -or $state -eq 'skip') {
                [void]$pending.Remove($key)
                [void]$lastAttempt.Remove($key)
            } elseif (($now - $pending[$key]).TotalHours -ge 24) {
                Write-C545DNamerLog ('WARNING: rename deferred for 24h; preserved temporary file: ' + [IO.Path]::GetFileName($key))
                [void]$pending.Remove($key)
                [void]$lastAttempt.Remove($key)
            }
        }
        $loopCount++
        $ownerAlive=$true
        if (($loopCount % 10) -eq 0) {
            try { $ownerAlive=$null -ne (Get-Process -Id $OwnerProcessId -ErrorAction SilentlyContinue) }
            catch { $ownerAlive=$false }
        }
        $shutdown=(Test-Path -LiteralPath $StopFile) -or (-not $ownerAlive)
        if ($shutdown) {
            if ($null -eq $closingSince) { $closingSince=Get-Date; Write-C545DNamerLog 'Watcher received shutdown request; draining detected pending files.' }
            # Do not lose the final MP4: keep waiting for finalized pending files.
            if ($pending.Count -eq 0 -and (($now-$closingSince).TotalSeconds -ge 3)) { break }
            if (($now-$closingSince).TotalSeconds -ge 180) {
                Write-C545DNamerLog ('Watcher shutdown grace expired, pending=' + $pending.Count + '; temporary files preserved.')
                break
            }
        }
        [void]$events.Wait(1000)
    }
}
catch {
    Write-C545DNamerLog ('ERROR event watcher: ' + $_.Exception.Message)
    exit 1
}
finally {
    if ($events) { $events.Dispose() }
    if($EnableMetadataDiagnostics -and $script:C545DMetadataWriterV04){
        try{[void](Stop-C545DMetadataV04)}catch{}
    }
    try { Remove-Item -LiteralPath $ReadyFile -Force -ErrorAction SilentlyContinue } catch { }
    try { Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue } catch { }
    Write-C545DNamerLog 'Event watcher exited.'
}
