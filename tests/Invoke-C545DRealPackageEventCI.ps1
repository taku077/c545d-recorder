#Requires -Version 5.1
<#
CI ONLY: Disposable self-signed MSIX fixture install/update/uninstall.
Runs exclusively on GitHub-hosted Windows; never run on the recorder.
The no-op packaged executable is NEVER launched.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$WatchDll,
  [Parameter(Mandatory=$true)][string]$StubExe
)
$ErrorActionPreference='Stop'
$name='C545D.CI.PackageEvents'
$root=Join-Path $env:RUNNER_TEMP ('c545d_event_'+[guid]::NewGuid().ToString('N'))
$watch=[IntPtr]::Zero
$runtime=$false
$cert=$null
$trusted=$false
$secret=[guid]::NewGuid().ToString('N')
New-Item -ItemType Directory -Path $root -Force | Out-Null

function Get-SdkExe([string]$exe) {
  $base=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Windows Kits\10\bin'
  $list=@(Get-ChildItem $base -Filter $exe -Recurse -File -ErrorAction SilentlyContinue |
          Where-Object {$_.DirectoryName -match '[\\/]x64$'} | Sort-Object FullName)
  if($list.Count -eq 0) { throw "C545D_REAL_APPX_PLATFORM_BLOCKED,missing_tool=$exe" }
  return $list[-1].FullName
}
function Require-Exit([string]$label) {
  if($LASTEXITCODE -ne 0) { throw "$label,exit=$LASTEXITCODE" }
}
function Read-Epoch {
  for($retry=0;$retry -lt 40;$retry++) {
    [UInt64]$g=0
    [UInt64]$l=0
    $status=[C545DWatchInterop]::Snapshot($script:watch,[ref]$g,[ref]$l)
    if($status -eq 0) { return $g }
    if($status -ne 5) { throw "C545D_REAL_APPX_SNAPSHOT_FAILED,status=$status" }
    Start-Sleep -Milliseconds 50
  }
  throw "C545D_REAL_APPX_SNAPSHOT_RACE_EXHAUSTED"
}
function Await-Event([UInt64]$epoch,[string]$stage) {
  for($k=0;$k -lt 150;$k++) {
    [UInt64]$now=Read-Epoch
    if($now -gt $epoch) { return $now }
    Start-Sleep -Milliseconds 100
  }
  throw "C545D_REAL_APPX_EVENT_MISSING,stage=$stage,package_action_succeeded=true"
}
function Pack-Fixture([string]$v,[string]$make,[string]$sign,[string]$pfx) {
  $layout=Join-Path $root ("layout_"+$v)
  $msix=Join-Path $root ("package_"+$v+".msix")
  & py tests/make_c545d_ci_package_fixture.py --out $layout --stub $StubExe --version $v | Out-Host
  Require-Exit 'C545D_REAL_APPX_FIXTURE_CREATION_FAILED'
  & $make pack /o /d $layout /p $msix *> $null
  Require-Exit 'C545D_REAL_APPX_PACK_FAILED'
  & $sign sign /fd SHA256 /f $pfx /p $secret $msix *> $null
  Require-Exit 'C545D_REAL_APPX_SIGN_FAILED'
  return $msix
}
try {
  if(@(Get-AppxPackage -Name $name -ErrorAction Stop).Count -ne 0) {
    throw 'C545D_REAL_APPX_UNSAFE_PREEXISTING_TEST_IDENTITY'
  }
  $make=Get-SdkExe 'MakeAppx.exe'
  $sign=Get-SdkExe 'SignTool.exe'
  $cert=New-SelfSignedCertificate -Type Custom -KeyUsage DigitalSignature -Subject 'CN=C545D CI Event Probe' -CertStoreLocation 'Cert:\CurrentUser\My' -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3') -KeyExportPolicy Exportable -HashAlgorithm SHA256 -ErrorAction Stop
  $pfx=Join-Path $root 'ephemeral.pfx'
  $cer=Join-Path $root 'ephemeral.cer'
  $pw=ConvertTo-SecureString -String $secret -AsPlainText -Force
  Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $pw | Out-Null
  Export-Certificate -Cert $cert -FilePath $cer | Out-Null
  Import-Certificate -FilePath $cer -CertStoreLocation 'Cert:\CurrentUser\TrustedPeople' | Out-Null
  $trusted=$true
  $v1=Pack-Fixture '1.0.0.0' $make $sign $pfx
  $v2=Pack-Fixture '1.0.1.0' $make $sign $pfx

  # Intentionally maintain the same real dedicated MTA watcher across all
  # three Windows package mutations. The C ABI emits generation only.
  $native=@'
using System;
using System.Runtime.InteropServices;
public static class C545DWatchInterop {
  [DllImport(@"__DLL__", EntryPoint="c545d_dedicated_runtime_enter", CallingConvention=CallingConvention.Cdecl)]
  public static extern int Enter();
  [DllImport(@"__DLL__", EntryPoint="c545d_dedicated_runtime_leave", CallingConvention=CallingConvention.Cdecl)]
  public static extern void Leave();
  [DllImport(@"__DLL__", EntryPoint="c545d_dedicated_open", CallingConvention=CallingConvention.Cdecl)]
  public static extern int Open(out IntPtr watch);
  [DllImport(@"__DLL__", EntryPoint="c545d_dedicated_snapshot", CallingConvention=CallingConvention.Cdecl)]
  public static extern int Snapshot(IntPtr watch, out UInt64 generation, out UInt64 locale);
  [DllImport(@"__DLL__", EntryPoint="c545d_dedicated_close", CallingConvention=CallingConvention.Cdecl)]
  public static extern void Close(IntPtr watch);
  [DllImport(@"__DLL__", EntryPoint="c545d_dedicated_global_counters", CallingConvention=CallingConvention.Cdecl)]
  public static extern void Counters(out UInt64 registered, out UInt64 revoked, out UInt64 errors);
}
'@
  Add-Type -TypeDefinition $native.Replace('__DLL__',$WatchDll.Replace('"','""')) -ErrorAction Stop
  $ret=[C545DWatchInterop]::Enter()
  if($ret -ne 0) { throw "C545D_REAL_APPX_ENTER_FAILED,status=$ret" }
  $runtime=$true
  $ret=[C545DWatchInterop]::Open([ref]$watch)
  if($ret -ne 0 -or $watch -eq [IntPtr]::Zero) { throw "C545D_REAL_APPX_WATCH_OPEN_FAILED,status=$ret" }
  [UInt64]$g0=Read-Epoch

  Add-AppxPackage -Path $v1 -ErrorAction Stop
  $installed=@(Get-AppxPackage -Name $name -ErrorAction Stop)
  if($installed.Count -ne 1 -or $installed[0].Version.ToString() -ne '1.0.0.0') {
    throw 'C545D_REAL_APPX_INSTALL_STATE_WRONG'
  }
  [UInt64]$g1=Await-Event $g0 'install'

  Add-AppxPackage -Path $v2 -ErrorAction Stop
  $installed=@(Get-AppxPackage -Name $name -ErrorAction Stop)
  if($installed.Count -ne 1 -or $installed[0].Version.ToString() -ne '1.0.1.0') {
    throw 'C545D_REAL_APPX_UPDATE_STATE_WRONG'
  }
  [UInt64]$g2=Await-Event $g1 'update'

  Remove-AppxPackage -Package $installed[0].PackageFullName -ErrorAction Stop
  if(@(Get-AppxPackage -Name $name -ErrorAction Stop).Count -ne 0) {
    throw 'C545D_REAL_APPX_UNINSTALL_STATE_WRONG'
  }
  [UInt64]$g3=Await-Event $g2 'uninstall'
  "C545D_REAL_PACKAGECATALOG_EVENT_PASS,install_delta=$($g1-$g0),update_delta=$($g2-$g1),uninstall_delta=$($g3-$g2),total_delta=$($g3-$g0),no_synthetic_notifications=true,CI_only=true"
}
finally {
  if($watch -ne [IntPtr]::Zero) {
    [C545DWatchInterop]::Close($watch)
    $watch=[IntPtr]::Zero
  }
  if($runtime) { [C545DWatchInterop]::Leave() }
  try {
    @(Get-AppxPackage -Name $name -ErrorAction SilentlyContinue) |
      ForEach-Object {Remove-AppxPackage -Package $_.PackageFullName -ErrorAction SilentlyContinue}
  } catch { "C545D_REAL_APPX_CLEANUP_PACKAGE_WARNING=true" }
  if($trusted -and $cert) {
    Remove-Item -LiteralPath ("Cert:\CurrentUser\TrustedPeople\"+$cert.Thumbprint) -Force -ErrorAction SilentlyContinue
  }
  if($cert) {
    Remove-Item -LiteralPath ("Cert:\CurrentUser\My\"+$cert.Thumbprint) -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
  "C545D_REAL_APPX_CLEANUP_EXECUTED=true,runner_only=true"
}
