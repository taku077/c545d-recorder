# CI-only: durable start/final receipts, never infer missing counters as zero.
$ErrorActionPreference='Stop'
Add-Type -Path @((Join-Path $PSScriptRoot 'C545DMetadataJournalPrototype.cs'),(Join-Path $PSScriptRoot 'C545DMetadataWriterPrototype.cs'))
$root=Join-Path $env:RUNNER_TEMP ('c545d-receipt-'+[guid]::NewGuid().ToString('N'))
$journal=Join-Path $root 'journal';$receipt=Join-Path $root 'receipt'
foreach($d in @($root,$journal,$receipt)){New-Item -ItemType Directory -Path $d|Out-Null}
function Eq($a,$b,[string]$tag){if($a -cne $b){throw ('RECEIPT_ASSERT_'+$tag+' actual='+$a+' expected='+$b)}}
$now=[datetime]::UtcNow
function New-Row {
    $r=New-Object 'C545DMetadataJournalPrototype+Row'
    $r.Utc=[datetime]::UtcNow;$r.Status='profile_match_metadata_only';$r.DurationMs=3600000
    $r.VideoTracks=1;$r.AudioTracks=1;$r.Width=2560;$r.Height=720
    $r.FpsNum=15;$r.FpsDen=1;$r.SampleRate=48000;$r.Channels=1;$r.H264=1;$r.Aac=1
    return $r
}
$gate=New-Object Threading.ManualResetEventSlim($false)
$writer=New-Object C545DMetadataWriterPrototype($journal,$gate,$receipt)
try{
    Eq ($writer.TryPublish((New-Row))) 'queued_not_saved' 'QUEUED'
    $clock=[Diagnostics.Stopwatch]::StartNew()
    while($writer.ReceiptStatus -eq 'not_enabled' -and $clock.ElapsedMilliseconds -lt 3000){Start-Sleep -Milliseconds 10}
    Eq $writer.ReceiptStatus 'started_not_final' 'START_DURABLE'
    $s=[C545DWriterReceipts]::ReadWindow($receipt,$now.AddHours(-1),$now.AddHours(1))
    Eq $s.UnfinishedRuns 1 'UNFINISHED'
    Eq $s.Rows[0].Accepted -1 'ACCEPTED_UNKNOWN'
    Eq $s.Rows[0].Saved -1 'SAVED_UNKNOWN'
    Eq $s.Status 'partial_or_unavailable' 'PARTIAL'
    Eq ($writer.Stop(50)) $false 'STOP_UNCONFIRMED'
    $gate.Set()
    Eq ($writer.Stop(5000)) $true 'DRAINED'
    Eq $writer.ReceiptStatus 'final_saved' 'FINAL_DURABLE'
    $s=[C545DWriterReceipts]::ReadWindow($receipt,$now.AddHours(-1),$now.AddHours(1))
    Eq $s.CompletedRuns 1 'COMPLETED'
    Eq $s.Rows[0].Accepted 1 'ACCEPTED'
    Eq $s.Rows[0].Saved 1 'SAVED'
    Eq $s.Rows[0].Failed 0 'FAILED'
    Eq $s.Status 'coverage_unverified' 'NOT_COMPLETE_COVERAGE'
    # A separate durable start without final simulates a process interrupted before finalization.
    $abandoned=[C545DWriterReceipts]::Start($receipt,$now.AddMinutes(-1))
    if($null -eq $abandoned){throw 'ABANDONED_START_MISSING'}
    Eq ([C545DWriterReceipts]::Finish($abandoned,$now,3,0,2,0,0)) $false 'INCONSISTENT_COUNTERS'
    $s=[C545DWriterReceipts]::ReadWindow($receipt,$now.AddHours(-1),$now.AddHours(1))
    Eq $s.UnfinishedRuns 1 'ABANDONED_UNKNOWN'
    # Retain valid completed receipt while rejecting a torn final record.
    $slot=Join-Path $receipt 'writer_001.dat'
    [IO.File]::AppendAllText($slot,'END|PRIVATE_SECRET')
    $s=[C545DWriterReceipts]::ReadWindow($receipt,$now.AddHours(-1),$now.AddHours(1))
    Eq $s.InvalidSlots 1 'TORN_FINAL'
    Eq $s.CompletedRuns 1 'VALID_RETAINED'
    Eq $s.Rows.Count 1 'TORN_NOT_EXPORTED'
    $badHash=(Get-FileHash -LiteralPath $slot).Hash
    # Old, finished receipt can be reused, but not corrupt/unfinished data.
    $old=[C545DWriterReceipts]::Start($receipt,$now.AddDays(-40))
    Eq ([C545DWriterReceipts]::Finish($old,$now.AddDays(-39),2,3,1,1,1)) $true 'OLD_FINAL'
    $reuse=[C545DWriterReceipts]::Start($receipt,$now)
    if($null -eq $reuse){throw 'REUSE_FAILED'}
    Eq @(Get-ChildItem -LiteralPath $receipt -File).Count 3 'OLD_SLOT_REUSED'
    Eq (Get-FileHash -LiteralPath $slot).Hash $badHash 'CORRUPT_PRESERVED'
    Eq ([C545DWriterReceipts]::Finish($reuse,$now.AddSeconds(1),2,3,1,1,1)) $true 'COUNTERS_FINAL'
    $s=[C545DWriterReceipts]::ReadWindow($receipt,$now.AddHours(-1),$now.AddHours(1))
    Eq $s.CompletedRuns 2 'TWO_FINAL'
    Eq @($s.Rows | Where-Object Rejected -eq 3).Count 1 'REJECTED_REPORTED'
    Eq @($s.Rows | Where-Object Failed -eq 1).Count 1 'FAILED_REPORTED'
    # Saturation: fixed slots, no eviction of recent or incomplete data.
    for($i=3;$i -lt 128;$i++){
        if($null -eq [C545DWriterReceipts]::Start($receipt,$now)){throw 'RECEIPT_FILL_FAILED'}
    }
    Eq @(Get-ChildItem -LiteralPath $receipt -File).Count 128 'FIXED_CAP'
    Eq ($null -eq [C545DWriterReceipts]::Start($receipt,$now)) $true 'FULL_REFUSED'
    $total=0L
    foreach($f in @(Get-ChildItem -LiteralPath $receipt -File)){$total+=$f.Length;if($f.Length -gt 1024){throw 'RECEIPT_FILE_CAP'}}
    if($total -gt 131072){throw 'RECEIPT_TOTAL_CAP'}
    Write-Host ('C545D_WRITER_RECEIPTS_PASS,unfinished_unknown=1,final_counts=1,inconsistent_denied=1,corrupt_excluded=1,expired_reused=1,corrupt_preserved=1,slots=128,cap_bytes=131072,actual_bytes='+$total+',saturation_refused=1,host_modified=0')
}finally{
    $gate.Set();[void]$writer.Stop(5000);$gate.Dispose()
    Remove-Item -LiteralPath $root -Recurse -Force
}
