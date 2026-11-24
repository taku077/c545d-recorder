# CI-only: compare frozen v0.3 baseline with actual v0.4 observer source.
param([Parameter(Mandatory=$true)][string]$BaselineObserver)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$root=Join-Path $env:RUNNER_TEMP ('metadata-zip-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
try{
    $observer=$BaselineObserver
    $candidateFile=Join-Path $repo 'diagnostics/C545D-WeeklyObserver.ps1'
    $journalSource=Join-Path $repo 'diagnostics/C545DMetadataJournalV04.cs'
    $writerSource=Join-Path $repo 'diagnostics/C545DMetadataWriterV04.cs'
    Add-Type -Path @($journalSource,$writerSource)
    $journal=Join-Path $root 'journal'
    $logs=Join-Path $root 'logs'
    $receiptRoot=Join-Path $root 'receipts'
    $metrics=Join-Path $root 'observer'
    foreach($dir in @($journal,$logs,$metrics,$receiptRoot)){New-Item -ItemType Directory -Path $dir | Out-Null}
    $now=[datetime]::UtcNow.AddMinutes(-10)
    # First session spans report boundary; counters must not be attributed to this week.
    $finished=[C545DWriterReceipts]::Start($receiptRoot,$now.AddDays(-8))
    if(-not [C545DWriterReceipts]::Finish($finished,$now,4,2,3,1,1)){throw 'WRITER_FIXTURE_FINAL'}
    $unfinished=[C545DWriterReceipts]::Start($receiptRoot,$now.AddMinutes(1))
    if($null -eq $unfinished){throw 'WRITER_FIXTURE_START'}
    $corrupt=[C545DWriterReceipts]::Start($receiptRoot,$now.AddMinutes(2))
    if($null -eq $corrupt){throw 'WRITER_FIXTURE_CORRUPT'}
    [IO.File]::AppendAllText((Join-Path $receiptRoot 'writer_002.dat'),'PRIVATE_SECRET_923')
    function Add-Fixture([string]$status,[datetime]$t){
        $row=New-Object 'C545DMetadataJournalV04+Row'
        $row.Utc=$t;$row.Status=$status
        $row.DurationMs=3600123;$row.VideoTracks=1;$row.AudioTracks=1;$row.Width=2560;$row.Height=720
        $row.FpsNum=15;$row.FpsDen=1;$row.SampleRate=48000;$row.Channels=1;$row.H264=1;$row.Aac=1
        if($status -eq 'profile_mismatch'){$row.AudioTracks=0;$row.Aac=-1}
        if($status -eq 'probe_unavailable'){
            $row.DurationMs=-1;$row.VideoTracks=-1;$row.AudioTracks=-1;$row.Width=-1;$row.Height=-1
            $row.FpsNum=-1;$row.FpsDen=-1;$row.SampleRate=-1;$row.Channels=-1;$row.H264=-1;$row.Aac=-1
        }
        if([C545DMetadataJournalV04]::Append($journal,$row) -ne 'saved'){throw 'FIXTURE_SAVE_FAILED'}
    }
    Add-Fixture 'profile_match_metadata_only' $now
    Add-Fixture 'profile_mismatch' $now.AddSeconds(1)
    Add-Fixture 'probe_unavailable' $now.AddSeconds(2)
    $local=$now.ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss',[Globalization.CultureInfo]::InvariantCulture)
    $log=Join-Path $logs 'Filename_Rename.log'
    1..4 | ForEach-Object {Add-Content -LiteralPath $log -Value ($local+'  Renamed (closed): PRIVATE_SECRET_923 -> C:\private\camera.mp4')}
    function Run-Export([string]$script,[string]$tag,[bool]$new){
        $argsList=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$script,
          '-RootDirectory',$metrics,'-RecorderLogDirectory',$logs,'-ExportNow')
        if($new){$argsList+=@('-MetadataJournalRoot',$journal,'-WriterReceiptRoot',$receiptRoot)}
        $before=@(Get-ChildItem (Join-Path $metrics 'reports') -Filter '*.zip' -File -ErrorAction SilentlyContinue | ForEach-Object FullName)
        & powershell.exe @argsList | Out-Null
        if($LASTEXITCODE -ne 0){throw ('OBSERVER_CHILD_FAILED_'+$tag)}
        $newZip=@(Get-ChildItem (Join-Path $metrics 'reports') -Filter '*.zip' -File | Where-Object {$before -notcontains $_.FullName})
        if($newZip.Count -ne 1){throw 'ZIP_COUNT'}
        $out=Join-Path $root $tag
        Expand-Archive -LiteralPath $newZip[0].FullName -DestinationPath $out
        return $out
    }
    function Assert-Eq($a,$b,[string]$tag){if($a -cne $b){throw ('METADATA_ZIP_ASSERT_'+$tag+' actual='+$a+' expected='+$b)}}
    $old=Run-Export $observer 'old' $false
    $new=Run-Export $candidateFile 'new' $true
    $oldManifest=Get-Content (Join-Path $old 'manifest.json') -Raw | ConvertFrom-Json
    $m=Get-Content (Join-Path $new 'manifest.json') -Raw | ConvertFrom-Json
    Assert-Eq $oldManifest.diagnostics_version '0.3.0' 'BASELINE_VERSION'
    Assert-Eq $m.diagnostics_version '0.4.0' 'CANDIDATE_VERSION'
    Assert-Eq $m.schema_version $oldManifest.schema_version 'SCHEMA_COMPATIBILITY'
    Assert-Eq @(Get-ChildItem $old -File).Count 5 'OLD_FILES'
    Assert-Eq @(Get-ChildItem $new -File).Count 7 'NEW_FILES'
    foreach($file in @('process_metrics.csv','recording_events.csv','recorder_sessions.csv')){
        Assert-Eq (Get-FileHash (Join-Path $old $file)).Hash (Get-FileHash (Join-Path $new $file)).Hash 'OLD_CSV_PARITY'
    }
    Assert-Eq $m.writer_completed_runs 1 'WRITER_COMPLETED'
    Assert-Eq $m.writer_unfinished_or_active_runs 1 'WRITER_UNFINISHED'
    Assert-Eq $m.writer_invalid_slots 1 'WRITER_CORRUPT'
    Assert-Eq $m.writer_event_coverage 'not_proven' 'WRITER_COVERAGE'
    $wrows=@(Import-Csv (Join-Path $new 'diagnostic_writer_runs.csv'))
    Assert-Eq $wrows.Count 2 'WRITER_ROWS'
    $done=@($wrows|Where-Object state -eq 'final_counters_saved')
    $unknown=@($wrows|Where-Object state -eq 'unfinished_or_active')
    Assert-Eq $done[0].accepted '4' 'WRITER_ACCEPTED'
    Assert-Eq $done[0].rejected '2' 'WRITER_REJECTED'
    Assert-Eq $done[0].failed '1' 'WRITER_FAILED'
    Assert-Eq $done[0].counter_scope 'whole_run_not_report_window' 'WRITER_SCOPE'
    Assert-Eq $unknown[0].accepted 'unknown' 'WRITER_UNKNOWN'
    Assert-Eq $unknown[0].saved 'unknown' 'WRITER_UNKNOWN_SAVED'
    Assert-Eq $m.metadata_event_count 3 'EVENTS'
    Assert-Eq $m.metadata_profile_match_count 1 'MATCH'
    Assert-Eq $m.metadata_profile_mismatch_count 1 'MISMATCH'
    Assert-Eq $m.metadata_unknown_count 1 'UNKNOWN'
    Assert-Eq $m.metadata_rename_count_difference 1 'COUNT_DIFFERENCE'
    Assert-Eq $m.metadata_event_coverage 'not_proven' 'COVERAGE'
    Assert-Eq $m.av_sync 'not_collected' 'SYNC_UNKNOWN'
    Assert-Eq $m.full_media_decode 'not_collected' 'DECODE_UNKNOWN'
    $csv=@(Import-Csv (Join-Path $new 'mp4_metadata.csv'))
    Assert-Eq $csv.Count 3 'CSV_ROWS'
    foreach($f in @(Get-ChildItem $new -File)){
        if([IO.File]::ReadAllText($f.FullName) -match 'PRIVATE_SECRET|rtsp://|C:\\private\\'){throw 'ZIP_SECRET_LEAK'}
    }
    Add-Fixture 'profile_match_metadata_only' $now.AddSeconds(3)
    $equal=Run-Export $candidateFile 'equal' $true
    $m=Get-Content (Join-Path $equal 'manifest.json') -Raw|ConvertFrom-Json
    Assert-Eq $m.metadata_rename_count_difference 0 'EQUAL_COUNT'
    Assert-Eq $m.metadata_event_coverage 'not_proven' 'EQUAL_NOT_PROOF'
    $slot=@(Get-ChildItem $journal -File)[0].FullName
    [IO.File]::AppendAllText($slot,'PRIVATE_SECRET_923')
    $bad=Run-Export $candidateFile 'bad' $true
    $m=Get-Content (Join-Path $bad 'manifest.json') -Raw|ConvertFrom-Json
    Assert-Eq $m.metadata_event_count 0 'CORRUPT_ROWS'
    Assert-Eq $m.metadata_journal_invalid_slots 1 'CORRUPT_SLOT'
    Assert-Eq $m.metadata_rename_count_difference 'not_classified' 'CORRUPT_DIFFERENCE'
    Assert-Eq $m.renamed_closed_mp4_count 4 'LEGACY_REPORT_RETAINS'
    $recovery=[C545DMetadataJournalV04]::RecoverTornTail($journal,$now)
    Assert-Eq $recovery 'recovered_loss_possible' 'RECOVERY_SUCCESS'
    $recovered=Run-Export $candidateFile 'recovered' $true
    $m=Get-Content (Join-Path $recovered 'manifest.json') -Raw|ConvertFrom-Json
    Assert-Eq $m.metadata_event_count 4 'RECOVERED_ROWS'
    Assert-Eq $m.metadata_journal_recovered_slots 1 'RECOVERED_MARKER'
    Assert-Eq $m.metadata_journal_source_status 'partial_or_unavailable' 'RECOVERED_PARTIAL'
    Assert-Eq $m.metadata_rename_count_difference 'not_classified' 'RECOVERY_COUNT_UNKNOWN'
    Assert-Eq $m.metadata_event_coverage 'not_proven' 'RECOVERY_NOT_PROOF'
    foreach($file in @(Get-ChildItem $recovered -File)){
        if([IO.File]::ReadAllText($file.FullName) -match 'PRIVATE_SECRET|rtsp://|C:\\private\\'){throw 'RECOVERED_ZIP_SECRET_LEAK'}
    }
    Write-Host 'C545D_METADATA_ZIP_RECOVERY_PASS,rows=4,recovered_slots=1,coverage_not_proven=1,count_unclassified=1,privacy=1'
    Remove-Item -LiteralPath $journal -Recurse -Force
    Remove-Item -LiteralPath $receiptRoot -Recurse -Force
    $missing=Run-Export $candidateFile 'missing' $true
    $m=Get-Content (Join-Path $missing 'manifest.json') -Raw|ConvertFrom-Json
    Assert-Eq $m.metadata_journal_source_status 'not_found' 'MISSING'
    Assert-Eq $m.metadata_event_count 0 'MISSING_ROWS'
    Assert-Eq $m.metadata_event_coverage 'not_proven' 'MISSING_NOT_HEALTH'
    Assert-Eq $m.metadata_rename_count_difference 'not_classified' 'MISSING_DIFF'
    Assert-Eq $m.writer_receipt_source_status 'not_found' 'WRITER_MISSING'
    Assert-Eq $m.writer_event_coverage 'not_proven' 'WRITER_MISSING_UNKNOWN'
    Assert-Eq @(Import-Csv (Join-Path $missing 'diagnostic_writer_runs.csv')).Count 0 'WRITER_EMPTY_CSV'
    # Missing compiled reader sources must not prevent old report export.
    $noModules=Join-Path $root 'no-modules'
    New-Item -ItemType Directory -Path $noModules|Out-Null
    $noReader=Join-Path $noModules 'C545D-WeeklyObserver.ps1'
    Copy-Item -LiteralPath $candidateFile -Destination $noReader
    foreach($dir in @($journal,$receiptRoot)){New-Item -ItemType Directory -Path $dir|Out-Null}
    $unavailable=Run-Export $noReader 'reader-unavailable' $true
    $m=Get-Content (Join-Path $unavailable 'manifest.json') -Raw|ConvertFrom-Json
    Assert-Eq $m.metadata_journal_source_status 'reader_unavailable' 'READER_UNAVAILABLE'
    Assert-Eq $m.writer_receipt_source_status 'reader_unavailable' 'WRITER_READER_UNAVAILABLE'
    Assert-Eq $m.renamed_closed_mp4_count 4 'READER_UNAVAILABLE_LEGACY'
    Assert-Eq @(Get-ChildItem $unavailable -File).Count 7 'READER_UNAVAILABLE_FILES'
    Write-Host 'C545D_V04_ACTUAL_OBSERVER_PASS,actual_source=1,reader_missing_fallback=1,legacy_report_retained=1'
    Write-Host 'C545D_WRITER_ZIP_PASS,completed=1,unfinished_unknown=1,corrupt_excluded=1,missing_unknown=1,whole_run_only=1,privacy=1'
    Write-Host 'C545D_METADATA_ZIP_INTEGRATION_PASS,baseline_files=5,candidate_files=7,legacy_csv_parity=3,profile_match=1,profile_mismatch=1,unknown=1,count_gap=1,equal_not_proof=1,corrupt_excluded=1,missing_unknown=1,privacy=1,host_modified=0'
}finally{Remove-Item -LiteralPath $root -Recurse -Force}
