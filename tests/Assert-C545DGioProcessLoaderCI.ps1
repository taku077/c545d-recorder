#Requires -Version 5.1
<#
CI-only: prove the actual live gst-launch process loads app-local GIO.
No camera, credentials, registry mutation, recorder operation, or SDK edits.
PATH prefers the candidate in BOTH trials; only executable location changes.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SdkRoot,
  [Parameter(Mandatory=$true)][string]$CandidateDll,
  [Parameter(Mandatory=$true)][string]$WorkRoot
)
$ErrorActionPreference='Stop'
$official=Join-Path $SdkRoot 'bin\gio-2.0-0.dll'
$installedLauncher=Join-Path $SdkRoot 'bin\gst-launch-1.0.exe'
$installedInspector=Join-Path $SdkRoot 'bin\gst-inspect-1.0.exe'
$overlay=Join-Path $WorkRoot 'private-gst-bin'
$overlayLauncher=Join-Path $overlay 'gst-launch-1.0.exe'
$overlayGio=Join-Path $overlay 'gio-2.0-0.dll'
$registry=Join-Path $WorkRoot 'registry-cache.bin'
$scanner=Join-Path $SdkRoot 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
$originalPath=$env:PATH
$oldRegistry=$env:GST_REGISTRY
$oldScanner=$env:GST_PLUGIN_SCANNER
$oldPluginPath=$env:GST_PLUGIN_SYSTEM_PATH_1_0
$running=$null
$officialHash='A875107C180FB248236D1E96E14F362F117124DF2FEE1237FA2142B7B363941B'
$candidateHash='67B9F7246E4744FEF7EE1EAD3BED4CE2179C6F0465EC68A92D01DD12B4A3CCAD'
function Assert-Hash([string]$file,[string]$sha,[string]$what) {
  if(-not (Test-Path -LiteralPath $file -PathType Leaf) -or
     (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $sha){
     throw "C545D_GIO_LOADER_CI_INVALID_HASH=$what"
  }
}
function Invoke-IsolatedProbe([string]$label,[string]$exe,[string]$expectedModule) {
  $output=Join-Path $WorkRoot ($label+'.wav')
  $uri=([Uri]::new([IO.Path]::GetFullPath($output))).AbsoluteUri
  $stdout=Join-Path $WorkRoot ($label+'.stdout')
  $stderr=Join-Path $WorkRoot ($label+'.stderr')
  $arguments=@('-e','-q','audiotestsrc','is-live=true','num-buffers=460','wave=sine',
    '!','audioconvert','!','audio/x-raw,format=S16LE,rate=48000,channels=1','!','wavenc','!','giosink',("location="+$uri))
  $script:running=Start-Process -FilePath $exe -ArgumentList $arguments -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WorkingDirectory $WorkRoot
  $observed=$false
  $pollErrors=0
  $pollCount=0
  $maxSeenModules=0
  try {
    # Plug-in loader initialization on Windows hosted runners can require
    # more than 10 seconds (particularly when the optional Python plug-in
    # fails discovery). Observe the live *actual process*, not a timeout guess.
    for($n=0;$n -lt 260;$n++){
      $pollCount=$n+1
      Start-Sleep -Milliseconds 100
      try {
        $live=Get-Process -Id $script:running.Id -ErrorAction Stop
        $allModules=@($live.Modules)
        if($allModules.Count -gt $maxSeenModules){$maxSeenModules=$allModules.Count}
        $matches=@($allModules | Where-Object {$_.ModuleName -ieq 'gio-2.0-0.dll'})
        if($matches.Count -gt 1){throw 'Unexpected duplicate GIO modules'}
        if($matches.Count -eq 1){
          $actual=[IO.Path]::GetFullPath($matches[0].FileName).TrimEnd('\')
          $expected=[IO.Path]::GetFullPath($expectedModule).TrimEnd('\')
          if(-not [string]::Equals($actual,$expected,[StringComparison]::OrdinalIgnoreCase)){
            throw "C545D_GIO_LOADER_CI_WRONG_DLL=$label"
          }
          $observed=$true
          break
        }
      } catch [System.InvalidOperationException] {
        $pollErrors++
      } catch [System.ComponentModel.Win32Exception] {
        $pollErrors++
      }
      if($script:running.HasExited){break}
    }
    if(-not $observed){
      $exited=[int]$script:running.HasExited
      $code=if($exited){$script:running.ExitCode}else{-999}
      $bytes=if(Test-Path -LiteralPath $output){(Get-Item -LiteralPath $output).Length}else{0}
      $rawError=if(Test-Path -LiteralPath $stderr){Get-Content -LiteralPath $stderr -Raw}else{''}
      $noElement=[int]($rawError -match '(?i)no element.*giosink|no such element.*giosink')
      $negotiation=[int]($rawError -match '(?i)not-negotiated|could not link|error from element')
      # Only fixed numeric fields appear in CI; raw stderr/paths never uploaded.
      throw "C545D_GIO_LOADER_CI_NOT_OBSERVED,mode=$label,polls=$pollCount,exited=$exited,exit_code=$code,max_modules=$maxSeenModules,output_bytes=$bytes,missing_giosink=$noElement,negotiation_or_element_error=$negotiation,poll_errors=$pollErrors"
    }
    if(-not $script:running.WaitForExit(30000)){throw "C545D_GIO_LOADER_CI_PROCESS_TIMEOUT=$label"}
    if($script:running.ExitCode -ne 0){
      $text=if(Test-Path -LiteralPath $stderr){Get-Content -LiteralPath $stderr -Raw}else{''}
      $wavSize=if(Test-Path -LiteralPath $output){(Get-Item -LiteralPath $output).Length}else{0}
      $missingElement=[int]($text -match '(?i)no element|no such element')
      $capsError=[int]($text -match '(?i)not-negotiated|could not link|no common format')
      $gioIOError=[int]($text -match '(?i)giosink|GIO.*error|could not open|no such file|error opening file|file exists')
      $scannerWarning=[int]($text -match '(?i)gstpython.dll')
      $exitCode=$script:running.ExitCode
      throw "C545D_GIO_LOADER_CI_PIPELINE_FAILURE,mode=$label,exit_code=$exitCode,wav_bytes=$wavSize,missing_element=$missingElement,caps_error=$capsError,gio_io_error=$gioIOError,optional_gstpython_warning=$scannerWarning,loaded_gio_verified=1"
    }
    if((Get-Item -LiteralPath $output).Length -lt 30000){
      throw "C545D_GIO_LOADER_CI_WAV_MISSING=$label"
    }
    Write-Output "C545D_GIO_LOADER_OBSERVATION,mode=$label,module_expected=1,output_valid=1,process_exit=0,CI_only=1"
  } finally {
    if($script:running){
      if(-not $script:running.HasExited){
        # Only a disposable CI audio-test process is terminated on test failure.
        try{$script:running.Kill()}catch{}
        try{[void]$script:running.WaitForExit(3000)}catch{}
      }
      $script:running.Dispose()
      $script:running=$null
    }
  }
}
try {
  Assert-Hash $official $officialHash 'official'
  Assert-Hash $CandidateDll $candidateHash 'candidate'
  if(-not (Test-Path -LiteralPath $installedLauncher) -or
     -not (Test-Path -LiteralPath $installedInspector) -or
     -not (Test-Path -LiteralPath $scanner)){
    throw 'C545D_GIO_LOADER_CI_INCOMPLETE_GSTREAMER_SDK'
  }
  New-Item -ItemType Directory -Path $overlay -Force | Out-Null
  Copy-Item -LiteralPath $CandidateDll -Destination $overlayGio
  Copy-Item -LiteralPath $installedLauncher -Destination $overlayLauncher
  Copy-Item -LiteralPath $installedInspector -Destination (Join-Path $overlay 'gst-inspect-1.0.exe')
  Assert-Hash $overlayGio $candidateHash 'private-copy'
  $env:PATH="$overlay;$(Join-Path $SdkRoot 'bin');$originalPath"
  $env:GST_PLUGIN_SCANNER=$scanner
  $env:GST_PLUGIN_SYSTEM_PATH_1_0=Join-Path $SdkRoot 'lib\gstreamer-1.0'
  $env:GST_REGISTRY=$registry
  # Do not run gst-inspect in Windows PowerShell 5.1 with
  # ErrorActionPreference=Stop: the *optional* SDK gstpython.dll scanner
  # warning is treated as NativeCommandError even when inspection succeeds.
  # The actual giosink pipeline plus live-process loaded-DLL verification
  # below are stricter, and child stderr is kept within disposable CI files.
  # 1. The ORIGINAL installed exe still loads the SDK's GIO although
  #    candidate overlay is first in PATH.
  Invoke-IsolatedProbe 'installed' $installedLauncher $official
  # 2. Copying only the same exe to an app-local directory changes the
  #    actual loaded GIO to the candidate, with identical PATH.
  Invoke-IsolatedProbe 'isolated' $overlayLauncher $overlayGio
  Assert-Hash $official $officialHash 'official_after'
  Assert-Hash $CandidateDll $candidateHash 'candidate_after'
  Assert-Hash $overlayGio $candidateHash 'private_after'
  Write-Output 'C545D_GIO_REAL_PROCESS_LOADER_CI_PASS,installed_exe_uses_official=1,PATH_override_did_not_bypass_app_dir=1,isolated_exe_uses_candidate=1,live_module_path_confirmed=1,original_sdk_unchanged=1,synthetic_GIO_audio_write=1,recorder_host_modified=0'
} finally {
  $env:PATH=$originalPath
  $env:GST_REGISTRY=$oldRegistry
  $env:GST_PLUGIN_SCANNER=$oldScanner
  $env:GST_PLUGIN_SYSTEM_PATH_1_0=$oldPluginPath
}
