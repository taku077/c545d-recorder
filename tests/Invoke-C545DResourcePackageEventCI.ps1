#Requires -Version 5.1
<#
CI ONLY. Signed disposable resource-package add/remove to test true
PackageCatalog callbacks while the parent main package FullName stays fixed.
No camera, production DLL, or user's registry/system is touched.
#>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$WatchDll,
      [Parameter(Mandatory=$true)][string]$StubExe,
      [string]$GioScanDll='',
      [switch]$AssertLocalizedDisplayName,
      [switch]$ReverseResourceLanguage,
      [string]$LocalizedProbeExe='')
$ErrorActionPreference='Stop'
if($ReverseResourceLanguage -and (-not $AssertLocalizedDisplayName)) {
  throw 'C545D_RESOURCE_REVERSE_MODE_REQUIRES_LOCALIZED_VALUE_ASSERTION'
}
if($AssertLocalizedDisplayName -and (-not $LocalizedProbeExe -or -not(Test-Path -LiteralPath $LocalizedProbeExe))){
  throw 'C545D_RESOURCE_LOCALIZED_TEST_REQUIRES_NATIVE_DISPLAY_PROBE'
}
$name='C545D.CI.PackageEvents'
$root=Join-Path $env:RUNNER_TEMP ('c545d_resource_'+[guid]::NewGuid().ToString('N'))
$secret=[guid]::NewGuid().ToString('N')
$watch=[IntPtr]::Zero
$entered=$false
$cert=$null
$installedParent=$null
$resourceFullName=$null
$gioStarted=$false
New-Item -ItemType Directory -Path $root -Force | Out-Null
function Tool([string]$exe) {
  $base=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Windows Kits\10\bin'
  $all=@(Get-ChildItem $base -Recurse -File -Filter $exe -ErrorAction SilentlyContinue |
         Where-Object {$_.DirectoryName -match '[\\/]x64$'} | Sort-Object FullName)
  if(!$all.Count){throw "C545D_RESOURCE_CI_MISSING_TOOL=$exe"}
  return $all[-1].FullName
}
function Checked([string]$stage) {
  if($LASTEXITCODE -ne 0){throw "C545D_RESOURCE_CI_FAILURE=$stage,exit=$LASTEXITCODE"}
}
function Epoch {
  for($i=0;$i -lt 40;$i++) {
    [UInt64]$g=0;[UInt64]$locale=0
    $ret=[C545DResourceWatch]::Snapshot($script:watch,[ref]$g,[ref]$locale)
    if($ret -eq 0){return $g}
    if($ret -ne 5){throw "C545D_RESOURCE_CI_SNAPSHOT_FAILURE=$ret"}
    Start-Sleep -Milliseconds 50
  }
  throw 'C545D_RESOURCE_CI_SNAPSHOT_TIMEOUT'
}
function Await([UInt64]$before) {
  for($i=0;$i -lt 80;$i++){
    [UInt64]$value=Epoch
    if($value -gt $before){return $value}
    Start-Sleep -Milliseconds 50
  }
  return $before
}
function Status {
  [UInt64]$events=0
  $ret=[C545DResourceWatch]::StatusCount($script:watch,[ref]$events)
  if($ret -ne 0){throw "C545D_RESOURCE_CI_STATUS_FAILED=$ret"}
  return $events
}
function Completion {
  [UInt64]$inst=0;[UInt64]$upd=0;[UInt64]$uninst=0
  $ret=[C545DResourceWatch]::Completion($script:watch,[ref]$inst,[ref]$upd,[ref]$uninst)
  if($ret -ne 0){throw "C545D_RESOURCE_CI_COMPLETION_FAILED=$ret"}
  return @{inst=$inst;upd=$upd;uninst=$uninst}
}
try {
  if(@(Get-AppxPackage -Name $name -ErrorAction Stop).Count){
    throw 'C545D_RESOURCE_CI_PREEXISTING_TEST_IDENTITY'
  }
  $make=Tool 'MakeAppx.exe'
  $sign=Tool 'SignTool.exe'
  $cert=New-SelfSignedCertificate -Type Custom -KeyUsage DigitalSignature -Subject 'CN=C545D CI Event Probe' -CertStoreLocation 'Cert:\CurrentUser\My' -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3') -KeyExportPolicy Exportable -HashAlgorithm SHA256
  $pfx=Join-Path $root 'temporary.pfx'
  $cer=Join-Path $root 'temporary.cer'
  Export-PfxCertificate -Cert $cert -FilePath $pfx -Password (ConvertTo-SecureString $secret -AsPlainText -Force) | Out-Null
  Export-Certificate -Cert $cert -FilePath $cer | Out-Null
  Import-Certificate -FilePath $cer -CertStoreLocation 'Cert:\CurrentUser\TrustedPeople' | Out-Null
  Import-Certificate -FilePath $cer -CertStoreLocation 'Cert:\LocalMachine\TrustedPeople' | Out-Null
  Import-Certificate -FilePath $cer -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
  $mainDir=Join-Path $root 'main'
  $resDir=Join-Path $root 'resource'
  $mainMsix=Join-Path $root 'main.msix'
  $resMsix=Join-Path $root 'resource.msix'
  $mainArgs=@('tests/make_c545d_ci_package_fixture.py','--out',$mainDir,'--stub',$StubExe,'--version','1.0.0.0')
  if($AssertLocalizedDisplayName){$mainArgs+='--localized-display-name'}
  if($ReverseResourceLanguage){$mainArgs+=@('--base-language','fr-fr')}
  & py @mainArgs
  Checked 'main_fixture'
  $resLanguage=if($ReverseResourceLanguage){'en-us'}else{'fr-fr'}
  $baseLanguage=if($ReverseResourceLanguage){'fr-fr'}else{'en-us'}
  $resourceId=if($ReverseResourceLanguage){'English'}else{'French'}
  $resourceArgs=@('tests/make_c545d_ci_resource_package_fixture.py',
                  '--out',$resDir,'--main-layout',$mainDir,'--resource-language',$resLanguage)
  & py @resourceArgs
  Checked 'resource_fixture'
  # Windows requires a valid base PRI before merging a resource pack PRI.
  # Create the same key in the parent base PRI and in the reverse-language resource PRI.
  $pri=Tool 'MakePri.exe'
  $strings=Join-Path $mainDir ('Strings\'+$baseLanguage)
  New-Item -ItemType Directory -Force -Path $strings | Out-Null
  @'
<?xml version="1.0" encoding="utf-8"?>
<root>
  <data name="C545DResourceProbe" xml:space="preserve">
    <value>__BASE_VALUE__ synthetic resource value</value>
  </data>
</root>
'@.Replace('__BASE_VALUE__',$(if($ReverseResourceLanguage){'French'}else{'English'})) | Set-Content -LiteralPath (Join-Path $strings 'Resources.resw') -Encoding utf8
  $mainCfg=Join-Path $mainDir 'priconfig.xml'
  $resCfg=Join-Path $resDir 'priconfig.xml'
  $mainPri=Join-Path $mainDir 'resources.pri'
  $resPri=Join-Path $resDir 'resources.pri'
  & $pri createconfig /cf $mainCfg /dq $baseLanguage /o
  Checked 'main_pri_config'
  & $pri new /pr $mainDir /cf $mainCfg /mn (Join-Path $mainDir 'AppxManifest.xml') /of $mainPri /o
  Checked 'main_pri_index'
  & $pri createconfig /cf $resCfg /dq $resLanguage /o
  Checked 'resource_pri_config'
  # ResourcePack may only index additional variants of names already in
  # the parent PRI. Keep unrelated PNG/TXT payload out of MakePri's input,
  # although MakeAppx will still package them from the mapping separately.
  $indexOnly=Join-Path $root ($resLanguage+'-index-only')
  $indexStrings=Join-Path $indexOnly ('Strings\'+$resLanguage)
  New-Item -ItemType Directory -Path $indexStrings -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $resDir ('Strings\'+$resLanguage+'\Resources.resw')) -Destination $indexStrings
  & $pri resourcepack /pr $indexOnly /cf $resCfg /if $mainPri /of $resPri /o
  Checked 'resource_pri_index'
  if(-not (Test-Path $mainPri) -or -not (Test-Path $resPri)){
    throw 'C545D_RESOURCE_CI_PRI_OUTPUT_MISSING'
  }
  & $make pack /o /d $mainDir /p $mainMsix *> $null
  Checked 'main_pack'
  Push-Location $resDir
  try {
    & $make pack /o /r /m (Join-Path $mainDir 'AppxManifest.xml') /f (Join-Path $resDir 'mapping.txt') /p $resMsix
    Checked 'resource_pack'
  } finally {Pop-Location}
  & $sign sign /fd SHA256 /f $pfx /p $secret $mainMsix *> $null
  Checked 'main_sign'
  & $sign sign /fd SHA256 /f $pfx /p $secret $resMsix *> $null
  Checked 'resource_sign'
  $native=@'
using System;
using System.Runtime.InteropServices;
public static class C545DResourceWatch {
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_runtime_enter",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Enter();
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_runtime_leave",CallingConvention=CallingConvention.Cdecl)]
  public static extern void Leave();
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_open",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Open(out IntPtr watch);
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_close",CallingConvention=CallingConvention.Cdecl)]
  public static extern void Close(IntPtr watch);
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_snapshot",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Snapshot(IntPtr watch,out UInt64 gen,out UInt64 locale);
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_ci_status_event_count",CallingConvention=CallingConvention.Cdecl)]
  public static extern int StatusCount(IntPtr watch,out UInt64 count);
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_ci_completion_counters",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Completion(IntPtr watch,out UInt64 inst,out UInt64 upd,out UInt64 uninst);
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_global_counters",CallingConvention=CallingConvention.Cdecl)]
  public static extern void Counters(out UInt64 registered,out UInt64 revoked,out UInt64 errors);
}
'@
  Add-Type -TypeDefinition $native.Replace('__DLL__',$WatchDll.Replace('"','""'))
  # Filter both independent native watchers (this one and GIO's) before
  # GIO initializes its own PackageCatalog subscriptions.
  $env:C545D_CI_EVENT_PACKAGE_NAME=$name
  if($GioScanDll) {
    $gionative=@'
using System;
using System.Runtime.InteropServices;
public static class C545DResourceGio {
  [DllImport(@"__DLL__",EntryPoint="c545d_ci_scan_real_msix_stage",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Scan(int stage);
  [DllImport(@"__DLL__",EntryPoint="c545d_ci_monitor_start",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Start();
  [DllImport(@"__DLL__",EntryPoint="c545d_ci_monitor_observe",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Observe(int stage);
  [DllImport(@"__DLL__",EntryPoint="c545d_ci_monitor_stop",CallingConvention=CallingConvention.Cdecl)]
  public static extern int Stop();
}
'@
    Add-Type -TypeDefinition $gionative.Replace('__DLL__',$GioScanDll.Replace('"','""'))
    if([C545DResourceGio]::Scan(0) -le 0){throw 'C545D_RESOURCE_CI_GIO_BASELINE_FAILED'}
    if([C545DResourceGio]::Start() -ne 0){throw 'C545D_RESOURCE_CI_GIO_MONITOR_START_FAILED'}
    $gioStarted=$true
  }
  $ret=[C545DResourceWatch]::Enter()
  if($ret -ne 0){throw "C545D_RESOURCE_CI_ENTER_FAILED=$ret"}
  $entered=$true
  $ret=[C545DResourceWatch]::Open([ref]$watch)
  if($ret -ne 0 -or $watch -eq [IntPtr]::Zero){throw "C545D_RESOURCE_CI_OPEN_FAILED=$ret"}
  [UInt64]$g0=Epoch
  Add-AppxPackage -Path $mainMsix -ErrorAction Stop
  $parent=@(Get-AppxPackage -Name $name -PackageTypeFilter Main -ErrorAction Stop)
  if($parent.Count -ne 1){throw "C545D_RESOURCE_CI_MAIN_COUNT=$($parent.Count)"}
  $installedParent=$parent[0].PackageFullName
  [UInt64]$g1=Await $g0
  if($g1 -le $g0){throw 'C545D_RESOURCE_CI_MAIN_EVENT_MISSING'}
  [UInt64]$s1=Status
  if($AssertLocalizedDisplayName){
    if($ReverseResourceLanguage){ & $LocalizedProbeExe $installedParent main_add reverse }
    else { & $LocalizedProbeExe $installedParent main_add }
    Checked 'localized_main_baseline'
  }
  if($gioStarted){
    $changed=[C545DResourceGio]::Observe(11)
    "C545D_RESOURCE_GIO_PREQUERY,stage=main_add,changed=$changed,CI_only=1"
  }
  $c1=Completion
  Add-AppxPackage -Path $resMsix -ErrorAction Stop
  $same=@(Get-AppxPackage -Name $name -PackageTypeFilter Main -ErrorAction Stop)
  if($same.Count -ne 1 -or $same[0].PackageFullName -ne $installedParent){
    throw 'C545D_RESOURCE_CI_PARENT_FULLNAME_CHANGED'
  }
  $resource=@(Get-AppxPackage -Name $name -PackageTypeFilter Resource -ErrorAction Stop |
              Where-Object {$_.ResourceId -eq $resourceId})
  if($resource.Count -ne 1){throw "C545D_RESOURCE_CI_RESOURCE_MISSING=$($resource.Count)"}
  $resourceFullName=$resource[0].PackageFullName
  [UInt64]$g2=Await $g1
  [UInt64]$s2=Status
  $c2=Completion
  if($AssertLocalizedDisplayName){
    if($ReverseResourceLanguage){ & $LocalizedProbeExe $installedParent resource_add reverse }
    else { & $LocalizedProbeExe $installedParent resource_add }
    Checked 'localized_resource_add'
  }
  if($gioStarted){
    $changed=[C545DResourceGio]::Observe(12)
    "C545D_RESOURCE_GIO_PREQUERY,stage=resource_add,changed=$changed,CI_only=1"
  }
  "C545D_RESOURCE_OS_ADD_OBSERVATION,parent_fullname_unchanged=1,resource_installed=1,native_generation_delta=$($g2-$g1),genuine_status_callbacks_delta=$($s2-$s1),install_terminal_delta=$($c2.inst-$c1.inst),update_terminal_delta=$($c2.upd-$c1.upd),uninstall_terminal_delta=$($c2.uninst-$c1.uninst),synthetic_events=0,CI_only=1"
  Remove-AppxPackage -Package $resourceFullName -ErrorAction Stop
  $resourceFullName=$null
  [UInt64]$g3=Await $g2
  [UInt64]$s3=Status
  $c3=Completion
  if($AssertLocalizedDisplayName){
    if($ReverseResourceLanguage){ & $LocalizedProbeExe $installedParent resource_remove reverse }
    else { & $LocalizedProbeExe $installedParent resource_remove }
    Checked 'localized_resource_remove'
  }
  if($gioStarted){
    $changed=[C545DResourceGio]::Observe(13)
    "C545D_RESOURCE_GIO_PREQUERY,stage=resource_remove,changed=$changed,CI_only=1"
  }
  "C545D_RESOURCE_OS_REMOVE_OBSERVATION,parent_fullname_unchanged=1,native_generation_delta=$($g3-$g2),genuine_status_callbacks_delta=$($s3-$s2),install_terminal_delta=$($c3.inst-$c2.inst),update_terminal_delta=$($c3.upd-$c2.upd),uninstall_terminal_delta=$($c3.uninst-$c2.uninst),synthetic_events=0,CI_only=1"
  'C545D_RESOURCE_PACKAGE_PROBE_COMPLETE,parent_fullname_stable=1,resource_add_remove=1,runner_only=1'
} finally {
  if($gioStarted){try{[void][C545DResourceGio]::Stop()}catch{'C545D_RESOURCE_CI_MONITOR_STOP_FAILED=1'}}
  if($watch -ne [IntPtr]::Zero){[C545DResourceWatch]::Close($watch)}
  if($entered){[C545DResourceWatch]::Leave()}
  try {
    if($resourceFullName){Remove-AppxPackage -Package $resourceFullName -ErrorAction SilentlyContinue}
    if($installedParent){Remove-AppxPackage -Package $installedParent -ErrorAction SilentlyContinue}
  }catch {'C545D_RESOURCE_CI_CLEANUP_PACKAGE_WARNING=1'}
  Remove-Item Env:C545D_CI_EVENT_PACKAGE_NAME -ErrorAction SilentlyContinue
  if($cert) {
    foreach($store in @('Cert:\CurrentUser\TrustedPeople','Cert:\LocalMachine\TrustedPeople','Cert:\LocalMachine\Root','Cert:\CurrentUser\My')){
      Remove-Item -LiteralPath ($store+'\'+$cert.Thumbprint) -Force -ErrorAction SilentlyContinue
    }
  }
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
  'C545D_RESOURCE_CI_CLEANUP_EXECUTED=1,runner_only=1'
}
