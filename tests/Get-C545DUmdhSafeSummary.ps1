# CI-only UMDH *diff* analysis. Never prints raw frames, symbols, paths,
# addresses, package names, memory contents or private user data.
# Use the symbolized UMDH -v Log1 Log2 comparison, not raw -f snapshots.
function Get-C545DUmdhSafeSummary {
  [CmdletBinding()]
  param([Parameter(Mandatory)][string]$Content)
  $lines=[regex]::Split($Content,'\r?\n')
  $rx='(?i)^\s*([+-])\s+(?:0x)?([0-9a-f]{1,16})\s+\([^)]*\)\s+(?:0x)?[0-9a-f]{1,16}\s+allocs\s+BackTrace([0-9a-f]+)\b'
  $headers=[System.Collections.Generic.List[object]]::new()
  for($i=0;$i -lt $lines.Length;$i++){
    $m=[regex]::Match($lines[$i],$rx)
    if($m.Success){
      $headers.Add([PSCustomObject]@{Index=$i;Sign=$m.Groups[1].Value;Id=$m.Groups[3].Value.ToUpperInvariant().TrimStart('0')})
    }
  }
  $positive=0;$gio=0;$glib=0;$winrt=0;$symbolized=0;$unresolved=0;$other=0
  foreach($h in $headers){
    if($h.Sign -ne '+'){continue}
    $positive++
    $end=$lines.Length
    foreach($next in $headers){
      if($next.Index -gt $h.Index){$end=$next.Index;break}
    }
    $mods=[System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    for($j=$h.Index+1;$j -lt $end;$j++){
      # UMDH prints one module!routine per symbolized frame.
      # Only the module stem is inspected; it is never printed.
      $ms=[regex]::Matches($lines[$j],'(?i)(?<![a-z0-9_.-])([a-z][a-z0-9_.-]{1,63})!\S')
      foreach($m in $ms){[void]$mods.Add($m.Groups[1].Value.ToLowerInvariant())}
    }
    if($mods.Count -eq 0){$unresolved++;continue}
    $symbolized++
    $hasGio=$false;$hasGlib=$false;$hasWinrt=$false;$hasOther=$false
    foreach($name in $mods){
      if($name -match '^(?:lib)?gio-2[._-]0(?:[-_.]0)?$'){$hasGio=$true}
      elseif($name -match '^(?:lib)?(?:glib|gobject|gmodule)-2[._-]0(?:[-_.]0)?$'){$hasGlib=$true}
      elseif($name -match '^(?:combase|windowsapp|windows[.]applicationmodel|ole32)$'){$hasWinrt=$true}
      elseif($name -notmatch '^(?:ntdll|kernel32|kernelbase|ucrtbase|msvcrt|vcruntime[0-9_.-]*|msvcp[0-9_.-]*)$'){$hasOther=$true}
    }
    if($hasGio){$gio++}
    if($hasGlib){$glib++}
    if($hasWinrt){$winrt++}
    if($hasOther){$other++}
  }
  [PSCustomObject]@{
    Positive=$positive;Symbolized=$symbolized;Unresolved=$unresolved
    GIO=$gio;GLib=$glib;WinRT=$winrt;Other=$other
    Exact360OwnerProven=0;RawUploaded=0
  }
}
