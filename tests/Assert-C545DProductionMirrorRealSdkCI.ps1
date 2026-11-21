#Requires -Version 5.1
<#
CI ONLY: bind a byte-equivalent production Record.ps1 mirror to the REAL
official GStreamer SDK and pinned private GIO. The mirrored Record.ps1 is
NEVER invoked: only camera-free WAV and dual synthetic RTP H264/AAC MP4 tests.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$CandidateManifest,
  [Parameter(Mandatory=$true)][string]$ReferenceManifest
)
$ErrorActionPreference='Stop'
$candidateSha='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
$officialSha='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
$pin=@{
  'gio-2.0-0.dll'='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
  'glib-2.0-0.dll'='CAF29CFC1467E3A3E5E91F0F649BD7A501107D9B3C32A2866B08E2ECFA209E3E'
  'gobject-2.0-0.dll'='811DAB4B420E520D91AC3FE5202975CC90CAF2C53EF2F8F0FCE8F8588A735C7A'
  'gmodule-2.0-0.dll'='86BE81A7011EC07E1992CE7A742AD881A80AE38583BBCFFBF973498D4748DAC5'
  'intl-8.dll'='2EF6A23F712FD7B9BF72B2FEF1A1FD5CDE27BA88F7D164E9E6DE18936C1F51B0'
  'z-1.dll'='B84851F9084247F466C076EE993BD5A92F3462466C4877B5C4ECC4125743A060'
}
$stage=$null; $owned=$false; $child=$null; $removed=$false
$observed=$false; $wavOk=$false; $mediaOk=$false; $preStopOk=$false; $segments=0; $prior=@{}
try {
  if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows' -or
     -not $env:RUNNER_TEMP){throw 'NOT_CI'}
  $temp=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $tempItem=Get-Item -LiteralPath $temp -Force
  if(-not $tempItem.PSIsContainer -or
     ($tempItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'UNSAFE_TEMP'}
  $sdkBin=Join-Path $SdkRoot 'bin'
  $ref=Get-Content -LiteralPath $ReferenceManifest -Raw | ConvertFrom-Json
  if($ref.schema -ne 1 -or $ref.install_approved -ne $false -or
     $ref.sdk -cne 'gstreamer-1.0-msvc-x86_64-1.28.8' -or
     ([string]$ref.candidate_sha256).ToUpperInvariant() -cne $candidateSha -or
     @($ref.dll_sha256.PSObject.Properties.Name).Count -ne 6){throw 'BAD_REFERENCE'}
  foreach($key in $pin.Keys){
    if(([string]$ref.dll_sha256.PSObject.Properties[$key].Value).ToUpperInvariant() -cne $pin[$key] -or
       (Get-FileHash -LiteralPath (Join-Path $sdkBin $key) -Algorithm SHA256).Hash -cne $pin[$key]){
      throw 'SDK_NOT_PINNED'
    }
  }
  if((Get-FileHash -LiteralPath $CandidateDll -Algorithm SHA256).Hash -cne $candidateSha){
    throw 'CANDIDATE_DIFFERENT'
  }
  $m=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $CandidateManifest).Path)
  if($m -notmatch ('(?m)^CANDIDATE_GIO_SHA256='+$candidateSha+'\r?$') -or
     $m -notmatch ('(?m)^REFERENCE_GIO_SHA256='+$officialSha+'\r?$') -or
     $m -notmatch '(?m)^C545D_RELEASE_CANDIDATE_STATUS=CI_TEST_ONLY_NOT_APPROVED_FOR_HOST\r?$'){
    throw 'CANDIDATE_MANIFEST_NOT_PINNED'
  }
  $scanner=Join-Path $SdkRoot 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
  $plugins=Join-Path $SdkRoot 'lib\gstreamer-1.0'
  if(-not (Test-Path -LiteralPath $scanner -PathType Leaf) -or
     -not (Test-Path -LiteralPath $plugins -PathType Container)){
    throw 'SDK_INCOMPLETE'
  }
  $stage=Join-Path $temp ('c545d-ci-production-mirror-'+[guid]::NewGuid().ToString('N'))
  if(Test-Path -LiteralPath $stage){throw 'STAGE_EXISTS'}
  New-Item -ItemType Directory -Path $stage | Out-Null
  [IO.File]::WriteAllText((Join-Path $stage '.c545d-ci-owned'),'CI_MIRROR_ONLY_NOT_FOR_EXECUTION')
  $owned=$true
  $bin=Join-Path $stage 'bin'
  New-Item -ItemType Directory -Path $bin | Out-Null
  foreach($exe in @('gst-launch-1.0.exe','gst-inspect-1.0.exe','gst-discoverer-1.0.exe')){
    $original=Join-Path $sdkBin $exe
    Copy-Item -LiteralPath $original -Destination (Join-Path $bin $exe)
    if((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -cne
       (Get-FileHash -LiteralPath (Join-Path $bin $exe) -Algorithm SHA256).Hash){
      throw 'EXECUTABLE_COPY_CHANGED'
    }
  }
  Copy-Item -LiteralPath $CandidateDll -Destination (Join-Path $bin 'gio-2.0-0.dll')
  if((Get-FileHash -LiteralPath (Join-Path $bin 'gio-2.0-0.dll') -Algorithm SHA256).Hash -cne $candidateSha){
    throw 'PRIVATE_CANDIDATE_CHANGED'
  }
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $source=(Resolve-Path -LiteralPath 'Record.ps1').Path
  $settings=(Resolve-Path -LiteralPath 'CommonSettings.ps1').Path
  $sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
  $settingsHash=(Get-FileHash -LiteralPath $settings -Algorithm SHA256).Hash
  $rows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File 'tools/New-C545DIsolatedProductionMirrorCI.ps1' -RecordSource $source -SettingsSource $settings -StageRoot $stage)
  if($LASTEXITCODE -ne 0 -or $rows.Count -ne 1 -or
     $rows[0] -cne 'C545D_PRODUCTION_MIRROR,rendered=1,exact_one_statement=1,source_syntax=1,candidate_pinned=1,host_executed=0,rtsp_contacted=0,install_approved=0,live_tapo_authorized=0,reason=CI_ONLY_MIRROR_PASS'){
    throw 'SOURCE_MIRROR_REFUSED'
  }
  $rows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File 'tools/New-C545DPrivateOutputSettingsMirrorCI.ps1' -StageRoot $stage -OriginalSettingsSource $settings)
  if($LASTEXITCODE -ne 0 -or $rows.Count -ne 1 -or
     $rows[0] -cne 'C545D_PRIVATE_OUTPUT_MIRROR,patched=1,single_assignment=1,source_syntax=1,private_only=1,host_executed=0,rtsp_contacted=0,install_approved=0,live_tapo_authorized=0,reason=CI_PRIVATE_OUTPUT_MIRROR_PASS'){
    throw 'OUTPUT_MIRROR_REFUSED'
  }
  $originalText=[IO.File]::ReadAllText($source)
  $expectedSource=$originalText.Replace('$bin = Find-GstBin',
    ('$bin = [IO.Path]::GetFullPath('''+$bin.Replace("'","''")+''')'))
  if([IO.File]::ReadAllText((Join-Path $stage 'Record.ps1')) -cne $expectedSource){
    throw 'SOURCE_PARITY_CHANGED'
  }
  foreach($key in @('PATH','LOCALAPPDATA','GST_PLUGIN_SCANNER','GST_REGISTRY','GST_PLUGIN_PATH',
      'GST_PLUGIN_PATH_1_0','GST_PLUGIN_SYSTEM_PATH','GST_PLUGIN_SYSTEM_PATH_1_0')){
    $prior[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
  }
  $env:PATH="$bin;$sdkBin;$($prior['PATH'])"
  $env:GST_PLUGIN_SCANNER=$scanner
  $env:GST_REGISTRY=Join-Path $stage 'private-registry.bin'
  $env:GST_PLUGIN_PATH=''
  $env:GST_PLUGIN_PATH_1_0=''
  $env:GST_PLUGIN_SYSTEM_PATH=''
  $env:GST_PLUGIN_SYSTEM_PATH_1_0=$plugins
  $wav=Join-Path $stage 'private-output\synthetic.wav'
  $uri=([Uri]::new([IO.Path]::GetFullPath($wav))).AbsoluteUri
  $args=@('-e','-q','audiotestsrc','is-live=true','num-buffers=500','!',
          'audioconvert','!','audio/x-raw,format=S16LE,rate=48000,channels=1',
          '!','wavenc','!','giosink',('location='+$uri))
  $child=Start-Process -FilePath (Join-Path $bin 'gst-launch-1.0.exe') -ArgumentList $args -PassThru -WorkingDirectory $stage -RedirectStandardOutput (Join-Path $stage 'test.stdout') -RedirectStandardError (Join-Path $stage 'test.stderr')
  for($i=0;$i -lt 260;$i++){
    Start-Sleep -Milliseconds 100
    try {
      $modules=@((Get-Process -Id $child.Id -ErrorAction Stop).Modules | Where-Object {$_.ModuleName -ieq 'gio-2.0-0.dll'})
      if($modules.Count -eq 1){
        $actual=[IO.Path]::GetFullPath($modules[0].FileName)
        $want=[IO.Path]::GetFullPath((Join-Path $bin 'gio-2.0-0.dll'))
        if(-not [string]::Equals($actual,$want,[StringComparison]::OrdinalIgnoreCase)){
          throw 'WRONG_GIO_MODULE'
        }
        $observed=$true
        break
      }
    } catch [System.InvalidOperationException] {} catch [System.ComponentModel.Win32Exception] {}
    if($child.HasExited){break}
  }
  if(-not $observed){throw 'MODULE_NOT_OBSERVED'}
  if(-not $child.WaitForExit(30000)){throw 'WAV_CHILD_TIMEOUT'}
  if($child.ExitCode -ne 0){throw 'WAV_CHILD_FAILED'}
  $child.Dispose();$child=$null
  if(-not (Test-Path -LiteralPath $wav -PathType Leaf) -or
     (Get-Item -LiteralPath $wav).Length -lt 30000){throw 'WAV_INVALID'}
  $wavOk=$true
  $media=@(& 'tests/Assert-GStreamerOverlaySplitMux.ps1' -SdkRoot $SdkRoot -OverlayDir $bin -Prefix 'ci_exactmirror_media')
  if($LASTEXITCODE -ne 0){throw 'SYNTHETIC_MEDIA_EXEC_FAILED'}
  $summary=@($media | Where-Object {$_ -match '^C545D_SPLITMUX_MSVC_GIO_PASS segments=\d+'})
  if($summary.Count -ne 1 -or
     $summary[0] -notmatch 'all_segments_av_decodable=true' -or
     $summary[0] -notmatch 'two_RTP_H264_decoders=avdec_h264' -or
     $summary[0] -notmatch 'output=2560x720@15fps'){
    throw 'MEDIA_SUMMARY_MISSING'
  }
  $segments=[int]([regex]::Match($summary[0],'segments=(\d+)').Groups[1].Value)
  if($segments -lt 2 -or $segments -gt 8){throw 'SEGMENTS_OUT_OF_RANGE'}
  $left=@(Get-ChildItem -LiteralPath 'artifacts' -Filter 'ci_exactmirror_media_*.mp4' -File -ErrorAction SilentlyContinue)
  if($left.Count -ne 0){throw 'SYNTHETIC_MP4_NOT_REMOVED'}
  foreach($check in @(
    @($source,$sourceHash),@($settings,$settingsHash),
    @((Join-Path $sdkBin 'gio-2.0-0.dll'),$officialSha),@($CandidateDll,$candidateSha))){
    if((Get-FileHash -LiteralPath $check[0] -Algorithm SHA256).Hash -cne $check[1]){
      throw 'ORIGINAL_BYTES_CHANGED'
    }
  }
  $mediaOk=$true
  # Execute the actual single-assignment mirrored production source, but
  # with a pre-existing managed stop marker. This permits source startup,
  # decoder/AAC preflights, and pipeline construction; NO RTSP launch.
  # Only disposable CI-local fake config and dummy DPAPI secret are read.
  $fixtureLocalAppData=Join-Path $stage 'ci-dummy-localappdata'
  $configDir=Join-Path $fixtureLocalAppData 'C545D_GStreamer'
  New-Item -ItemType Directory -Path $configDir -Force | Out-Null
  $dummySettings=@{
    camera_ip='127.0.0.1'
    camera_user='ci_fixture_not_real'
    output_folder='C:\NONEXISTENT_NOT_USED'
  }
  $dummySettings | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $configDir 'settings.json') -Encoding utf8
  # The exact production recorder executes in Windows PowerShell 5.1.
  # Generate the fake DPAPI payload in that SAME PS5.1 user/runtime, never
  # using PowerShell7's independently versioned secure-string serialization.
  # This local CI script carries no user secret, only an inert public dummy.
  $dummyPwScript=Join-Path $stage 'ci-generate-dummy-dpapi.ps1'
  $dummyPwCode=@(
    'param([string]$OutFile)',
    '$dummy=ConvertTo-SecureString ''dummy_ci_only_password_not_real'' -AsPlainText -Force',
    'ConvertFrom-SecureString $dummy | Set-Content -LiteralPath $OutFile -Encoding ASCII'
  )
  [IO.File]::WriteAllText($dummyPwScript,($dummyPwCode -join [Environment]::NewLine))
  $dummyPwFile=Join-Path $configDir 'camera_password.dpapi'
  & $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $dummyPwScript -OutFile $dummyPwFile
  if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $dummyPwFile -PathType Leaf)){
    throw 'CI_DUMMY_DPAPI_GENERATION_FAILED'
  }
  $env:LOCALAPPDATA=$fixtureLocalAppData
  $stop=Join-Path $stage 'ci-preexisting-stop.marker'
  [IO.File]::WriteAllText($stop,'NO_RTSP_ALLOWED_FOR_PRESTOP_TEST')
  $recorder=Join-Path $stage 'Record.ps1'
  $cmdArgs=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
       ('"'+$recorder+'"'),'-StopFile',('"'+$stop+'"'))
  # GitHub-hosted Windows DPAPI was confirmed to decrypt correctly when
  # Windows PowerShell 5.1 is invoked directly as a native command; both
  # Start-Process and managed ProcessStartInfo reported a different DPAPI
  # result for the same CI dummy. Use the proved direct mode with stdout
  # captured privately, an existing STOP marker, loopback-only config and
  # the GitHub Actions job timeout as the outer kill boundary. Never used
  # for an actual camera or user machine.
  $preStopErr=Join-Path $stage 'prestop.stderr'
  $preStopOut=Join-Path $stage 'prestop.stdout'
  $preStopRows=@(& $ps -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $recorder -StopFile $stop 2> $preStopErr)
  $nativeExit=$LASTEXITCODE
  $stopOutput=($preStopRows -join [Environment]::NewLine)
  [IO.File]::WriteAllText($preStopOut,$stopOutput)
  if($nativeExit -ne 0){
    # Only fixed sanitized booleans, never full stdout/stderr or URLs.
    $errText=[IO.File]::ReadAllText((Join-Path $stage 'prestop.stderr'))
    $badSettings=[int]($errText -match 'settings do not exist|Saved settings are incomplete|Saved camera IP address is invalid')
    $badDpapi=[int]($errText -match 'Cannot decrypt saved password|Saved password is missing')
    $badElements=[int]($errText -match 'Missing GStreamer elements|GStreamer MSVC x64 Runtime was not found')
    $badDecoder=[int]($errText -match 'No H.264 decoder passed')
    $badAac=[int]($errText -match 'No high-quality AAC encoder passed')
    $graphObserved=[int]$stopOutput.Contains('GStreamer separator validation: PASS')
    $stopObserved=[int]$stopOutput.Contains('Stop requested; skipping any new RTSP session.')
    Write-Output "C545D_PRESTOP_FAILURE_DIAG,native_nonzero=1,direct_native_invocation=1,settings_error=$badSettings,dpapi_error=$badDpapi,element_error=$badElements,decoder_error=$badDecoder,aac_error=$badAac,graph_observed=$graphObserved,stop_observed=$stopObserved"
    throw 'RECORDER_PRESTOP_FAILURE'
  }
  if(-not $stopOutput.Contains('GStreamer separator validation: PASS') -or
     -not $stopOutput.Contains('Stop requested; skipping any new RTSP session.') -or
     $stopOutput.Contains('GStreamer launching (EOS enabled)')){
    throw 'RECORDER_PRESTOP_INVARIANT_FAILED'
  }
  if(@(Get-ChildItem -LiteralPath (Join-Path $stage 'private-output') -Filter '*.mp4' -File).Count -ne 0){
    throw 'RECORDER_PRESTOP_WRITTEN_MP4'
  }
  foreach($check in @(@($source,$sourceHash),@($settings,$settingsHash))){
    if((Get-FileHash -LiteralPath $check[0] -Algorithm SHA256).Hash -cne $check[1]){
      throw 'PRESTOP_MUTATED_PRODUCTION_SOURCE'
    }
  }
  $preStopOk=$true
} finally {
  if($child){
    if(-not $child.HasExited){try{$child.Kill();[void]$child.WaitForExit(5000)}catch{}}
    $child.Dispose()
  }
  foreach($key in $prior.Keys){
    [Environment]::SetEnvironmentVariable($key,$prior[$key],'Process')
  }
  if($owned -and $stage){
    $item=Get-Item -LiteralPath $stage -Force
    $parent=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($stage)).TrimEnd('\')
    $linked=@(Get-ChildItem -LiteralPath $stage -Recurse -Force -ErrorAction Stop | Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if($item.PSIsContainer -and
       ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and
       $linked.Count -eq 0 -and
       [string]::Equals($parent,$temp,[StringComparison]::OrdinalIgnoreCase) -and
       [IO.Path]::GetFileName($stage) -match '^c545d-ci-production-mirror-[a-f0-9]{32}$' -and
       [IO.File]::ReadAllText((Join-Path $stage '.c545d-ci-owned')) -ceq 'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){
      Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction Stop
      $removed=-not (Test-Path -LiteralPath $stage)
    }
  }
}
if(-not $observed -or -not $wavOk -or -not $mediaOk -or -not $preStopOk -or -not $removed){
  throw 'INTEGRATED_CI_NOT_QUALIFIED'
}
Write-Output "C545D_PRODUCTION_MIRROR_REAL_SDK_CI_PASS,source_mirror=1,private_settings_output=1,official_sdk_pinned=1,real_private_exe=1,real_candidate_gio_loaded=1,giosink_wav=1,synthetic_dual_rtp_h264_aac=1,segments=$segments,mp4_decode=1,eos=1,originals_unchanged=1,owned_rollback=1,recorder_prestop_preflight=1,real_tapo_tested=0,real_hourly_split_tested=0,install_approved=0"
