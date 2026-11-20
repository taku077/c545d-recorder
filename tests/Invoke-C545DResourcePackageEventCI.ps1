#Requires -Version 5.1
<#
CI ONLY. Signed disposable resource-package add/remove to test true
PackageCatalog callbacks while the parent main package FullName stays fixed.
No camera, production DLL, or user's registry/system is touched.
#>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$WatchDll,
      [Parameter(Mandatory=$true)][string]$StubExe)
$ErrorActionPreference='Stop'
$name='C545D.CI.PackageEvents'
$root=Join-Path $env:RUNNER_TEMP ('c545d_resource_'+[guid]::NewGuid().ToString('N'))
$secret=[guid]::NewGuid().ToString('N')
$watch=[IntPtr]::Zero
$entered=$false
$cert=$null
$installedParent=$null
$resourceFullName=$null
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
  & py tests/make_c545d_ci_package_fixture.py --out $mainDir --stub $StubExe --version '1.0.0.0'
  Checked 'main_fixture'
  & py tests/make_c545d_ci_resource_package_fixture.py --out $resDir --main-layout $mainDir
  Checked 'resource_fixture'
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
  [DllImport(@"__DLL__",EntryPoint="c545d_dedicated_global_counters",CallingConvention=CallingConvention.Cdecl)]
  public static extern void Counters(out UInt64 registered,out UInt64 revoked,out UInt64 errors);
}
'@
  Add-Type -TypeDefinition $native.Replace('__DLL__',$WatchDll.Replace('"','""'))
  $env:C545D_CI_EVENT_PACKAGE_NAME=$name
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
  Add-AppxPackage -Path $resMsix -ErrorAction Stop
  $same=@(Get-AppxPackage -Name $name -PackageTypeFilter Main -ErrorAction Stop)
  if($same.Count -ne 1 -or $same[0].PackageFullName -ne $installedParent){
    throw 'C545D_RESOURCE_CI_PARENT_FULLNAME_CHANGED'
  }
  $resource=@(Get-AppxPackage -Name $name -PackageTypeFilter Resource -ErrorAction Stop |
              Where-Object {$_.ResourceId -eq 'French'})
  if($resource.Count -ne 1){throw "C545D_RESOURCE_CI_RESOURCE_MISSING=$($resource.Count)"}
  $resourceFullName=$resource[0].PackageFullName
  [UInt64]$g2=Await $g1
  [UInt64]$s2=Status
  "C545D_RESOURCE_OS_ADD_OBSERVATION,parent_fullname_unchanged=1,resource_installed=1,native_generation_delta=$($g2-$g1),genuine_status_callbacks_delta=$($s2-$s1),synthetic_events=0,CI_only=1"
  Remove-AppxPackage -Package $resourceFullName -ErrorAction Stop
  $resourceFullName=$null
  [UInt64]$g3=Await $g2
  [UInt64]$s3=Status
  "C545D_RESOURCE_OS_REMOVE_OBSERVATION,parent_fullname_unchanged=1,native_generation_delta=$($g3-$g2),genuine_status_callbacks_delta=$($s3-$s2),synthetic_events=0,CI_only=1"
  'C545D_RESOURCE_PACKAGE_PROBE_COMPLETE,parent_fullname_stable=1,resource_add_remove=1,runner_only=1'
} finally {
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
