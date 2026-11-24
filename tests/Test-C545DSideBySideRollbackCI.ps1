# CI-only: side-by-side rollback between two previously built candidate ZIPs.
# No camera, no installed DLL replacement, no changes to the user's host.
param([Parameter(Mandatory=$true)][string]$OldZip,[Parameter(Mandatory=$true)][string]$NewZip)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
   $env:RUNNER_ENVIRONMENT -cne 'github-hosted'){throw 'CI_ONLY'}
$root=Join-Path $env:RUNNER_TEMP ('c545d-rollback-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -ErrorAction Stop|Out-Null
$oldDir=Join-Path $root 'previous'
$newDir=Join-Path $root 'candidate'
$data=Join-Path $root 'private-appdata'
$output=Join-Path $root 'private-output'
$store=Join-Path $root 'observer'
New-Item -ItemType Directory -Path $data,$output,$store|Out-Null
$ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$prior=@{}
foreach($key in @('LOCALAPPDATA','C545D_NATIVE_SMOKE_OUTPUT','C545D_SEI_AU_FILTER','C545D_METADATA_V04','C545D_METADATA_PROBE_SHA256')){
 $prior[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
}
function Get-Tree([string]$dir){
 $map=@{}
 foreach($f in Get-ChildItem -LiteralPath $dir -File -Recurse -Force){
  if($f.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'PACKAGE_REPARSE'}
  $map[$f.FullName.Substring($dir.Length+1)]=(Get-FileHash -LiteralPath $f.FullName).Hash
 }
 return $map
}
function Assert-Tree($before,$after){
 if($before.Count -ne $after.Count){throw 'TREE_COUNT_CHANGED'}
 foreach($key in $before.Keys){if($before[$key] -cne $after[$key]){throw 'TREE_BYTES_CHANGED'}}
}
function Expand-Checked([string]$zip,[string]$dir,[string]$commit){
 Expand-Archive -LiteralPath $zip -DestinationPath $dir
 $m=Get-Content -LiteralPath (Join-Path $dir 'BUILD_IDENTITY.json') -Raw|ConvertFrom-Json
 if($m.source_commit -cne $commit -or $m.metadata_default_enabled -ne 0 -or $m.host_runtime_verified -ne 0 -or
    @($m.files.PSObject.Properties).Count -ne 12){throw 'PACKAGE_IDENTITY'}
 foreach($f in $m.files.PSObject.Properties){
  if($f.Name -notmatch '\A(?:diagnostics/|plugins/)?[A-Za-z0-9_.-]+\z' -or
     $f.Name -match '\.\.' -or (Get-FileHash -LiteralPath (Join-Path $dir $f.Name)).Hash -cne $f.Value){throw 'PACKAGE_HASH'}
 }
 foreach($f in Get-ChildItem -LiteralPath $dir -Recurse -Force -File){
  if($f.Name -match '(?i)settings\.json|camera_password\.dpapi|\.etl$|\.mp4$|\.mkv$|\.csv$|Recording_.*\.txt$'){throw 'PACKAGE_PRIVATE_DATA'}
 }
}
function Smoke([string]$dir,[string]$tag){
 $env:C545D_NATIVE_SMOKE_OUTPUT=Join-Path $root ($tag+'.txt')
 $env:C545D_SEI_AU_FILTER='off'
 $p=Start-Process -FilePath (Join-Path $dir 'C545D_Recorder.exe') -ArgumentList '--smoke' -WorkingDirectory $dir -PassThru
 try{
  if(-not $p.WaitForExit(15000) -or $p.ExitCode -ne 0 -or
     (Get-Content -LiteralPath $env:C545D_NATIVE_SMOKE_OUTPUT -Raw).Trim() -cne 'PASS NATIVE WINFORMS;SEI=off'){throw 'EXE_SMOKE'}
 }finally{if(-not $p.HasExited){$p.Kill();[void]$p.WaitForExit(5000)};$p.Dispose()}
}
function Verify-Settings([string]$dir){
 # Original settings reader under the same synthetic user/profile.
 . (Join-Path $dir 'CommonSettings.ps1')
 $s=Read-C545DSettings
 if($s.camera_ip -ne '127.0.0.1' -or $s.camera_user -ne 'synthetic' -or $s.output_folder -ne $output){throw 'SETTINGS_READ'}
 $sec=Read-C545DPassword
 $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
 try{if([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) -cne 'CI_SYNTHETIC_ONLY'){throw 'DPAPI_READ'}}
 finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr);$sec.Dispose()}
}
function Sample([string]$dir,[string]$tag,[int]$count){
 $observer=Join-Path $dir 'diagnostics\C545D-WeeklyObserver.ps1'
 $argsList=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$observer,
  '-RootDirectory',$store,'-RecorderLogDirectory',(Join-Path $root 'missing-logs'),
  '-MetadataJournalRoot',(Join-Path $root 'missing-journal'),'-WriterReceiptRoot',(Join-Path $root 'missing-receipts'))
 & $ps @argsList -Once | Out-Null
 if($LASTEXITCODE -ne 0){throw 'OBSERVER_SAMPLE'}
 $rows=@(Get-ChildItem -LiteralPath (Join-Path $store 'metrics') -Filter 'process_*.csv' -File|ForEach-Object{Import-Csv -LiteralPath $_.FullName})
 if($rows.Count -ne $count){throw 'OBSERVER_HISTORY'}
 & $ps @argsList -ExportNow | Out-Null
 if($LASTEXITCODE -ne 0){throw 'OBSERVER_EXPORT'}
 $reports=@(Get-ChildItem -LiteralPath (Join-Path $store 'reports') -Filter '*.zip' -File)
 if($reports.Count -ne $count){throw 'REPORT_HISTORY'}
 $latest=$reports|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
 $unpack=Join-Path $root ('report-'+$tag)
 Expand-Archive -LiteralPath $latest.FullName -DestinationPath $unpack
 $m=Get-Content -LiteralPath (Join-Path $unpack 'manifest.json') -Raw|ConvertFrom-Json
 if($m.actual_samples -ne $count -or $m.automatic_upload -ne $false){throw 'REPORT_COVERAGE'}
 $m.package_identity.source_commit
}
try{
 Expand-Checked $OldZip $oldDir '9278ec4b32f55618fca64f9609310648b2d39dda'
 Expand-Checked $NewZip $newDir '2dc4212131eb7a367564e260bcaf9d35dc6271bd'
 $oldTree=Get-Tree $oldDir;$newTree=Get-Tree $newDir
 $env:LOCALAPPDATA=$data
 Remove-Item Env:C545D_METADATA_V04,Env:C545D_METADATA_PROBE_SHA256 -ErrorAction SilentlyContinue
 $request=@{camera_ip='127.0.0.1';camera_user='synthetic';output_folder=$output;new_password='CI_SYNTHETIC_ONLY'}|ConvertTo-Json -Compress
 $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($request))
 $encoded|& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $oldDir 'C545D_SettingsBridge.ps1')|Out-Null
 if($LASTEXITCODE -ne 0){throw 'INITIAL_SETTINGS'}
 $cfg=Join-Path $data 'C545D_GStreamer'
 $settingsTree=Get-Tree $cfg
 [IO.File]::WriteAllText((Join-Path $output 'preserve.txt'),'SYNTHETIC_RECORDING_SENTINEL')
 $recordingTree=Get-Tree $output
 Smoke $oldDir 'old';Verify-Settings $oldDir
 if((Sample $oldDir 'old' 1) -cne '9278ec4b32f55618fca64f9609310648b2d39dda'){throw 'OLD_REPORT_IDENTITY'}
 $statePath=Join-Path $store 'observer_state.json'
 $initial=Get-Content -LiteralPath $statePath -Raw|ConvertFrom-Json
 $firstZip=Get-Tree (Join-Path $store 'reports')
 Smoke $newDir 'new';Verify-Settings $newDir
 if((Sample $newDir 'new' 2) -cne '2dc4212131eb7a367564e260bcaf9d35dc6271bd'){throw 'NEW_REPORT_IDENTITY'}
 Smoke $oldDir 'rollback';Verify-Settings $oldDir
 if((Sample $oldDir 'rollback' 3) -cne '9278ec4b32f55618fca64f9609310648b2d39dda'){throw 'ROLLBACK_REPORT_IDENTITY'}
 $last=Get-Content -LiteralPath $statePath -Raw|ConvertFrom-Json
 if($initial.started_utc -cne $last.started_utc -or $initial.next_cut_utc -cne $last.next_cut_utc){throw 'CADENCE_RESET'}
 $reports=Get-Tree (Join-Path $store 'reports')
 foreach($key in $firstZip.Keys){if($firstZip[$key] -cne $reports[$key]){throw 'PREVIOUS_REPORT_CHANGED'}}
 Assert-Tree $oldTree (Get-Tree $oldDir)
 Assert-Tree $newTree (Get-Tree $newDir)
 Assert-Tree $settingsTree (Get-Tree $cfg)
 Assert-Tree $recordingTree (Get-Tree $output)
 Write-Host 'C545D_SIDEBYSIDE_ROLLBACK_CI_PASS,exact_packages=2,smoke=3,settings_dpapi=3,history_rows=3,report_zips=3,cadence_preserved=1,package_hashes_unchanged=1,recording_sentinel_unchanged=1,real_camera=0,host_baseline=0,install_approved=0'
}finally{
 foreach($key in $prior.Keys){[Environment]::SetEnvironmentVariable($key,$prior[$key],'Process')}
 # Runner-owned fixture only; retain no raw user data or diagnostic archives.
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
