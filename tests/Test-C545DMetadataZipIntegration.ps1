# CI-only: compare actual v0.3 observer ZIP to isolated v0.4 candidate.
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$root=Join-Path $env:RUNNER_TEMP ('metadata-zip-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
try{
    $observer=Join-Path $repo 'diagnostics/C545D-WeeklyObserver.ps1'
    $source=[IO.File]::ReadAllText($observer)
    $adapter=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'C545D-MetadataReportPrototype.ps1'))
    $journalSource=Join-Path $PSScriptRoot 'C545DMetadataJournalPrototype.cs'
    Add-Type -Path $journalSource
    $journal=Join-Path $root 'journal'
    $logs=Join-Path $root 'logs'
    $metrics=Join-Path $root 'observer'
    foreach($dir in @($journal,$logs,$metrics)){New-Item -ItemType Directory -Path $dir | Out-Null}
    $nl=[Environment]::NewLine
    function Replace-Once([string]$text,[string]$old,[string]$new){
        if(([regex]::Matches($text,[regex]::Escape($old))).Count -ne 1){throw 'OBSERVER_SOURCE_ANCHOR_DRIFT'}
        $text.Replace($old,$new)
    }
    $candidate=Replace-Once $source '  [switch]$SelfTest,' ('  [string]$MetadataJournalRoot,'+$nl+'  [string]$MetadataJournalSource,'+$nl+'  [switch]$SelfTest,')
    $candidate=Replace-Once $candidate '$version=''0.3.0''' '$version=''0.4.0'''
    $candidate=Replace-Once $candidate 'function New-SafeBundle(' ($adapter+$nl+'function New-SafeBundle(')
    $anchor=' $worker=Read-WorkerSessions $RecorderLogDirectory $begin $end'
    $candidate=Replace-Once $candidate $anchor ($anchor+$nl+' $metadata=Read-C545DMetadataReport $MetadataJournalRoot $MetadataJournalSource $begin $end $media')
    $manifestFields=@'
     metadata_journal_source_status=$metadata.status
     metadata_journal_invalid_slots=$metadata.invalid_slots
     metadata_journal_busy_slots=$metadata.busy_slots
     metadata_journal_saturated_slots=$metadata.saturated_slots
     metadata_journal_recovered_slots=$metadata.recovered_slots
     metadata_event_count=$metadata.rows.Count
     metadata_profile_match_count=$metadata.matches
     metadata_profile_mismatch_count=$metadata.mismatches
     metadata_unknown_count=$metadata.unknown
     metadata_rename_count_difference=$metadata.count_difference
     metadata_event_coverage='not_proven'
     metadata_time_semantics='publication_utc_not_exact_rename_time'
     camera_composition='not_collected';av_sync='not_collected';full_media_decode='not_collected'
'@
    $anchor='     recorder_version=''not_collected'''
    $candidate=Replace-Once $candidate $anchor ($anchor+$nl+$manifestFields)
    $anchor='   $metric=Join-Path $work ''process_metrics.csv'''
    $insert=@'
   $metadataFile=Join-Path $work 'mp4_metadata.csv'
   Write-C545DMetadataCsv $metadata $metadataFile
   $summary['metadata_event_count']=$metadata.rows.Count
   $summary['metadata_coverage']='not_proven'
'@
    $candidate=Replace-Once $candidate $anchor ($insert+$nl+$anchor)
    $candidate=Replace-Once $candidate 'Compress-Archive -LiteralPath @($metric,$mediaFile,$sessionFile,' 'Compress-Archive -LiteralPath @($metric,$mediaFile,$sessionFile,$metadataFile,'
    $candidateFile=Join-Path $root 'observer-v04-ci.ps1'
    [IO.File]::WriteAllText($candidateFile,$candidate,(New-Object Text.UTF8Encoding($true)))
    $now=[datetime]::UtcNow.AddMinutes(-10)
    function Add-Fixture([string]$status,[datetime]$t){
        $row=New-Object 'C545DMetadataJournalPrototype+Row'
        $row.Utc=$t;$row.Status=$status
        $row.DurationMs=3600123;$row.VideoTracks=1;$row.AudioTracks=1;$row.Width=2560;$row.Height=720
        $row.FpsNum=15;$row.FpsDen=1;$row.SampleRate=48000;$row.Channels=1;$row.H264=1;$row.Aac=1
        if($status -eq 'profile_mismatch'){$row.AudioTracks=0;$row.Aac=-1}
        if($status -eq 'probe_unavailable'){
            $row.DurationMs=-1;$row.VideoTracks=-1;$row.AudioTracks=-1;$row.Width=-1;$row.Height=-1
            $row.FpsNum=-1;$row.FpsDen=-1;$row.SampleRate=-1;$row.Channels=-1;$row.H264=-1;$row.Aac=-1
        }
        if([C545DMetadataJournalPrototype]::Append($journal,$row) -ne 'saved'){throw 'FIXTURE_SAVE_FAILED'}
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
        if($new){$argsList+=@('-MetadataJournalRoot',$journal,'-MetadataJournalSource',$journalSource)}
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
    Assert-Eq @(Get-ChildItem $new -File).Count 6 'NEW_FILES'
    foreach($file in @('process_metrics.csv','recording_events.csv','recorder_sessions.csv')){
        Assert-Eq (Get-FileHash (Join-Path $old $file)).Hash (Get-FileHash (Join-Path $new $file)).Hash 'OLD_CSV_PARITY'
    }
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
    $recovery=[C545DMetadataJournalPrototype]::RecoverTornTail($journal,$now)
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
    $missing=Run-Export $candidateFile 'missing' $true
    $m=Get-Content (Join-Path $missing 'manifest.json') -Raw|ConvertFrom-Json
    Assert-Eq $m.metadata_journal_source_status 'not_found' 'MISSING'
    Assert-Eq $m.metadata_event_count 0 'MISSING_ROWS'
    Assert-Eq $m.metadata_event_coverage 'not_proven' 'MISSING_NOT_HEALTH'
    Assert-Eq $m.metadata_rename_count_difference 'not_classified' 'MISSING_DIFF'
    Write-Host 'C545D_METADATA_ZIP_INTEGRATION_PASS,baseline_files=5,candidate_files=6,legacy_csv_parity=3,profile_match=1,profile_mismatch=1,unknown=1,count_gap=1,equal_not_proof=1,corrupt_excluded=1,missing_unknown=1,privacy=1,host_modified=0'
}finally{Remove-Item -LiteralPath $root -Recurse -Force}
