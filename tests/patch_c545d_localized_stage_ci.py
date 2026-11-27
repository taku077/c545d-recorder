#!/usr/bin/env python3
"""Instrument a disposable copy; never publish original exception messages."""
import argparse
from pathlib import Path

STAGES=(
("  if(@(Get-AppxPackage -Name $name -ErrorAction Stop).Count){","identity"),
("  $make=Tool 'MakeAppx.exe'","tools"),
("  $cert=New-SelfSignedCertificate","certificate"),
("  Export-PfxCertificate -Cert $cert","certificate_export"),
("  Import-Certificate -FilePath $cer -CertStoreLocation 'Cert:\\CurrentUser\\TrustedPeople'","certificate_import"),
("  & py @mainArgs","main_fixture"),
("  & py @resourceArgs","resource_fixture"),
("  $pri=Tool 'MakePri.exe'","pri_tool"),
("  & $pri createconfig /cf $mainCfg","main_pri"),
("  & $pri createconfig /cf $resCfg","resource_pri"),
("  & $make pack /o /d $mainDir","main_pack"),
("  Push-Location $resDir","resource_pack"),
("  & $sign sign /fd SHA256 /f $pfx /p $secret $mainMsix","main_sign"),
("  & $sign sign /fd SHA256 /f $pfx /p $secret $resMsix","resource_sign"),
("  Add-Type -TypeDefinition $native.Replace","watch_import"),
("    Add-Type -TypeDefinition $gionative.Replace","gio_import"),
("    if([C545DResourceGio]::Scan(0)","gio_baseline"),
("    if([C545DResourceGio]::Start()","gio_start"),
("  $ret=[C545DResourceWatch]::Enter()","watch_enter"),
("  $ret=[C545DResourceWatch]::Open(","watch_open"),
("  Add-AppxPackage -Path $mainMsix","main_add"),
("  Add-AppxPackage -Path $resMsix","resource_add"),
("  Remove-AppxPackage -Package $resourceFullName -ErrorAction Stop","resource_remove"),
)
CATCH=r""" } catch {
  $record=$_
  $line=[int]$record.InvocationInfo.ScriptLineNumber
  [Console]::WriteLine("C545D_LOCALIZED_FAILURE,stage=$c545dStage,line=$line")
  $exception=$record.Exception
  for($depth=0;$null -ne $exception -and $depth -lt 8;$depth++){
    $hr=[int]$exception.HResult
    [Console]::WriteLine("C545D_LOCALIZED_HRESULT,depth=$depth,value=$hr")
    $exception=$exception.InnerException
  }
  throw
} finally {
  [Console]::WriteLine("C545D_LOCALIZED_STAGE,stage=cleanup")
"""
def patch(s):
    if "C545D_LOCALIZED_FAILURE" in s: raise ValueError("already_patched")
    for anchor,stage in STAGES:
        if s.count(anchor)!=1: raise ValueError("stage_anchor:"+stage)
        indent=anchor[:len(anchor)-len(anchor.lstrip())]
        s=s.replace(anchor,indent+"$c545dStage='"+stage+"'\n"+indent+
                    '[Console]::WriteLine("C545D_LOCALIZED_STAGE,stage=$c545dStage")\n'+anchor,1)
    a="} finally {\n  if($gioStarted)"
    if s.count(a)!=1: raise ValueError("catch_anchor")
    return s.replace(a,CATCH.lstrip()+"  if($gioStarted)",1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.source.name!="Invoke-C545DResourcePackageEventCI.ps1" or a.out.name!="c545d_localized_stage_probe.ps1" or a.out.exists():
        raise SystemExit("disposable_only")
    s=a.source.read_text(encoding="utf-8-sig")
    a.out.write_text(patch(s),encoding="utf-8-sig")
    print("C545D_LOCALIZED_STAGE_PATCH_PASS,stages=23,raw_uploaded=0")
if __name__=="__main__": main()
