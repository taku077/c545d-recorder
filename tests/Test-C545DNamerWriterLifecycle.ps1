# CI-only actual event watcher lifecycle comparison. No camera, no recorder process.
param([Parameter(Mandatory=$true)][string]$FixtureDirectory,
      [Parameter(Mandatory=$true)][string]$ProbeExe)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows'){throw 'CI_ONLY'}
$repo=Split-Path -Parent $PSScriptRoot
$root=Join-Path $FixtureDirectory 'writer-lifecycle'
New-Item -ItemType Directory -Path $root | Out-Null
$originalNamer=[IO.File]::ReadAllText((Join-Path $repo 'SegmentNamer.ps1'))
$originalWorker=[IO.File]::ReadAllText((Join-Path $repo 'SegmentNamerWorker.ps1'))
$integration=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Test-C545DNamerSingleProbe.ps1'))
function Replace-Once([string]$s,[string]$a,[string]$b){
    if(([regex]::Matches($s,[regex]::Escape($a))).Count -ne 1){throw 'LIFECYCLE_ANCHOR_DRIFT'}
    $s.Replace($a,$b)
}
function Read-HereString([string]$name){
    $m=[regex]::Match($integration,('(?ms)^\$'+$name+'=@''\r?\n(.*?)\r?\n''@'))
    if(-not $m.Success){throw 'LIFECYCLE_SHARED_SOURCE_MISSING'}
    $m.Groups[1].Value
}
$nl=[Environment]::NewLine
$namer=Replace-Once $originalNamer '        $duration=Get-C545DDuration $file.FullName' (Read-HereString 'new')
$namer=Replace-Once $namer "        return 'done'" (Read-HereString 'replacement')
$worker=Replace-Once $originalWorker '$events=$null' (@'
$script:probeCalls=0
$script:publishFailures=0
$script:C545DProbePath=$env:C545D_CI_DIRECT_PROBE
$script:C545DProbeSearched=$true
. (Join-Path $PSScriptRoot 'C545D-ClosedMetadataPrototype.ps1')
Add-Type -Path (Join-Path $PSScriptRoot 'C545DClosedProbePrototype.cs')
Add-Type -Path @((Join-Path $PSScriptRoot 'C545DMetadataJournalPrototype.cs'),(Join-Path $PSScriptRoot 'C545DMetadataWriterPrototype.cs'))
$script:diagnosticGate=New-Object Threading.ManualResetEventSlim($env:C545D_CI_STALL -ne '1')
$script:diagnosticWriter=New-Object C545DMetadataWriterPrototype($env:C545D_CI_JOURNAL,$script:diagnosticGate)
function Publish-C545DTestEvidence($row){
    $entry=New-Object 'C545DMetadataJournalPrototype+Row'
    $entry.Utc=[datetime]::UtcNow;$entry.Status=$row.metadata_status
    $entry.DurationMs=$row.duration_ms
    $entry.VideoTracks=$row.video_tracks;$entry.AudioTracks=$row.audio_tracks
    $entry.Width=$row.width;$entry.Height=$row.height
    $entry.FpsNum=$row.fps_num;$entry.FpsDen=$row.fps_den
    $entry.SampleRate=$row.sample_rate;$entry.Channels=$row.channels
    $entry.H264=$row.video_h264;$entry.Aac=$row.audio_aac
    if($script:diagnosticWriter.TryPublish($entry) -ne 'queued_not_saved'){throw 'DIAGNOSTIC_QUEUE_REJECTED'}
}
$events=$null
'@)
$worker=Replace-Once $worker '    if ($events) { $events.Dispose() }' (@'
    if ($events) { $events.Dispose() }
    # Existing watcher drain is over. Only now stop accepting metadata.
    $clock=[Diagnostics.Stopwatch]::StartNew()
    $drained=$script:diagnosticWriter.Stop(250)
    $ms=$clock.ElapsedMilliseconds
    Write-Host ('C545D_CI_WRITER_STOP,drained='+[int]$drained+',accepted='+$script:diagnosticWriter.Accepted+
        ',saved='+$script:diagnosticWriter.Saved+',rejected='+$script:diagnosticWriter.Rejected+
        ',failed='+$script:diagnosticWriter.Failed+',publish_failures='+$script:publishFailures+
        ',probes='+$script:probeCalls+',elapsed_ms='+$ms)
    if($drained){$script:diagnosticGate.Dispose()}
'@)
$stage=Join-Path $root 'source'
New-Item -ItemType Directory -Path $stage|Out-Null
$utf8=New-Object Text.UTF8Encoding($true)
[IO.File]::WriteAllText((Join-Path $stage 'SegmentNamer.ps1'),$namer,$utf8)
[IO.File]::WriteAllText((Join-Path $stage 'SegmentNamerWorker.ps1'),$worker,$utf8)
foreach($name in @('C545D-ClosedMetadataPrototype.ps1','C545DClosedProbePrototype.cs','C545DMetadataJournalPrototype.cs','C545DMetadataWriterPrototype.cs')){
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $stage
}
$sample=Join-Path $FixtureDirectory '2026-11-24_12-00_12-01.mp4'
$sampleHash=(Get-FileHash -LiteralPath $sample).Hash
function Wait-Until([scriptblock]$predicate,[int]$milliseconds,[string]$tag){
    $clock=[Diagnostics.Stopwatch]::StartNew()
    do {
        if(& $predicate){return}
        Start-Sleep -Milliseconds 100
    }while($clock.ElapsedMilliseconds -lt $milliseconds)
    throw ('LIFECYCLE_TIMEOUT_'+$tag)
}
function Assert-Eq($a,$b,[string]$tag){
    if($a -cne $b){throw ('LIFECYCLE_ASSERT_'+$tag+' actual='+$a+' expected='+$b)}
}
function Run-Arm([bool]$stall){
    $arm=Join-Path $root ('arm_'+[int]$stall)
    $folder=Join-Path $arm 'output';$journal=Join-Path $arm 'journal'
    $private=Join-Path $arm 'local'
    foreach($d in @($folder,$journal,$private)){New-Item -ItemType Directory -Path $d -Force|Out-Null}
    $ready=Join-Path $arm 'ready';$stop=Join-Path $arm 'stop'
    $stdout=Join-Path $arm 'stdout';$stderr=Join-Path $arm 'stderr'
    $oldLocal=$env:LOCALAPPDATA
    $env:LOCALAPPDATA=$private
    $env:C545D_CI_STALL=[string][int]$stall
    $env:C545D_CI_JOURNAL=$journal
    $env:C545D_CI_DIRECT_PROBE=$ProbeExe
    $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $scriptPath=Join-Path $stage 'SegmentNamerWorker.ps1'
    $argsLine='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$scriptPath+
        '" -OutputDirectory "'+$folder+'" -OwnerProcessId '+$PID+' -ReadyFile "'+$ready+'" -StopFile "'+$stop+'"'
    $proc=$null;$locked=$null
    try{
        # Own the actual process handle and drain both pipes concurrently.
        $psi=New-Object Diagnostics.ProcessStartInfo
        $psi.FileName=$ps;$psi.Arguments=$argsLine
        $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
        $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
        $proc=[Diagnostics.Process]::Start($psi)
        $null=$proc.Handle
        $outTask=$proc.StandardOutput.ReadToEndAsync()
        $errTask=$proc.StandardError.ReadToEndAsync()
        Wait-Until { (Test-Path -LiteralPath $ready) -or $proc.HasExited } 20000 'READY'
        if($proc.HasExited){
            $e=if($errTask.Wait(1000)){$errTask.Result}else{''}
            # Only report a bounded line/type diagnostic, not private paths.
            Write-Host ('LIFECYCLE_EARLY_EXIT,stderr_chars='+$e.Length)
            throw 'LIFECYCLE_WORKER_EARLY_EXIT'
        }
        $first=Join-Path $folder 'C545D_PENDING_20261124_120000_12345678_00001.mp4'
        Copy-Item -LiteralPath $sample -Destination $first
        Wait-Until { -not(Test-Path -LiteralPath $first) } 15000 'FIRST_RENAME'
        # A final segment is still locked when shutdown is requested.
        $lastName='C545D_PENDING_20261124_120000_12345678_00002.mp4'
        $last=Join-Path $folder $lastName
        $locked=[IO.File]::Open($last,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $input=[IO.File]::OpenRead($sample)
        try{$input.CopyTo($locked);$locked.Flush()}finally{$input.Dispose()}
        $log=Join-Path $private 'C545D_GStreamer\Logs\Filename_Rename.log'
        Wait-Until {
            try{(Get-Content -LiteralPath $log -Raw -ErrorAction Stop).Contains('Event: new temporary MP4 '+$lastName)}catch{$false}
        } 12000 'FINAL_EVENT'
        [IO.File]::WriteAllText($stop,'CI_SYNTHETIC_STOP')
        Wait-Until {
            try{(Get-Content -LiteralPath $log -Raw -ErrorAction Stop).Contains('Watcher received shutdown request')}catch{$false}
        } 10000 'SHUTDOWN_SEEN'
        Assert-Eq (Test-Path -LiteralPath $last) $true 'LOCKED_FINAL_PRESERVED'
        Assert-Eq $proc.HasExited $false 'WATCHER_ALIVE'
        $locked.Dispose();$locked=$null
        if(-not $proc.WaitForExit(20000)){throw 'LIFECYCLE_STOP_TIMEOUT'}
        $proc.Refresh()
        Assert-Eq $proc.ExitCode 0 'EXIT_CODE'
        if(-not $outTask.Wait(1000) -or -not $errTask.Wait(1000)){throw 'LIFECYCLE_PIPE_DRAIN_TIMEOUT'}
        [IO.File]::WriteAllText($stdout,$outTask.Result)
        [IO.File]::WriteAllText($stderr,$errTask.Result)
        Assert-Eq (Test-Path -LiteralPath $last) $false 'FINAL_RENAMED'
        Assert-Eq (Test-Path -LiteralPath $ready) $false 'READY_REMOVED'
        Assert-Eq (Test-Path -LiteralPath $stop) $false 'STOP_REMOVED'
        $files=@(Get-ChildItem -LiteralPath $folder -Filter '*.mp4' -File)
        Assert-Eq $files.Count 2 'FILE_COUNT'
        foreach($file in $files){Assert-Eq (Get-FileHash -LiteralPath $file.FullName).Hash $sampleHash 'MEDIA_HASH'}
        $line=@(Get-Content -LiteralPath $stdout | Where-Object {$_ -cmatch '^C545D_CI_WRITER_STOP,'})
        Assert-Eq $line.Count 1 'WRITER_STOP_MARKER'
        $expect=if($stall){'^C545D_CI_WRITER_STOP,drained=0,accepted=2,saved=0,rejected=0,failed=0,publish_failures=0,probes=2,elapsed_ms=\d+$'}else{'^C545D_CI_WRITER_STOP,drained=1,accepted=2,saved=2,rejected=0,failed=0,publish_failures=0,probes=2,elapsed_ms=\d+$'}
        if($line[0] -cnotmatch $expect){throw ('LIFECYCLE_BAD_COUNTERS_'+$line[0])}
        if([int]($line[0] -replace '^.*elapsed_ms=','') -gt 1500){throw 'LIFECYCLE_WRITER_STOP_TOO_LONG'}
        $jfiles=@(Get-ChildItem -LiteralPath $journal -File)
        if($stall){Assert-Eq $jfiles.Count 0 'STALL_NOT_SAVED'}
        else{
            # Verify complete persisted rows independently of child memory.
            Assert-Eq $jfiles.Count 1 'NORMAL_JOURNAL'
            Assert-Eq @(Get-Content -LiteralPath $jfiles[0].FullName).Count 3 'NORMAL_ROWS'
        }
        Write-Host ('C545D_NAMER_WRITER_ARM_PASS,stall='+[int]$stall+',final_renamed=1,media_hashes=2,'+($line[0] -replace '^C545D_CI_WRITER_STOP,',''))
    }finally{
        if($locked){$locked.Dispose()}
        if($proc){if(-not $proc.HasExited){$proc.Kill();[void]$proc.WaitForExit(3000)};$proc.Dispose()}
        $env:LOCALAPPDATA=$oldLocal
        Remove-Item Env:C545D_CI_STALL,Env:C545D_CI_JOURNAL,Env:C545D_CI_DIRECT_PROBE -ErrorAction SilentlyContinue
    }
}
Run-Arm $false
Run-Arm $true
if([IO.File]::ReadAllText((Join-Path $repo 'SegmentNamer.ps1')) -cne $originalNamer -or
   [IO.File]::ReadAllText((Join-Path $repo 'SegmentNamerWorker.ps1')) -cne $originalWorker){throw 'PRODUCTION_SOURCE_CHANGED'}
Write-Host 'C545D_NAMER_WRITER_LIFECYCLE_PASS,arms=2,actual_watcher=1,locked_final_after_stop=1,normal_saved=2,stalled_unconfirmed=2,source_unchanged=1,real_eos=0,real_camera=0,host_modified=0'
