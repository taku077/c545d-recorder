# Synthetic policy tests. Never starts GStreamer, accesses cameras, or writes MP4.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$file = Join-Path $root 'Record.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$errors)
if (@($errors).Count -ne 0) { throw 'Record.ps1 failed parser validation' }
$fn = $ast.Find({
    param($node)
    ($node -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and
    ($node.Name -eq 'Get-C545DExitAction')
}, $true)
if (-not $fn) { throw 'Get-C545DExitAction not found' }
# Execute ONLY the isolated pure function. Never dot-source Record.ps1: it
# would connect to cameras or trigger media startup.
. ([scriptblock]::Create($fn.Extent.Text))
$cases = @(
  @{ Name='gui_stop_zero';      Marker=$true;  Managed=$true;  Code=0;   Expected='stop' },
  @{ Name='gui_stop_error';     Marker=$true;  Managed=$true;  Code=1;   Expected='stop' },
  @{ Name='unexpected_ctrl_c'; Marker=$false; Managed=$true;  Code=0;   Expected='reconnect' },
  @{ Name='unexpected_error';  Marker=$false; Managed=$true;  Code=137; Expected='reconnect' },
  @{ Name='standalone_exit';   Marker=$false; Managed=$false; Code=0;   Expected='stop' },
  @{ Name='standalone_error';  Marker=$false; Managed=$false; Code=2;   Expected='reconnect' }
)
foreach ($c in $cases) {
    $actual = Get-C545DExitAction -authorizedStop $c.Marker -managedSession $c.Managed -exitCode $c.Code
    if ($actual -ne $c.Expected) {
        throw ('Exit policy FAIL: ' + $c.Name + ', got=' + $actual)
    }
    Write-Host ('PASS ' + $c.Name + ': ' + $actual)
}
$src=[IO.File]::ReadAllText($file)
if ($src -notmatch 'Take-C545DUnexpectedCtrlCCount') { throw 'Missing control event evidence' }
if ($src -notmatch 'if \(\$exitAction -eq ''stop''\)') { throw 'Recording loop does not use exit policy' }
if ($src -notmatch 'Start-Sleep -Milliseconds 250') { throw 'Missing interruptible retry delay' }
$worker=[IO.File]::ReadAllText((Join-Path $root 'RecordGUIWorker.ps1'))
if ($worker -notmatch 'TakeCtrlCSignals\(\)') { throw 'Worker does not capture console interrupts' }
Write-Host 'PASS: recording stop/reconnect policy and event evidence.'
