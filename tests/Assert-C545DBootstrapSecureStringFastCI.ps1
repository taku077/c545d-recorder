#Requires -Version 5.1
<# Fast CI-only child Windows PowerShell5.1 fake SecureString diagnostic.
 No GStreamer/RTSP/real credentials/user profile/production settings accessed.
 Test the exact child hidden-console process creation used by our test harness.
#>
$ErrorActionPreference='Stop'
$stage=$null;$p=$null;$owned=$false
$phase='START'
try {
  if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){throw 'CI_ONLY'}
  $root=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
  $stage=Join-Path $root ('c545d-ci-dpapi-child-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $stage | Out-Null
  [IO.File]::WriteAllText((Join-Path $stage '.owned'),'CI_DPAPI_CHILD')
  $owned=$true
  $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $child=Join-Path $stage 'child.ps1'
  $lines=@(
    'param([string]$Root)',
    '$ErrorActionPreference=''Stop''',
    '$state=Join-Path $Root ''state''',
    '[IO.File]::WriteAllText($state,''ENTER'')',
    '$conf=Join-Path $Root ''C545D_GStreamer''',
    'New-Item -ItemType Directory -Path $conf -Force|Out-Null',
    '[IO.File]::WriteAllText($state,''DIRECTORY_READY'')',
    'try {',
    '  $raw=ConvertTo-SecureString ''CI_DUMMY_NOT_REAL'' -AsPlainText -Force',
    '  [IO.File]::WriteAllText($state,''SECURESTRING_READY'')',
    '  $encrypted=ConvertFrom-SecureString $raw',
    '  [IO.File]::WriteAllText($state,''ENCRYPTED'')',
    '  $decrypted=ConvertTo-SecureString -String $encrypted',
    '  [IO.File]::WriteAllText($state,''DECRYPTED'')',
    '} catch {',
    '  $kind=$_.Exception.GetType().Name',
    '  $allowed=@(''CommandNotFoundException'',''CryptographicException'',''RuntimeException'',''MethodInvocationException'',''ArgumentException'',''SecurityException'')',
    '  if($kind -notin $allowed){$kind=''Other''}',
    '  [IO.File]::WriteAllText($state,''EXCEPTION_''+$kind)',
    '  exit 3',
    '}',
    'exit 0'
  )
  [IO.File]::WriteAllText($child,($lines -join [Environment]::NewLine),
      [Text.UTF8Encoding]::new($false))
  $args=@('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
    '-File',('"'+$child+'"'),'-Root',('"'+$stage+'"'))
  $p=Start-Process -FilePath $ps -ArgumentList $args -PassThru -WindowStyle Hidden -WorkingDirectory $root
  if(-not $p.WaitForExit(15000)){throw 'CHILD_TIMEOUT'}
  $statePath=Join-Path $stage 'state'
  $state=if(Test-Path -LiteralPath $statePath){[IO.File]::ReadAllText($statePath)}else{'NO_STATE'}
  $allowedStates=@('ENTER','DIRECTORY_READY','SECURESTRING_READY','ENCRYPTED','DECRYPTED',
    'NO_STATE','EXCEPTION_CommandNotFoundException','EXCEPTION_CryptographicException',
    'EXCEPTION_RuntimeException','EXCEPTION_MethodInvocationException',
    'EXCEPTION_ArgumentException','EXCEPTION_SecurityException','EXCEPTION_Other')
  if($state -notin $allowedStates){$state='OTHER'}
  $exit=[int]$p.ExitCode
  $phase='COMPLETE'
  Write-Output "C545D_FAST_SECURESTRING_CHILD,status=$state,exit=$exit,real_camera=0"
  if($state -cne 'DECRYPTED' -or $exit -ne 0){throw 'SECURESTRING_CHILD_FAILED'}
} catch {
  $known=@('CI_ONLY','CHILD_TIMEOUT','SECURESTRING_CHILD_FAILED')
  $reason=if($_.Exception.Message -in $known){$_.Exception.Message}else{'BLOCKED'}
  Write-Output "C545D_FAST_SECURESTRING_CHILD_FAIL,phase=$phase,reason=$reason,real_camera=0"
  exit 3
} finally {
  if($p){
    if(-not $p.HasExited){try{$p.Kill();[void]$p.WaitForExit(5000)}catch {}}
    $p.Dispose()
  }
  if($owned -and $stage -and (Test-Path -LiteralPath $stage)){
    $item=Get-Item -LiteralPath $stage -Force
    $links=@(Get-ChildItem -LiteralPath $stage -Recurse -Force|Where-Object {
      ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if(-not $item.PSIsContainer -or $links.Count -ne 0 -or
       ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
       [IO.Path]::GetDirectoryName($stage).TrimEnd('\') -cne $root -or
       [IO.File]::ReadAllText((Join-Path $stage '.owned')) -cne 'CI_DPAPI_CHILD'){
      throw 'CI_STAGE_CLEANUP_REFUSED'
    }
    Remove-Item -LiteralPath $stage -Force -Recurse
  }
}
