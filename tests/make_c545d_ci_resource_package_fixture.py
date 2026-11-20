#!/usr/bin/env python3
"""CI ONLY: make a no-executable MSIX resource package for the existing
signed disposable C545D.CI.PackageEvents main app. This does not modify the
recorder or a customer's installed packages. The fixed synthetic identity is
intentionally identical to the pre-existing test app's *Name* and *Version*;
only ResourceId differs.
"""
from pathlib import Path
import argparse
import shutil

def build(out: Path, existing_main_layout: Path) -> None:
    logo = existing_main_layout / "Assets" / "StoreLogo.png"
    if not logo.is_file():
        raise ValueError("expected existing disposable main fixture asset")
    out.mkdir(parents=True, exist_ok=True)
    (out / "Assets").mkdir(exist_ok=True)
    shutil.copyfile(logo, out / "Assets" / "StoreLogo.png")
    (out / "resource.txt").write_text(
        "CI-only French resource fixture. No media or user content.\n",
        encoding="utf-8",
    )
    manifest = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">
  <Identity Name="C545D.CI.PackageEvents" Publisher="CN=C545D CI Event Probe"
            Version="1.0.0.0" ResourceId="French"/>
  <Properties>
    <DisplayName>C545D CI French Resource</DisplayName>
    <PublisherDisplayName>C545D CI Event Probe</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <ResourcePackage>true</ResourcePackage>
  </Properties>
  <Resources><Resource Language="fr-fr"/></Resources>
</Package>
"""
    (out / "AppxManifest.xml").write_text(manifest, encoding="utf-8")
    # According to the official MakeAppx /r /m /f contract, resources
    # require both ResourceDimensions and ResourceId in the mapping.
    # Keep the mapping self-contained under the disposable temp root.
    mapping = """[ResourceMetadata]
"ResourceDimensions" "language-fr-fr"
"ResourceId" "French"

[Files]
"Assets\\StoreLogo.png" "Assets\\StoreLogo.png"
"resource.txt" "resource.txt"
"""
    (out / "mapping.txt").write_text(mapping, encoding="utf-8")
    print("C545D_RESOURCE_FIXTURE_CREATED,resource_id=French,"
          "main_version_unchanged=1,resource_only=1,CI_only=1")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--main-layout", type=Path, required=True)
    args = parser.parse_args()
    build(args.out, args.main_layout)
