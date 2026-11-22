#!/usr/bin/env python3
"""Fix one redundant UTF-16 path allocation in upstream GLib 2.82.4.

The "path-utf16" GParamSpec is a pointer property. Its set_property handler
copies the incoming path using g_wcsdup(); it does not assume ownership.
g_win32_registry_key_new_w() must pass the borrowed input pointer rather
than g_wcsdup()'ing it a second time and losing the temporary allocation.

CI-only patch until tested with GStreamer SDK, no user machine modifications.
"""
from pathlib import Path
import sys


def main(filename: str) -> None:
    path = Path(filename)
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    src = original.decode("utf-8").replace("\r\n", "\n")
    # Anchor narrowly to this constructor and not any other GValue pointer.
    before = """  result = g_initable_new (G_TYPE_WIN32_REGISTRY_KEY,
                           NULL,
                           error,
                           "path-utf16",
                           g_wcsdup (path, -1),
                           NULL);"""
    after = """  /* The pointer property setter takes a private copy of path.
   * Passing an additional g_wcsdup() here leaked the temporary copy.
   * g_initable_new() sets this property synchronously.
   */
  result = g_initable_new (G_TYPE_WIN32_REGISTRY_KEY,
                           NULL,
                           error,
                           "path-utf16",
                           (gpointer) path,
                           NULL);"""
    if src.count(before) != 1:
        raise RuntimeError(
            "GLIB_2824_UTF16_FIX_REFUSED: unexpected constructor source"
        )
    setter = """    case PROP_PATH_UTF16:
      path_w = (gunichar2 *) g_value_get_pointer (value);"""
    setter_copy = """      priv->absolute_path_w = g_wcsdup (path_w, -1);"""
    prop = """g_param_spec_pointer ("path-utf16", NULL, NULL,"""
    if src.count(setter) != 1 or src.count(setter_copy) != 1 or src.count(prop) != 1:
        raise RuntimeError(
            "GLIB_2824_UTF16_FIX_REFUSED: pointer ownership contract changed"
        )
    path.write_bytes(src.replace(before, after, 1).replace("\n", newline).encode("utf-8"))
    print("GLIB_2824_UTF16_REDUNDANT_ALLOCATION_REMOVED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_registry_owned_path.py <gwin32registrykey.c>")
    main(sys.argv[1])
