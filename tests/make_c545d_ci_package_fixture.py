#!/usr/bin/env python3
"""Generate isolated, synthetic MSIX test fixtures. CI ONLY.

No camera data, installed package names, credentials, private keys or registry
content. The executable is a throwaway no-op stub compiled in the runner.
"""
import argparse
from pathlib import Path
import shutil
import struct
import zlib


def png(size):
    row = b"\x00" + (b"\x70\x70\x70\xff" * size)
    raw = row * size
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level=9))
            + chunk(b"IEND", b""))


def build(out, stub, version):
    if version not in ("1.0.0.0", "1.0.1.0"):
        raise ValueError("Only the two disposable CI fixture versions are permitted")
    if not stub.is_file():
        raise ValueError("CI no-op stub missing")
    out.mkdir(parents=True, exist_ok=True)
    (out / "Assets").mkdir(exist_ok=True)
    shutil.copyfile(stub, out / "app.exe")
    for file, size in (("StoreLogo.png", 50), ("LargeLogo.png", 150),
                       ("SmallLogo.png", 44)):
        (out / "Assets" / file).write_bytes(png(size))
    # One unique synthetic identity; no real installed app or actual customer
    # package names. Signing CN MUST match this manifest Publisher exactly.
    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="C545D.CI.PackageEvents" Publisher="CN=C545D CI Event Probe"
            Version="{version}" ProcessorArchitecture="x64"/>
  <Properties>
    <DisplayName>C545D CI Event Probe</DisplayName>
    <PublisherDisplayName>C545D CI Event Probe</PublisherDisplayName>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0"
                        MaxVersionTested="10.0.26100.0"/>
  </Dependencies>
  <Resources><Resource Language="en-us"/></Resources>
  <Applications>
    <Application Id="App" Executable="app.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="C545D CI Event Probe"
                          Description="Disposable Windows CI package event fixture"
                          BackgroundColor="transparent"
                          Square150x150Logo="Assets\LargeLogo.png"
                          Square44x44Logo="Assets\SmallLogo.png"/>
    </Application>
  </Applications>
  <Capabilities><rescap:Capability Name="runFullTrust"/></Capabilities>
</Package>
"""
    (out / "AppxManifest.xml").write_bytes(manifest.encode("utf-8"))
    print(f"C545D_MSIX_SYNTHETIC_FIXTURE_CREATED,version={version},"
          "payload=NOOP_EXECUTABLE,media=false,credentials=false")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stub", type=Path, required=True)
    ap.add_argument("--version", choices=("1.0.0.0", "1.0.1.0"), required=True)
    a=ap.parse_args()
    build(a.out, a.stub, a.version)
