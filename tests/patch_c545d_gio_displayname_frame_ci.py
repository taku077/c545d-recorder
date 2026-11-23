#!/usr/bin/env python3
"""CI-only original-stack discriminator immediately inside WinRT DisplayName getter.

Applies AFTER 2.82.4 packageparser source overlays, including the opted-out
exact DisplayName cache. The marker is an x64 MSVC *noinline GIO frame*, not a
new production cache, ABI export or functional bypass. The getter is still
called exactly once per uncached package, with the exact HRESULT and HSTRING.
TraceEvent's private RSDS-verified symbol is used, never uploaded raw.
"""
from __future__ import annotations
import argparse
from pathlib import Path

TARGET = "           hr = IPackage2_get_DisplayName (ipackage2, &display_name);"
MARKER = "c545d_ci_displayname_getter_scope"
ENTRY = "gboolean\ng_win32_package_parser_enum_packages"
FUNCTION = r'''/* Disposable MSVC CI ONLY: visible allocation stack boundary.
 * Volatile read after the getter prevents a tail call, preserving the
 * original HRESULT and ownership of the returned HSTRING.
 */
static __declspec(noinline) HRESULT
c545d_ci_displayname_getter_scope (IPackage2 *package, HSTRING *returned)
{
  HRESULT result = IPackage2_get_DisplayName (package, returned);
  volatile HRESULT keep_frame_until_return = result;
  return keep_frame_until_return;
}

'''

def patch(s: str) -> str:
    if MARKER in s:
        raise ValueError("displayname_frame_already_injected")
    if s.count(TARGET) != 1 or s.count(ENTRY) != 1:
        raise ValueError("getter_callsite_or_function_anchor_not_unique")
    if s.index(ENTRY) > s.index(TARGET):
        raise ValueError("getter_call_not_inside_expected_parser")
    # Replacement is exact and independent of C function arguments.
    s = s.replace(ENTRY, FUNCTION + ENTRY, 1)
    s = s.replace(TARGET, TARGET.replace(
        "IPackage2_get_DisplayName", MARKER), 1)
    if s.count(MARKER) != 2: # static function definition and one getter call
        # One definition + one call is required; no partial application.
        raise ValueError("getter_frame_marker_count")
    return s

def selftest() -> None:
    example = (
        "#include <windows.h>\n"
        + ENTRY + "\n{\n"
        + TARGET + "\n"
        + '           canned_com_error_handler_pkg ("IPackage2_get_DisplayName()", package_cleanup);\n'
        + "  return TRUE;\n}\n"
    )
    positive = patch(example)
    assert "volatile HRESULT keep_frame_until_return" in positive
    assert positive.index(MARKER) < positive.index(ENTRY)
    assert "hr = c545d_ci_displayname_getter_scope (ipackage2, &display_name);" in positive
    assert positive.count("IPackage2_get_DisplayName (") == 1
    bad = [
        positive,
        example.replace(TARGET,""),
        example.replace(TARGET,TARGET+"\n"+TARGET),
        example.replace(ENTRY,""),
        example.replace(ENTRY,ENTRY+"\n"+ENTRY),
        example.replace(ENTRY,ENTRY).replace(TARGET,"    hr = Other();"),
    ]
    for num, case in enumerate(bad):
        try: patch(case)
        except ValueError: pass
        else: raise AssertionError(f"unsafe_getter_wrapper_patch_accepted:{num}")
    print("C545D_GIO_DISPLAYNAME_FRAME_SOURCE_SELFTEST_PASS,positive=1,negative=6,"
          "original_getter_preserved=1,one_noinline_private_frame=1,"
          "no_winrt_path_or_cache_semantics_changed=1,host_untouched=1,release_HOLD=1")

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("source",nargs="?",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        selftest()
        return
    if a.source is None or a.source.name != "gwin32packageparser.c":
        p.error("only disposable GLib 2.82.4 gwin32packageparser.c")
    original=a.source.read_bytes()
    nl="\r\n" if b"\r\n" in original else "\n"
    updated=patch(original.decode("utf-8").replace("\r\n","\n"))
    a.source.write_bytes(updated.replace("\n",nl).encode("utf-8"))
    print("C545D_GIO_DISPLAYNAME_FRAME_SOURCE_PASS,private_noinline=1,"
          "functionality_original=1,actual_stack_detection_pending=1,"
          "original_source_GIO_2824=1,host_untouched=1,release_HOLD=1")

if __name__=="__main__":
    main()
