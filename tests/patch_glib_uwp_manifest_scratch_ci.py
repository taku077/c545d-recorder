#!/usr/bin/env python3
"""Disposable GIO WinRT manifest path scratch-buffer reuse candidate.

Scope: during *one* synchronous PackageManager enumeration only, reuse the
temporary wchar_t manifest path buffer across packages; free it at the
function's single cleanup label. No cross-scan cache, no public API change.
Applied after the existing native-path/WinRT patch chain and before Meson
rebuild in an ISOLATED Windows CI runner, never to a running recorder.
"""
from __future__ import annotations

import sys
from pathlib import Path

DECL = "  struct _xml_sax_state *sax = &sax_stack;\n"
DECL_NEW = (DECL +
    "  wchar_t *c545d_ci_manifest_scratch = NULL;\n"
    "  gsize c545d_ci_manifest_capacity = 0;\n")
ALLOC = "      manifest_filename = g_new (wchar_t, manifest_filename_size + 1);\n"
ALLOC_NEW = (
    "      /* Reuse only within this synchronous package enumeration. */\n"
    "      if (manifest_filename_size + 1 > c545d_ci_manifest_capacity)\n"
    "        {\n"
    "          c545d_ci_manifest_scratch = g_realloc_n (\n"
    "              c545d_ci_manifest_scratch, manifest_filename_size + 1,\n"
    "              sizeof (wchar_t));\n"
    "          c545d_ci_manifest_capacity = manifest_filename_size + 1;\n"
    "        }\n"
    "      manifest_filename = c545d_ci_manifest_scratch;\n")
PKG_RELEASE = "      g_clear_pointer (&manifest_filename, g_free);\n"
PKG_RELEASE_NEW = "      /* Borrowed from the scan-local scratch buffer. */\n      manifest_filename = NULL;\n"
SCAN_RELEASE = "  cleanup:\n  if (packages_iterator)\n"
SCAN_RELEASE_NEW = "  cleanup:\n  g_free (c545d_ci_manifest_scratch);\n  if (packages_iterator)\n"

def replace_once(s: str, old: str, new: str) -> str:
    if s.count(old) != 1:
        raise ValueError("manifest_source_anchor_missing_or_duplicated")
    return s.replace(old,new,1)

def patch(src: str) -> str:
    if src.count("g_win32_package_parser_enum_packages (") != 1:
        raise ValueError("package_enumeration_function_scope_changed")
    # Prevent accidental scope change if the parser becomes async. Caller
    # parses every package synchronously before advancing the iterator.
    start=src.index("g_win32_package_parser_enum_packages (")
    stop=src.find("\nstatic gboolean\nparse_manifest_file (",start)
    if stop < 0:
        raise ValueError("parser_scope_missing")
    sub=src[start:stop]
    if sub.count("parse_manifest_file (sax);") != 1:
        raise ValueError("manifest_parser_invocation_scope_changed")
    # Early diagnostic-skip branches also call MoveNext: the LAST call is
    # the normal loop continuation after the synchronous XML parse.\n    if (sub.index("parse_manifest_file (sax);") > sub.rindex("IIterator_MoveNext (packages_iterator")):
        raise ValueError("manifest_parser_no_longer_synchronous")
    for old,new in ((DECL,DECL_NEW),(ALLOC,ALLOC_NEW),
                    (PKG_RELEASE,PKG_RELEASE_NEW),
                    (SCAN_RELEASE,SCAN_RELEASE_NEW)):
        # Restrict changes to the exact enum function for fail-closed safety.
        if sub.count(old) != 1:
            raise ValueError("unexpected_candidate_manifest_lifetime_anchor")
        sub=replace_once(sub,old,new)
    if sub.count("g_free (c545d_ci_manifest_scratch);") != 1:
        raise ValueError("scan_cleanup_unbalanced")
    if sub.count("g_realloc_n (") != 1:
        raise ValueError("scratch_growth_not_unique")
    return src[:start]+sub+src[stop:]

def selftest() -> None:
    s=("g_win32_package_parser_enum_packages (\n{\n"+
       DECL+"  for (;;) {\n"
       "      wchar_t *manifest_filename = NULL;\n"
       +ALLOC+"      parse_manifest_file (sax);\n"
       "      hr = IIterator_MoveNext (packages_iterator, &has_current);\n"
       "      package_cleanup:\n"+PKG_RELEASE+
       "    }\n"+SCAN_RELEASE+"  return result;\n}\n"
       "\nstatic gboolean\nparse_manifest_file (\n")
    p=patch(s)
    assert p.count("g_realloc_n (")==1
    assert p.count("g_free (c545d_ci_manifest_scratch);")==1
    assert p.count("g_clear_pointer (&manifest_filename, g_free);")==0
    cases=[
        s.replace(DECL,""),
        s.replace(ALLOC,""),
        s.replace(ALLOC,ALLOC+ALLOC),
        s.replace(PKG_RELEASE,""),
        s.replace(SCAN_RELEASE,""),
        s.replace("parse_manifest_file (sax);",""),
        s.replace("parse_manifest_file (sax);\n      hr = IIterator_MoveNext (packages_iterator, &has_current);",
                  "hr = IIterator_MoveNext (packages_iterator, &has_current);\n      parse_manifest_file (sax);"),
    ]
    for bad in cases:
        try:
            patch(bad)
        except ValueError:
            continue
        raise AssertionError("negative source fixture erroneously accepted")
    print("C545D_MANIFEST_SCRATCH_SELFTEST_PASS,negative=7,positive=1,"
          "real_host_untouched=1")

def main() -> None:
    if sys.argv[1:]==["--selftest"]:
        selftest();return
    if len(sys.argv)!=2:
        raise SystemExit("usage: script --selftest OR script <disposable gwin32packageparser.c>")
    path=Path(sys.argv[1])
    original=path.read_bytes()
    crlf=b"\r\n" in original
    modified=patch(original.decode("utf-8").replace("\r\n","\n"))
    if modified.encode("utf-8")==original:
        raise ValueError("patch_made_no_change")
    path.write_bytes(modified.replace("\n","\r\n").encode("utf-8") if crlf else modified.encode("utf-8"))
    print("C545D_MANIFEST_SCRATCH_CANDIDATE_SOURCE_PASS,"
          "per_package_alloc_reused_within_scan=1,scan_cleanup=1,"
          "source_only=1,Windows10_recorder_untested=1")

if __name__=="__main__":
    main()
