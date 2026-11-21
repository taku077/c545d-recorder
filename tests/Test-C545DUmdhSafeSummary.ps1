# Runner-only synthetic UMDH parsing: no debugger, heap capture or user data.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Get-C545DUmdhSafeSummary.ps1')
function Assert([bool]$ok,[string]$message){if(-not $ok){throw $message}}
$ms= @'
+ 5320 (f110 - 9df0) 3a allocs BackTrace00053
ntdll!RtlAllocateHeap+0x00000808
MyApp!LeakyFunc+0x0000001E
Total increase == 5320
'@
$a=Get-C545DUmdhSafeSummary -Content $ms
Assert ($a.Positive -eq 1 -and $a.Symbolized -eq 1 -and $a.GIO -eq 0 -and $a.Other -eq 1) 'Microsoft official example not parsed'
$sample=@'
+ 100 (100 - 0) 1 allocs BackTrace0000A
ntdll!RtlAllocateHeap+0x0008
gio-2.0-0!g_app_info_get_all+0x5
glib-2.0-0!g_malloc+0x1
- 20 (0 - 20) 1 allocs BackTrace0000B
ntdll!RtlFreeHeap+0x10
+ 80 (80 - 0) 1 allocs BackTrace0000C
combase!RoGetActivationFactory+0x10
+ 16 (16 - 0) 1 allocs BackTrace0000D
0x000000000000ABCD
'@
$b=Get-C545DUmdhSafeSummary -Content $sample
Assert ($b.Positive -eq 3 -and $b.Symbolized -eq 2 -and $b.Unresolved -eq 1) 'Signed count or unresolved stack wrong'
Assert ($b.GIO -eq 1 -and $b.GLib -eq 1 -and $b.WinRT -eq 1) 'Module-safe families wrong'
$zero=Get-C545DUmdhSafeSummary -Content 'Total increase == 0'
Assert ($zero.Positive -eq 0 -and $zero.Unresolved -eq 0) 'Zero growth incorrectly rejected'
$raw=Get-C545DUmdhSafeSummary -Content '+ 100 (100 - 0) 1 allocs BackTrace00AA'
Assert ($raw.Positive -eq 1 -and $raw.Unresolved -eq 1 -and $raw.GIO -eq 0) 'Raw unresolved snapshot falsely categorized'
Write-Host 'C545D_UMDH_SAFE_DIFF_SELFTEST_PASS,synthetic_cases=4,known_symbol_stacks=3,unresolved_classified=1,windows_runs=0,real_camera=0,host_modified=0'
