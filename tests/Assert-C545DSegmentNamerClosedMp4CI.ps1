#Requires -Version 5.1
<#
CI ONLY: exercise the actual, unmodified SegmentNamerWorker.ps1 against a
previously decoded synthetic H264/AAC MP4. All files are private stage-owned.
No production recorder, camera, installed DLL, registry or user directory.
The watcher must not rename an exclusively open file and must rename exactly
four closed temporary-name MP4 copies while preserving unrelated filenames.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$StageRoot,
  [Parameter(Mandatory=$true)][string]$SampleMp4
)
$ErrorActionPreference='Stop'
$state='BLOCKED';$readyOk=0;$deferred=0;$renamedCount=0
$manualPreserved=0;$cleanExit=0;$integrity=0;$unchanged=0
$watcher=$null;$locked=$null;$src=$null;$phase='PRECHECK'
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_DISPOSABLE_CI'}
  $root=[IO.Path]::GetFullPath($StageRoot).TrimEnd('\')
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  if(-not [string]::Equals([IO.Path]::GetDirectoryName($root).TrimEnd('\'),
        $temp,[StringComparison]::OrdinalIgnoreCase) -or
     [IO.Path]::GetFileName($root) -notmatch '^c545d-ci-production-mirror-[a-f0-9]{32}$' -or
     [IO.File]::ReadAllText((Join-Path $root '.c545d-ci-owned')) -cne
       'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){throw 'UNOWNED_STAGE'}
  $item=Get-Item -LiteralPath $root -Force
  if(-not $item.PSIsContainer -or
     ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'UNSAFE_STAGE'}
  $sample=[IO.Path]::GetFullPath($SampleMp4)
  $expectedParent=Join-Path $root 'private-output'
  if(-not [string]::Equals([IO.Path]::GetDirectoryName($sample),$expectedParent,
        [StringComparison]::OrdinalIgnoreCase)){throw 'UNOWNED_SAMPLE'}
  $sampleItem=Get-Item -LiteralPath $sample -Force
  if($sampleItem.PSIsContainer -or
     ($sampleItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
     $sampleItem.Length -lt 30000){throw 'INVALID_MP4_SAMPLE'}
  $privateLocal=[IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')
  if(-not [string]::Equals($privateLocal,(Join-Path $root 'ci-localappdata'),
        [StringComparison]::OrdinalIgnoreCase)){throw 'NONPRIVATE_ENVIRONMENT'}
  $sourceRoot=Split-Path -Parent $PSScriptRoot
  $namerSource=Join-Path $sourceRoot 'SegmentNamer.ps1'
  $workerSource=Join-Path $sourceRoot 'SegmentNamerWorker.ps1'
  $beforeNamer=(Get-FileHash -LiteralPath $namerSource -Algorithm SHA256).Hash
  $beforeWorker=(Get-FileHash -LiteralPath $workerSource -Algorithm SHA256).Hash
  $sourceHash=(Get-FileHash -LiteralPath $sample -Algorithm SHA256).Hash
  $folder=Join-Path $root 'namer-fixture'
  if(Test-Path -LiteralPath $folder){throw 'FIXTURE_EXISTS'}
  [void](New-Item -ItemType Directory -Path $folder -ErrorAction Stop)
  $ready=Join-Path $root 'namer-fixture.ready'
  $stop=Join-Path $root 'namer-fixture.stop'
  if((Test-Path -LiteralPath $ready) -or (Test-Path -LiteralPath $stop)){
    throw 'MARKER_EXISTS'
  }
  $manual=Join-Path $folder 'manual_preserved.mp4'
  Copy-Item -LiteralPath $sample -Destination $manual -ErrorAction Stop
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $argLine='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+
     $workerSource+'" -OutputDirectory "'+$folder+'" -OwnerProcessId '+$PID+
     ' -ReadyFile "'+$ready+'" -StopFile "'+$stop+'"'
  $phase='WATCHER_READY'
  $watcher=Start-Process -FilePath $ps -ArgumentList $argLine -PassThru -WorkingDirectory $root -WindowStyle Hidden -ErrorAction Stop
  for($i=0;$i -lt 120;$i++){
    Start-Sleep -Milliseconds 100
    if($watcher.HasExited){break}
    if(Test-Path -LiteralPath $ready -PathType Leaf){$readyOk=1;break}
  }
  if($readyOk -ne 1){throw 'WATCHER_NOT_READY'}
  $phase='LOCKED_FILE'
  $names=@(
    '2026-11-21_08-00-00-000_00000.mp4',
    '2026-11-21_08-00-01-000_00001.mp4',
    '2026-11-21_08-00-02-000_00002.mp4',
    '2026-11-21_08-00-03-000_00003.mp4'
  )
  $first=Join-Path $folder $names[0]
  $locked=[IO.File]::Open($first,[IO.FileMode]::CreateNew,
      [IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
  $src=[IO.File]::OpenRead($sample)
  try {$src.CopyTo($locked);$locked.Flush()} finally {$src.Dispose();$src=$null}
  # Wait for the genuine event callback and first rename attempt while
  # FileShare.None prevents access to this still-open MP4.
  $eventObserved=0
  $log=Join-Path (Join-Path $privateLocal 'C545D_GStreamer\Logs') 'Filename_Rename.log'
  for($i=0;$i -lt 80;$i++){
    Start-Sleep -Milliseconds 100
    if($watcher.HasExited){throw 'WATCHER_EARLY_EXIT'}
    if(Test-Path -LiteralPath $log -PathType Leaf){
      try {
        $stream=[IO.File]::Open($log,[IO.FileMode]::Open,
              [IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
        try {
          $reader=New-Object IO.StreamReader($stream)
          $txt=$reader.ReadToEnd()
        } finally {$stream.Dispose()}
        if($txt.Contains('Event: new temporary MP4 '+$names[0])){
          $eventObserved=1;break
        }
      } catch [IO.IOException] {}
    }
  }
  if($eventObserved -ne 1){throw 'CREATION_EVENT_MISSING'}
  Start-Sleep -Milliseconds 1600
  $present=@(Get-ChildItem -LiteralPath $folder -File -Filter '*.mp4')
  if(-not (Test-Path -LiteralPath $first -PathType Leaf) -or
     $present.Count -ne 2){throw 'PREMATURE_RENAME'}
  $deferred=1
  $locked.Dispose();$locked=$null
  $phase='CLOSED_MP4'
  for($i=1;$i -lt $names.Count;$i++){
    Copy-Item -LiteralPath $sample -Destination (Join-Path $folder $names[$i]) -ErrorAction Stop
    Start-Sleep -Milliseconds 250
  }
  $finalNameRegex='^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_\d{2}-\d{2}(?:_\d{2})?\.mp4$'
  $finalFiles=@()
  for($i=0;$i -lt 450;$i++){
    Start-Sleep -Milliseconds 100
    if($watcher.HasExited){throw 'WATCHER_EARLY_EXIT'}
    $files=@(Get-ChildItem -LiteralPath $folder -File -Filter '*.mp4')
    $finalFiles=@($files|Where-Object {$_.Name -cmatch $finalNameRegex})
    $pending=@($files|Where-Object {$_.Name -in $names})
    if($finalFiles.Count -eq 4 -and $pending.Count -eq 0){break}
  }
  $renamedCount=$finalFiles.Count
  if($renamedCount -ne 4){throw 'RENAME_INCOMPLETE'}
  foreach($file in $finalFiles){
    if((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -cne $sourceHash){
      throw 'RENAME_MODIFIED_MP4'
    }
  }
  $integrity=1
  $manualPreserved=[int]((Test-Path -LiteralPath $manual -PathType Leaf) -and
    (Get-FileHash -LiteralPath $manual -Algorithm SHA256).Hash -ceq $sourceHash)
  if($manualPreserved -ne 1){throw 'UNRELATED_FILE_CHANGED'}
  $phase='SHUTDOWN'
  [IO.File]::WriteAllText($stop,'CI_TEST_SHUTDOWN')
  if(-not $watcher.WaitForExit(16000) -or $watcher.ExitCode -ne 0){
    throw 'WATCHER_SHUTDOWN_FAILED'
  }
  $cleanExit=1
  $unchanged=[int]((Get-FileHash -LiteralPath $namerSource -Algorithm SHA256).Hash -ceq $beforeNamer -and
    (Get-FileHash -LiteralPath $workerSource -Algorithm SHA256).Hash -ceq $beforeWorker)
  if($unchanged -ne 1){throw 'NAMER_SOURCE_CHANGED'}
  $state='PASS'
} catch {
  $allowed=@('NOT_DISPOSABLE_CI','UNOWNED_STAGE','UNSAFE_STAGE',
    'UNOWNED_SAMPLE','INVALID_MP4_SAMPLE','NONPRIVATE_ENVIRONMENT',
    'FIXTURE_EXISTS','MARKER_EXISTS','WATCHER_NOT_READY','WATCHER_EARLY_EXIT',
    'CREATION_EVENT_MISSING','PREMATURE_RENAME','RENAME_INCOMPLETE',
    'RENAME_MODIFIED_MP4','UNRELATED_FILE_CHANGED','WATCHER_SHUTDOWN_FAILED',
    'NAMER_SOURCE_CHANGED')
  $code=[string]$_.Exception.Message
  if($code -in $allowed){$state=$code}else{$state='BLOCKED'}
} finally {
  if($src){$src.Dispose()}
  if($locked){$locked.Dispose()}
  if($watcher){
    if(-not $watcher.HasExited){
      # CI-only cleanup of this private watcher child. A forced stop is FAIL.
      try {$watcher.Kill();[void]$watcher.WaitForExit(4000)}catch{}
    }
    $watcher.Dispose()
  }
}
Write-Output "C545D_SEGMENT_NAMER_CI,ready=$readyOk,locked_deferred=$deferred,renamed=$renamedCount,mp4_hashes_intact=$integrity,manual_preserved=$manualPreserved,clean_exit=$cleanExit,source_unchanged=$unchanged,real_camera=0,host_modified=0,reason=$state"
if($state -ceq 'PASS' -and $readyOk -eq 1 -and $deferred -eq 1 -and
   $renamedCount -eq 4 -and $integrity -eq 1 -and $manualPreserved -eq 1 -and
   $cleanExit -eq 1 -and $unchanged -eq 1){exit 0}
exit 3
