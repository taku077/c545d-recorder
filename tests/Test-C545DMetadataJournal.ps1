# CI-only; synthetic event journal test, no camera or media access.
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'C545DMetadataJournalPrototype.cs')
$root=Join-Path $env:RUNNER_TEMP ('c545d-meta-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
function Assert-Eq($a,$b,[string]$tag){if($a -cne $b){throw ('JOURNAL_ASSERT_'+$tag+' actual='+$a+' expected='+$b)}}
function New-Row([datetime]$t){
    $row=New-Object 'C545DMetadataJournalPrototype+Row'
    $row.Utc=$t;$row.Status='profile_match_metadata_only';$row.DurationMs=3600123
    $row.VideoTracks=1;$row.AudioTracks=1;$row.Width=2560;$row.Height=720
    $row.FpsNum=15;$row.FpsDen=1;$row.SampleRate=48000;$row.Channels=1;$row.H264=1;$row.Aac=1
    return $row
}
function Save-Row($row){[C545DMetadataJournalPrototype]::Append($root,$row)}
function Get-Snapshot([datetime]$b,[datetime]$e){[C545DMetadataJournalPrototype]::ReadWindow($root,$b,$e)}
$start=[datetime]::new(2026,10,1,0,0,0,[DateTimeKind]::Utc)
try{
    Assert-Eq (Get-Snapshot $start $start.AddDays(1)).Status 'no_events_coverage_unverified' 'EMPTY'
    # 40 days of simulated hourly events, no wall-clock wait.
    for($d=0;$d -lt 40;$d++){
        for($h=0;$h -lt 24;$h++){
            Assert-Eq (Save-Row (New-Row $start.AddDays($d).AddHours($h))) 'saved' 'HOURLY'
        }
    }
    $files=@(Get-ChildItem -LiteralPath $root -File)
    Assert-Eq $files.Count 32 'FIXED_SLOTS'
    $latest=$start.AddDays(40)
    $week=Get-Snapshot $latest.AddDays(-7) $latest
    Assert-Eq $week.Rows.Count 168 'LAST_WEEK'
    Assert-Eq $week.Status 'coverage_unverified' 'NO_OVERCLAIM'
    Assert-Eq (Get-Snapshot $latest.AddDays(-31) $latest).Rows.Count 744 '31DAY_WINDOW'
    Assert-Eq (Save-Row (New-Row $start)) 'clock_rollback' 'STALE_WRITE'
    $bad=New-Row $latest
    $bad.Status='rtsp://synthetic:PRIVATE_SECRET@192.0.2.1/stream6'
    Assert-Eq (Save-Row $bad) 'invalid_row' 'SECRET'
    $bad=New-Row $latest;$bad.Width=1280
    Assert-Eq (Save-Row $bad) 'invalid_row' 'FALSE_PROFILE'
    $unavailable=New-Row $latest
    $unavailable.Status='probe_unavailable';$unavailable.DurationMs=-1
    $unavailable.VideoTracks=-1;$unavailable.AudioTracks=-1;$unavailable.Width=-1;$unavailable.Height=-1
    $unavailable.FpsNum=-1;$unavailable.FpsDen=-1;$unavailable.SampleRate=-1;$unavailable.Channels=-1;$unavailable.H264=-1;$unavailable.Aac=-1
    Assert-Eq (Save-Row $unavailable) 'saved' 'UNKNOWN'
    for($i=1;$i -lt 256;$i++){Assert-Eq (Save-Row (New-Row $latest.AddSeconds($i))) 'saved' 'FILL'}
    Assert-Eq (Save-Row (New-Row $latest.AddSeconds(257))) 'capacity_reached' 'CAP'
    $day=Get-Snapshot $latest $latest.AddDays(1)
    Assert-Eq $day.Rows.Count 256 'CAP_ROWS'
    Assert-Eq $day.SaturatedSlots 1 'CAP_VISIBLE'
    Assert-Eq $day.Status 'partial_or_unavailable' 'CAP_COVERAGE'
    Assert-Eq $day.Rows[0].Status 'probe_unavailable' 'UNKNOWN_ROUNDTRIP'
    $slot=@(Get-ChildItem -LiteralPath $root -File | Where-Object {
        [IO.File]::ReadAllText($_.FullName).StartsWith('C545D_META_V1|'+$latest.ToString('yyyyMMdd'))
    })
    Assert-Eq $slot.Count 1 'CURRENT_SLOT'
    $hash=(Get-FileHash -LiteralPath $slot[0].FullName).Hash
    $lock=[IO.File]::Open($slot[0].FullName,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{
        Assert-Eq (Save-Row (New-Row $latest)) 'busy_or_io_error' 'BUSY_WRITER'
        $busy=Get-Snapshot $latest $latest.AddDays(1)
        Assert-Eq $busy.BusySlots 1 'BUSY_READER'
        Assert-Eq $busy.Status 'partial_or_unavailable' 'BUSY_COVERAGE'
    }finally{$lock.Dispose()}
    Assert-Eq (Get-FileHash -LiteralPath $slot[0].FullName).Hash $hash 'BUSY_UNCHANGED'
    $total=0L
    foreach($file in @(Get-ChildItem -LiteralPath $root -File)){
        $total+=$file.Length
        if($file.Length -gt 65536 -or [IO.File]::ReadAllText($file.FullName) -match 'rtsp|PRIVATE_SECRET|192\.0\.2\.1'){throw 'JOURNAL_PRIVACY_OR_CAP'}
    }
    if($total -gt 2097152){throw 'JOURNAL_TOTAL_CAP'}
    # Simulate interrupted append / malicious data. Do not export partial slot.
    [IO.File]::AppendAllText($slot[0].FullName,'incomplete')
    $corrupt=Get-Snapshot $latest $latest.AddDays(1)
    Assert-Eq $corrupt.InvalidSlots 1 'CORRUPT_SLOT'
    Assert-Eq $corrupt.Rows.Count 0 'CORRUPT_NO_ROWS'
    Assert-Eq $corrupt.Status 'partial_or_unavailable' 'CORRUPT_COVERAGE'
    Assert-Eq (Save-Row (New-Row $latest)) 'source_invalid' 'CORRUPT_WRITE_DENIED'
    # Recovery is explicit: only a complete validated prefix and incomplete tail.
    $recoverDay=$latest.AddDays(1)
    Assert-Eq (Save-Row (New-Row $recoverDay)) 'saved' 'RECOVERY_FIRST'
    Assert-Eq (Save-Row (New-Row $recoverDay.AddHours(1))) 'saved' 'RECOVERY_SECOND'
    $recoverySlot=@(Get-ChildItem -LiteralPath $root -File | Where-Object {
        [IO.File]::ReadAllText($_.FullName).StartsWith('C545D_META_V1|'+$recoverDay.ToString('yyyyMMdd'))
    })[0].FullName
    $intact=[IO.File]::ReadAllText($recoverySlot)
    [IO.File]::AppendAllText($recoverySlot,'20261110T020000.000')
    $tornHash=(Get-FileHash $recoverySlot).Hash
    $lock=[IO.File]::Open($recoverySlot,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{Assert-Eq ([C545DMetadataJournalPrototype]::RecoverTornTail($root,$recoverDay)) 'busy_or_io_error' 'RECOVERY_BUSY'}
    finally{$lock.Dispose()}
    Assert-Eq (Get-FileHash $recoverySlot).Hash $tornHash 'RECOVERY_BUSY_UNCHANGED'
    Assert-Eq ([C545DMetadataJournalPrototype]::RecoverTornTail($root,$recoverDay.AddDays(-32))) 'not_recoverable' 'RECOVERY_WRONG_DAY'
    Assert-Eq ([C545DMetadataJournalPrototype]::RecoverTornTail($root,$recoverDay)) 'recovered_loss_possible' 'RECOVERY_SUCCESS'
    Assert-Eq ([IO.File]::ReadAllText($recoverySlot)) ($intact.Replace('C545D_META_V1|','C545D_META_R1|')) 'RECOVERY_PREFIX_EXACT'
    $restored=Get-Snapshot $recoverDay $recoverDay.AddDays(1)
    Assert-Eq $restored.Rows.Count 2 'RECOVERY_ROWS'
    Assert-Eq $restored.RecoveredSlots 1 'RECOVERY_MARKER'
    Assert-Eq $restored.Status 'partial_or_unavailable' 'RECOVERY_COVERAGE'
    Assert-Eq (Save-Row (New-Row $recoverDay.AddHours(2))) 'saved' 'RECOVERY_APPEND'
    Assert-Eq (Get-Snapshot $recoverDay $recoverDay.AddDays(1)).Rows.Count 3 'RECOVERY_CONTINUE'
    Assert-Eq ([C545DMetadataJournalPrototype]::RecoverTornTail($root,$recoverDay)) 'not_torn_tail' 'RECOVERY_IDEMPOTENT'
    # Refuse a malformed complete row followed by a torn fragment.
    [IO.File]::AppendAllText($recoverySlot,('bad-complete'+[char]10+'torn'))
    $badHash=(Get-FileHash $recoverySlot).Hash
    Assert-Eq ([C545DMetadataJournalPrototype]::RecoverTornTail($root,$recoverDay)) 'not_recoverable' 'RECOVERY_BAD_PREFIX'
    Assert-Eq (Get-FileHash $recoverySlot).Hash $badHash 'RECOVERY_BAD_PREFIX_UNCHANGED'
    Write-Host 'C545D_JOURNAL_TORN_TAIL_PASS,complete_rows_preserved=2,append_after_recovery=1,loss_marker=1,locked_unchanged=1,wrong_day_denied=1,corrupt_prefix_denied=1,idempotent=1,real_power_cut=0'
    # Automatic recovery uses a single attempt on a same-day invalid append.
    $autoDay=$recoverDay.AddDays(1)
    Assert-Eq (Save-Row (New-Row $autoDay)) 'saved' 'AUTO_FIRST'
    $autoSlot=@(Get-ChildItem -LiteralPath $root -File | Where-Object {
        [IO.File]::ReadAllText($_.FullName).StartsWith('C545D_META_V1|'+$autoDay.ToString('yyyyMMdd'))
    })[0].FullName
    [IO.File]::AppendAllText($autoSlot,'interrupted')
    Assert-Eq ([C545DMetadataJournalPrototype]::AppendRecovering($root,(New-Row $autoDay.AddHours(1)))) 'saved_after_recovery' 'AUTO_RECOVERED'
    $auto=Get-Snapshot $autoDay $autoDay.AddDays(1)
    Assert-Eq $auto.Rows.Count 2 'AUTO_ROWS'
    Assert-Eq $auto.RecoveredSlots 1 'AUTO_LOSS_MARKER'
    [IO.File]::AppendAllText($autoSlot,('bad-complete'+[char]10))
    $autoHash=(Get-FileHash $autoSlot).Hash
    Assert-Eq ([C545DMetadataJournalPrototype]::AppendRecovering($root,(New-Row $autoDay.AddHours(2)))) 'corrupt_slot_preserved' 'AUTO_CORRUPT_REFUSED'
    Assert-Eq (Get-FileHash $autoSlot).Hash $autoHash 'AUTO_CORRUPT_UNCHANGED'
    Assert-Eq ([C545DMetadataJournalPrototype]::AppendRecovering($root,(New-Row $autoDay.AddDays(1)))) 'saved' 'AUTO_NEXT_DAY'
    $lock=[IO.File]::Open($autoSlot,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try{Assert-Eq ([C545DMetadataJournalPrototype]::AppendRecovering($root,(New-Row $autoDay))) 'busy_or_io_error' 'AUTO_BUSY_NO_RETRY'}
    finally{$lock.Dispose()}
    Write-Host 'C545D_JOURNAL_AUTO_RECOVERY_PASS,recovered_append=1,rows=2,loss_marker=1,corrupt_preserved=1,next_day_saved=1,busy_no_retry=1'
    $junction=$root+'-junction'
    New-Item -ItemType Junction -Path $junction -Target $root | Out-Null
    try{Assert-Eq ([C545DMetadataJournalPrototype]::Append($junction,(New-Row $latest))) 'root_rejected' 'REPARSE'}
    finally{[IO.Directory]::Delete($junction)}
    Write-Host ('C545D_METADATA_JOURNAL_PASS,simulated_days=40,hourly_writes=960,slots=32,week_rows=168,day_cap=256,byte_cap=2097152,actual_bytes='+$total+',busy=1,corrupt=1,clock_rollback=1,privacy=1,coverage_unverified=1,host_modified=0')
}finally{Remove-Item -LiteralPath $root -Recurse -Force}
