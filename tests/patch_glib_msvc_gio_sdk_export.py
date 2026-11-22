#!/usr/bin/env python3
"""Restore exactly one GStreamer 1.28.8 SDK GIO DLL export for MSVC CI.

GLib 2.82.4's Meson default does not export an internal GIOModule function
that is exported by the official GStreamer MSVC x64 SDK (verified with DUMPBIN).
The source implementation already exists. Export its *existing* function; do
not add a shim, replace logic or suppress other ABI differences.
Only the isolated MSVC build experiment uses this change.
"""
from pathlib import Path
import sys

TARGET = "_g_io_modules_ensure_extension_points_registered"


def patch_file(filename: str) -> None:
    p = Path(filename)
    original = p.read_bytes()
    text = original.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n")
    start = "libgio = library('gio-2.0',"
    old = "  link_args : [noseh_link_args, glib_link_flags],"
    new = ("  # Keep the existing function exported to match the official GStreamer "
           "MSVC SDK.\n  link_args : [noseh_link_args, glib_link_flags, "
           "'/EXPORT:" + TARGET + "'],")
    if normalized.count(start) != 1 or normalized.count(old) != 1:
        raise RuntimeError("MSVC_GIO_SDK_EXPORT_REFUSED: unexpected upstream Meson source")
    if normalized.count(new) or normalized.count("/EXPORT:" + TARGET):
        raise RuntimeError("MSVC_GIO_SDK_EXPORT_REFUSED: already modified")
    p.write_bytes(normalized.replace(old, new, 1).replace("\n", nl).encode("utf-8"))
    print("MSVC_GIO_SDK_EXPORT_PARITY_PATCHED: " + TARGET)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_msvc_gio_sdk_export.py <gio/meson.build>")
    patch_file(sys.argv[1])
