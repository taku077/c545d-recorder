# CI-only artificial blocked writer; no recorder or camera needed.
$ErrorActionPreference='Stop'
Add-Type -Path @((Join-Path $PSScriptRoot 'C545DMetadataJournalPrototype.cs'),(Join-Path $PSScriptRoot 'C545DMetadataWriterPrototype.cs'))
$root=Join-Path $env:RUNNER_TEMP ('c545d-writer-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
function Eq($a,$b,[string]$tag){if($a -cne $b){throw ('WRITER_ASSERT_'+$tag+' actual='+$a+' expected='+$b)}}
$now=[datetime]::new(2026,11,24,12,0,0,[DateTimeKind]::Utc)
function New-Row([datetime]$t){
    $r=New-Object 'C545DMetadataJournalPrototype+Row'
    $r.Utc=$t;$r.Status='profile_match_metadata_only';$r.DurationMs=3600000
    $r.VideoTracks=1;$r.AudioTracks=1;$r.Width=2560;$r.Height=720
    $r.FpsNum=15;$r.FpsDen=1;$r.SampleRate=48000;$r.Channels=1;$r.H264=1;$r.Aac=1
    return $r
}
$gate=New-Object Threading.ManualResetEventSlim($false)
$writer=New-Object C545DMetadataWriterPrototype($root,$gate)
try{
    $row=New-Row $now
    Eq ($writer.TryPublish($row)) 'queued_not_saved' 'FIRST'
    # Worker consumes first row but cannot touch disk.
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while($writer.Pending -ne 0 -and $clock.ElapsedMilliseconds -lt 3000){Start-Sleep -Milliseconds 10}
    Eq $writer.Pending 0 'WORKER_STALLED'
    $row.Status='rtsp://synthetic:secret@192.0.2.1/stream6'
    $timer=[Diagnostics.Stopwatch]::StartNew()
    for($i=1;$i -le 16;$i++){Eq ($writer.TryPublish((New-Row $now.AddSeconds($i)))) 'queued_not_saved' 'QUEUE'}
    for($i=0;$i -lt 100;$i++){Eq ($writer.TryPublish((New-Row $now.AddSeconds(30+$i)))) 'queue_full' 'FULL'}
    $elapsed=$timer.ElapsedMilliseconds
    if($elapsed -gt 2000){throw 'PUBLICATION_STALL'}
    Eq $writer.Accepted 17 'ACCEPTED'
    Eq $writer.Rejected 100 'REJECTED'
    Eq $writer.Pending 16 'CAPACITY'
    Eq $writer.Saved 0 'NOT_DURABLE'
    Eq @(Get-ChildItem -LiteralPath $root -File).Count 0 'NO_DISK'
    $stopTimer=[Diagnostics.Stopwatch]::StartNew()
    Eq ($writer.Stop(50)) $false 'BOUNDED_STOP'
    $stopMs=$stopTimer.ElapsedMilliseconds
    if($stopMs -gt 1500){throw 'STOP_STALL'}
    Eq ($writer.TryPublish((New-Row $now))) 'stopping' 'AFTER_STOP'
    $gate.Set()
    Eq ($writer.Stop(5000)) $true 'DRAIN'
    Eq $writer.Saved 17 'SAVED'
    Eq $writer.Failed 0 'NO_FAILED'
    Eq $writer.Rejected 101 'REJECTED_FINAL'
    $s=[C545DMetadataJournalPrototype]::ReadWindow($root,$now.Date,$now.Date.AddDays(1))
    Eq $s.Rows.Count 17 'PERSISTED'
    Eq $s.Status 'coverage_unverified' 'NOT_COVERAGE_PROOF'
    foreach($r in $s.Rows){Eq $r.Status 'profile_match_metadata_only' 'IMMUTABLE_COPY'}
    # Real journal contention: worker counts failure without retry or data change.
    $slot=@(Get-ChildItem $root -File)[0].FullName
    $hash=(Get-FileHash $slot).Hash
    $lock=[IO.File]::Open($slot,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{
        $other=New-Object C545DMetadataWriterPrototype($root,$null)
        Eq ($other.TryPublish((New-Row $now.AddMinutes(1)))) 'queued_not_saved' 'LOCK_QUEUED'
        Eq ($other.Stop(5000)) $true 'LOCK_DRAIN'
        Eq $other.Failed 1 'LOCK_FAILED'
        Eq $other.Saved 0 'LOCK_NOT_SAVED'
    }finally{$lock.Dispose()}
    Eq (Get-FileHash $slot).Hash $hash 'LOCK_UNCHANGED'
    # Real journal recovery runs on writer, not on caller.
    [IO.File]::AppendAllText($slot,'torn-fragment')
    $third=New-Object C545DMetadataWriterPrototype($root,$null)
    Eq ($third.TryPublish((New-Row $now.AddMinutes(2)))) 'queued_not_saved' 'RECOVERY_QUEUED'
    Eq ($third.Stop(5000)) $true 'RECOVERY_DRAIN'
    Eq $third.Saved 1 'RECOVERY_SAVED'
    Eq $third.Recovered 1 'RECOVERY_COUNT'
    $s=[C545DMetadataJournalPrototype]::ReadWindow($root,$now.Date,$now.Date.AddDays(1))
    Eq $s.Rows.Count 18 'RECOVERY_ROWS'
    Eq $s.RecoveredSlots 1 'RECOVERY_MARKER'
    Eq $s.Status 'partial_or_unavailable' 'RECOVERY_COVERAGE'
    Write-Host ('C545D_METADATA_WRITER_PASS,capacity=16,accepted=17,full_rejected=100,publication_batch_ms='+$elapsed+',stop_timeout_ms='+$stopMs+',drained=17,lock_failed=1,auto_recovered=1,immutable_copy=1,host_modified=0')
}finally{
    $gate.Set()
    [void]$writer.Stop(5000)
    $gate.Dispose()
    Remove-Item -LiteralPath $root -Recurse -Force
}
