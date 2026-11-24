# CI-only external UI Automation; does not inject code into the shipped EXE.
param([int]$TargetPid,[ValidateSet('start','stop','quit')][string]$Action,[string]$Stage)
$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
   $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
   [IO.File]::ReadAllText((Join-Path $Stage '.c545d-ci-owned')) -cne 'CI_MIRROR_ONLY_NOT_FOR_EXECUTION'){exit 3}
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$target=Get-Process -Id $TargetPid -ErrorAction Stop
try{
    if($target.Path -ine (Join-Path $Stage 'C545D_Recorder.exe')){exit 3}
    $names=@{
        start=(-join @([char]9679,[char]32,[char]37682,[char]30011,[char]38283,[char]22987))
        stop=(-join @([char]9632,[char]32,[char]37682,[char]30011,[char]20572,[char]27490))
        quit=(-join @([char]12450,[char]12503,[char]12522,[char]12434,[char]32066,[char]20102))
    }
    $clock=[Diagnostics.Stopwatch]::StartNew()
    do{
        $target.Refresh()
        if($target.HasExited){exit 3}
        if($target.MainWindowHandle -ne [IntPtr]::Zero){
            $root=[System.Windows.Automation.AutomationElement]::FromHandle($target.MainWindowHandle)
            if($root.Current.ProcessId -ne $TargetPid){exit 3}
            $condition=[System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                [System.Windows.Automation.ControlType]::Button)
            $matches=@($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition) |
                Where-Object {$_.Current.Name -ceq $names[$Action] -and $_.Current.ProcessId -eq $TargetPid})
            if($matches.Count -gt 1){exit 3}
            if($matches.Count -eq 1 -and $matches[0].Current.IsEnabled){
                $invoke=$matches[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $invoke.Invoke()
                exit 0
            }
        }
        Start-Sleep -Milliseconds 150
    }while($clock.ElapsedMilliseconds -lt 12000)
    exit 3
}finally{$target.Dispose()}
