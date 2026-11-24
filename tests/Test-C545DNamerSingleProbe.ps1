# CI-only integration against actual SegmentNamer.ps1, never packaged or run on host.
param([Parameter(Mandatory=$true)][string]$FixtureDirectory,
      [Parameter(Mandatory=$true)][string]$ProbeExe)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
. (Join-Path $repo 'tests/C545D-ClosedMetadataPrototype.ps1')
if(-not ('C545DClosedProbePrototype' -as [type])){
    Add-Type -Path (Join-Path $repo 'tests/C545DClosedProbePrototype.cs')
}
$original=[IO.File]::ReadAllText((Join-Path $repo 'SegmentNamer.ps1'))
$script:logRoot=Join-Path $FixtureDirectory 'integration-logs'
$baseline=Join-Path $FixtureDirectory 'baseline'
$candidate=Join-Path $FixtureDirectory 'candidate'
foreach($dir in @($script:logRoot,$baseline,$candidate)){
    New-Item -ItemType Directory -Path $dir -ErrorAction Stop | Out-Null
}
function Set-NamerFixture([string]$root,[string]$source,[string]$name){
    $p=Join-Path $root $name
    Copy-Item -LiteralPath $source -Destination $p -ErrorAction Stop
    [IO.File]::SetCreationTime($p,[datetime]'2026-11-24T12:00:59.500')
    [IO.File]::SetLastWriteTime($p,[datetime]'2026-11-24T12:02:00')
    return $p
}
function Set-NamerProbe([string]$path){
    $script:C545DProbePath=$path
    $script:C545DProbeSearched=$true
    $script:C545DNamerLogDir=$script:logRoot
}
function Assert-Equal($actual,$expected,[string]$tag){
    if($actual -cne $expected){throw ('INTEGRATION_ASSERT_'+$tag)}
}
$fixture=Join-Path $FixtureDirectory '2026-11-24_12-00_12-01.mp4'
$noAudio=Join-Path $FixtureDirectory 'no-audio.mp4'
$pending='C545D_PENDING_20261124_120000_12345678_00001.mp4'
$collision='2026-11-24_12-00_12-01.mp4'
# Baseline uses the real unmodified rename and its duration-only probe.
. ([scriptblock]::Create($original))
Set-NamerProbe $ProbeExe
$basePath=Set-NamerFixture $baseline $fixture $pending
[IO.File]::WriteAllText((Join-Path $baseline $collision),'collision')
Assert-Equal (Invoke-C545DRenameOne $basePath $baseline) 'done' 'BASELINE_DONE'
$baseFinal=@(Get-ChildItem -LiteralPath $baseline -File | Where-Object Name -ne $collision)
Assert-Equal $baseFinal.Count 1 'BASELINE_COUNT'
# Compile an isolated candidate from the exact actual source. Fail if anchors drift.
# Capture once after the original exclusive-open gate, publish only after actual Move-Item.
$old='        $duration=Get-C545DDuration $file.FullName'
$new=@'
        $duration=$null
        $observation=$null
        $probeExe=Get-C545DProbeExe
        if($probeExe){
            $script:probeCalls++
            $observation=[C545DClosedProbePrototype]::ProbeRenameCandidate($root,$name,$true,$probeExe,4000)
            if($observation.Status -eq 'ok'){
                try{
                    $doc=ConvertFrom-Json -InputObject $observation.Json -ErrorAction Stop
                    $d=0.0
                    if([double]::TryParse([string]$doc.format.duration,
                        [Globalization.NumberStyles]::Float,
                        [Globalization.CultureInfo]::InvariantCulture,[ref]$d) -and
                        $d -gt 0 -and -not [double]::IsInfinity($d)){
                        $duration=$d
                    }
                }catch{}
            }
        }
'@
$anchor="        return 'done'"
$replacement=@'
        # A diagnostic failure is not a failed rename; no retries of a moved file.
        try{
            if($null -eq $observation){
                $row=ConvertTo-C545DMetadataEvidence '' 1
                $row.metadata_status='probe_unavailable'
            }else{
                $row=ConvertTo-C545DMetadataEvidence $observation.Json $observation.ExitCode
            }
            Publish-C545DTestEvidence $row
        }catch{$script:publishFailures++}
        return 'done'
'@
foreach($token in @($old,$anchor)){
    if(([regex]::Matches($original,[regex]::Escape($token))).Count -ne 1){
        throw 'SOURCE_ANCHOR_DRIFT'
    }
}
$modified=$original.Replace($old,$new).Replace($anchor,$replacement)
. ([scriptblock]::Create($modified))
$script:probeCalls=0
$script:publishFailures=0
$script:failPublish=$false
$script:rows=New-Object 'System.Collections.Generic.List[object]'
$journalRoot=Join-Path $FixtureDirectory 'integration-journal'
New-Item -ItemType Directory -Path $journalRoot | Out-Null
if(-not ('C545DMetadataJournalPrototype' -as [type])){
    Add-Type -Path (Join-Path $repo 'tests/C545DMetadataJournalPrototype.cs')
}
$journalBegin=[datetime]::UtcNow.AddMinutes(-1)

function Publish-C545DTestEvidence($row){
    if($script:failPublish){throw 'SYNTHETIC_SINK_FAILURE'}
    $entry=New-Object 'C545DMetadataJournalPrototype+Row'
    $entry.Utc=[datetime]::UtcNow
    $entry.Status=$row.metadata_status
    $entry.DurationMs=$row.duration_ms
    $entry.VideoTracks=$row.video_tracks;$entry.AudioTracks=$row.audio_tracks
    $entry.Width=$row.width;$entry.Height=$row.height
    $entry.FpsNum=$row.fps_num;$entry.FpsDen=$row.fps_den
    $entry.SampleRate=$row.sample_rate;$entry.Channels=$row.channels
    $entry.H264=$row.video_h264;$entry.Aac=$row.audio_aac
    $status=[C545DMetadataJournalPrototype]::Append($journalRoot,$entry)
    if($status -ne 'saved'){throw ('JOURNAL_PUBLISH_'+$status)}
    $script:rows.Add($row)
}
Set-NamerProbe $ProbeExe
$target=Set-NamerFixture $candidate $fixture $pending
[IO.File]::WriteAllText((Join-Path $candidate $collision),'collision')
$hash=(Get-FileHash -LiteralPath $target).Hash
Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'done' 'CANDIDATE_DONE'
Assert-Equal $script:probeCalls 1 'SINGLE_PROBE'
Assert-Equal $script:rows.Count 1 'ONE_EVENT'
Assert-Equal $script:rows[0].metadata_status 'profile_match_metadata_only' 'NORMAL_PROFILE'
$actualFinal=Join-Path $candidate $baseFinal[0].Name
Assert-Equal (Test-Path -LiteralPath $actualFinal) $true 'EXACT_FILENAME_PARITY'
Assert-Equal (Get-FileHash -LiteralPath $actualFinal).Hash $hash 'UNCHANGED_HASH'
Assert-Equal ([IO.File]::ReadAllText((Join-Path $candidate $collision))) 'collision' 'COLLISION_PRESERVED'
# Replaying renamed event cannot probe or emit again.
Assert-Equal (Invoke-C545DRenameOne $actualFinal $candidate) 'skip' 'FINAL_SKIP'
Assert-Equal $script:probeCalls 1 'NO_DUPLICATE'
# Wrong AV profile has valid duration: rename as usual, record separate diagnosis.
$target=Set-NamerFixture $candidate $noAudio $pending
Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'done' 'NO_AUDIO_RENAME'
Assert-Equal $script:probeCalls 2 'NO_AUDIO_SINGLE_PROBE'
Assert-Equal $script:rows[1].metadata_status 'profile_mismatch' 'NO_AUDIO_CLASS'
# Active writer must block before any probe or success event.
$target=Set-NamerFixture $candidate $fixture $pending
$lock=[IO.File]::Open($target,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)
try{
    Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'pending' 'LOCKED'
    Assert-Equal $script:probeCalls 2 'LOCKED_NO_PROBE'
    Assert-Equal $script:rows.Count 2 'LOCKED_NO_EVENT'
}finally{$lock.Dispose()}
# Force actual move failure through a CI-local function shadow, never a success event.
function Move-Item {throw 'SYNTHETIC_MOVE_FAILURE'}
try{
    Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'pending' 'MOVE_FAILED'
    Assert-Equal $script:probeCalls 3 'MOVE_FAILED_PROBED_ONCE'
    Assert-Equal $script:rows.Count 2 'MOVE_FAILED_NO_EVENT'
    Assert-Equal (Test-Path -LiteralPath $target) $true 'MOVE_FAILED_SOURCE_REMAINS'
}finally{Remove-Item Function:Move-Item}
# Diagnostic publication failure cannot reverse successful rename.
$script:failPublish=$true
Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'done' 'PUBLISH_FAILURE_RENAME_DONE'
Assert-Equal $script:publishFailures 1 'PUBLISH_FAILURE_COUNTED'
Assert-Equal $script:probeCalls 4 'PUBLISH_FAILURE_SINGLE_PROBE'
Assert-Equal (Test-Path -LiteralPath $target) $false 'PUBLISH_FAILURE_SOURCE_MOVED'
$script:failPublish=$false
# Broken MP4 larger than readiness threshold retains original pending policy.
$target=Join-Path $candidate $pending
[IO.File]::WriteAllBytes($target,(New-Object byte[] 2048))
Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'pending' 'BAD_MP4_PENDING'
Assert-Equal $script:probeCalls 5 'BAD_MP4_SINGLE_PROBE'
Assert-Equal $script:rows.Count 2 'BAD_MP4_NO_EVENT'
Remove-Item -LiteralPath $target
# Missing ffprobe retains existing timestamp fallback, no successful profile assertion.
Set-NamerProbe ''
$target=Set-NamerFixture $candidate $fixture $pending
Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'done' 'NO_PROBE_FALLBACK'
Assert-Equal $script:probeCalls 5 'NO_PROBE_NO_CHILD'
Assert-Equal $script:rows[2].metadata_status 'probe_unavailable' 'NO_PROBE_UNKNOWN'
$blob=ConvertTo-Json -InputObject ($script:rows.ToArray()) -Compress
if($blob -match 'rtsp|secret|filename|[A-Za-z]:\\'){throw 'EVIDENCE_PRIVACY'}
Write-Host 'C545D_NAMER_SINGLE_PROBE_PASS,baseline_name_parity=1,collision_preserved=1,media_hash_unchanged=1,normal_probes=1,wrong_profile_rename=1,locked_no_probe=1,move_failed_no_event=1,publish_failed_rename_done=1,invalid_mp4_pending=1,missing_probe_fallback=1,duplicate_probe=0,host_modified=0'

# Persistent sink evidence must agree with successful publication, not every rename.
$journalEnd=[datetime]::UtcNow.AddMinutes(1)
$snapshot=[C545DMetadataJournalPrototype]::ReadWindow($journalRoot,$journalBegin,$journalEnd)
Assert-Equal $snapshot.Rows.Count 3 'JOURNAL_PERSISTED'
Assert-Equal $snapshot.Status 'coverage_unverified' 'JOURNAL_NO_OVERCLAIM'
Assert-Equal @($snapshot.Rows | Where-Object Status -eq 'profile_match_metadata_only').Count 1 'JOURNAL_MATCH'
Assert-Equal @($snapshot.Rows | Where-Object Status -eq 'profile_mismatch').Count 1 'JOURNAL_MISMATCH'
Assert-Equal @($snapshot.Rows | Where-Object Status -eq 'probe_unavailable').Count 1 'JOURNAL_UNKNOWN'
# Real journal file contention must be isolated from a completed rename.
$journalFiles=@(Get-ChildItem -LiteralPath $journalRoot -File)
Assert-Equal $journalFiles.Count 1 'JOURNAL_ONE_DAY'
$journalLock=[IO.File]::Open($journalFiles[0].FullName,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try{
    $target=Set-NamerFixture $candidate $fixture $pending
    Assert-Equal (Invoke-C545DRenameOne $target $candidate) 'done' 'JOURNAL_BUSY_RENAME_DONE'
    Assert-Equal (Test-Path -LiteralPath $target) $false 'JOURNAL_BUSY_MOVED'
    Assert-Equal $script:publishFailures 2 'JOURNAL_BUSY_FAILURE'
    Assert-Equal $script:probeCalls 5 'JOURNAL_BUSY_NO_EXTRA_PROBE'
}finally{$journalLock.Dispose()}
# Read from another PowerShell process to prove persistence independently of memory.
$readerScript=Join-Path $PSScriptRoot 'Read-C545DMetadataJournalFixture.ps1'
& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $readerScript -JournalRoot $journalRoot
if($LASTEXITCODE -ne 0){throw 'JOURNAL_READER_CHILD_FAILED'}
Write-Host 'C545D_NAMER_PERSISTENT_SINK_PASS,persisted=3,busy_rename_done=1,publication_failures=2,separate_reader=1,coverage_unverified=1,host_modified=0'
