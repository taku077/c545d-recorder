#!/usr/bin/env python3
"""Pin GLib 2.82.4 AppInfo graph/WinRT package-parser OWNERSHIP semantics.

Runs on CI Ubuntu using exact public upstream sources and copies of two
candidate patch scripts. This is source review, NOT a new heap/Windows
measurement, nor a demonstration that the remaining 360B block is freed.

A separate diagnostic-only COM failure-path candidate must never be
silently integrated with the production GIO/recorder pipeline.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOTS = ("apps_by_id", "apps_by_exe", "fake_apps", "urls",
         "extensions", "handlers")
RELEASES = (
    "IStorageItem_Release (storage_item)",
    "IUnknown_Release (package_install_location)",
    "IPackage2_Release (ipackage2)",
    "IPackage_Release (ipackage)",
    "IUnknown_Release (item)",
    "IPackageId_Release (ipackageid)",
    "IIterator_Release (packages_iterator)",
    "IIterable_Release (packages_iterable)",
    "IPackageManager_Release (pm)",
    "IInspectable_Release (ii_pm)",
)
HSTRINGS = ("path", "package_family", "display_name",
            "name", "full_name")
SAX = ("application_usermodelid", "supported_extensions", "supported_verbs",
       "supported_extgroups", "supported_protocols")


def section(source: str, start: str, end: str) -> str:
    if source.count(start) != 1:
        raise ValueError(f"source start anchor count incorrect: {start!r}")
    a = source.index(start)
    b = source.find(end, a + len(start))
    if b < 0:
        raise ValueError(f"source end anchor absent or unordered: {end!r}")
    return source[a:b]


def order(s: str, *steps: str) -> None:
    pos = 0
    for step in steps:
        at = s.find(step, pos)
        if at < 0:
            raise ValueError(f"missing or out of order: {step!r}")
        pos = at + len(step)


def audit(original: str, weak: str, package: str, balanced: str) -> list[str]:
    original_shell = section(original, "struct _GWin32AppInfoShellVerb {",
                             "struct _GWin32AppInfoFileExtension {")
    changed_shell = section(weak, "struct _GWin32AppInfoShellVerb {",
                            "struct _GWin32AppInfoFileExtension {")
    if "GWin32AppInfoApplication *app;" not in original_shell or (
            "GWeakRef app;" not in changed_shell or
            "GWin32AppInfoApplication *app;" in changed_shell):
        raise ValueError("ShellVerb backref owner did not change to weak")
    for token in (
        "g_weak_ref_init (&self->app, NULL)",
        "g_weak_ref_clear (&verb->app)",
        "g_weak_ref_get (&verb->app)",
        "g_weak_ref_set (&shverb->app, app_rec)",
        "g_weak_ref_set (&handler_verb->app, app)",
        "g_win32_appinfo_shell_verb_finalize",
    ):
        if token not in weak:
            raise ValueError("missing weak reference lifecycle: " + token)
    if "g_clear_object (&shverb->app);" in weak:
        raise ValueError("strong application reference reintroduced")
    # public GAppInfo retains its own strong refs; these are dropped during
    # finalize. Weak backrefs do NOT replace caller ownership of public refs.
    public = section(weak, "static void\ng_win32_app_info_finalize (",
                     "static void\ng_win32_app_info_class_init (")
    for token in ("g_clear_object (&info->app)", "g_clear_object (&info->handler)"):
        if token not in public:
            raise ValueError("public GAppInfo finalize lost owned reference: " + token)
    if "new_info->app = g_object_ref (app);" not in weak:
        raise ValueError("public GAppInfo lost caller-independent ownership")

    rebuild = section(weak, "static void\nupdate_registry_data (void)",
                      "static void\nwatch_keys (void);")
    for name in ROOTS:
        dispose = f"g_clear_pointer (&{name}, g_hash_table_destroy);"
        new = re.search(
            rf"\b{name}\s*=\s*g_hash_table_new_full\s*\([^;]+g_object_unref\)",
            rebuild, flags=re.S)
        if rebuild.count(dispose) != 1 or new is None:
            raise ValueError(f"{name}: root destroy/rebuild missing")
        if rebuild.index(dispose) > new.start():
            raise ValueError(f"{name}: old root overwritten before release")
    order(rebuild, "uwp_handler_table =", "g_win32_package_parser_enum_packages",
          "read_uwp_handler_info ();", "g_hash_table_unref (uwp_handler_table);")
    if rebuild.count("g_hash_table_unref (uwp_handler_table);") != 1:
        raise ValueError("temporary UWP map unref not unique")
    # Note: the static pointer is intentionally not reset after unref in
    # upstream 2.82.4. In the current serialized worker, it is replaced
    # before the following use; this is not evidence of accumulating tables.

    handler = section(weak, "g_win32_appinfo_handler_dispose (",
                      "static void\ng_win32_appinfo_file_extension_dispose (")
    app = section(weak, "g_win32_appinfo_application_dispose (",
                  "static const gchar *\ng_win32_appinfo_application_get_some_name (")
    for token in ("g_clear_object (&handler->key)",
                  "g_clear_object (&handler->icon)",
                  "g_clear_pointer (&handler->verbs, g_ptr_array_unref)"):
        if token not in handler:
            raise ValueError("handler release missing: " + token)
    for token in ("g_clear_pointer (&app->verbs, g_ptr_array_unref)",
                  "g_clear_pointer (&app->supported_urls, g_hash_table_destroy)",
                  "g_clear_pointer (&app->supported_exts, g_hash_table_destroy)"):
        if token not in app:
            raise ValueError("app releases missing: " + token)

    winrt = section(package, "g_win32_package_parser_enum_packages (",
                    "static gboolean\nparse_manifest_file")
    package_cleanup = section(winrt, "      package_cleanup:", "  cleanup:")
    final_cleanup = section(winrt, "  cleanup:", "  return result;")
    for name in HSTRINGS:
        if f"LoadedWindowsDeleteString ({name})" not in package_cleanup:
            raise ValueError("HSTRING release missing: " + name)
    for token in RELEASES:
        if token not in (package_cleanup + final_cleanup):
            raise ValueError("COM interface release missing: " + token)
    for token in ("g_clear_pointer (&manifest_filename, g_free)",
                  "IStorageItem_Release (storage_item)",
                  "IPackageId_Release (ipackageid)"):
        if token not in package_cleanup:
            raise ValueError("per-package cleanup lost: " + token)
    xml = section(package, "static gboolean\nparse_manifest_file (",
                  "static gboolean\nxml_parser_get_current_state (")
    for name in SAX:
        token = f"g_clear_pointer (&sax->{name},"
        if token not in xml:
            raise ValueError("SAX auxiliary state cleanup missing: " + name)
    for token in ("IXmlReader_Release (xml_reader)", "IStream_Release (file_stream)"):
        if token not in xml:
            raise ValueError("XML COM stream cleanup missing: " + token)

    # Official 2.82.4 calls CoUninitialize unconditionally at cleanup,
    # including jumps before CoInitializeEx and RPC_E_CHANGED_MODE.
    # Check the independent diagnostic-only candidate fixes *only* this.
    order(winrt,
          "CoInitializeEx (NULL, COINIT_APARTMENTTHREADED)",
          "if (hr != S_OK && hr != S_FALSE)",
          "  cleanup:",
          "  CoUninitialize ();")
    if "c545d_ci_com_init_result" in package:
        raise ValueError("wrong original WinRT parser supplied")
    if balanced.count("c545d_ci_com_init_result = hr;") != 1:
        raise ValueError("CI candidate did not capture exact COM init result")
    if balanced.count("c545d_ci_com_init_result == S_OK") != 1 or (
            balanced.count("c545d_ci_com_init_result == S_FALSE") != 1):
        raise ValueError("candidate missed S_OK/S_FALSE balance")
    if re.search(r"(?m)^  CoUninitialize \(\);$", section(
            balanced, "  cleanup:", "  return result;")):
        raise ValueError("candidate still contains unconditional COM uninit")
    if "    CoUninitialize ();" not in balanced:
        raise ValueError("guarded CoUninitialize missing")
    results = [
        "C545D_GIO_GRAPH_BACKREF_AUDIT,glib=2.82.4,weak_ref=1,"
        "weak_init_get_set_clear=1,public_info_owned_refs_release=1,"
        "allocation_stack_attributed=0,CI_only=1",
        "C545D_GIO_GRAPH_ROOT_AUDIT,old_owned_tables_destroyed=6,"
        "rebuilt_owned_tables=6,per_scan_uwp_table_unref=1,"
        "root_reference_identity_unknown=1,CI_only=1",
        "C545D_GIO_WINRT_CLEANUP_AUDIT,hstrings_release=5,"
        "COM_interfaces_release=10,SAX_members_release=5,"
        "WinRT_allocation_owner_unproven=1,CI_only=1",
        "C545D_GIO_COM_FAILURE_PATH_AUDIT,upstream_unconditional_uninit=1,"
        "CI_candidate_balanced_success_only=1,MTA_failure_path_risk=1,"
        "not_current_memory_leak_cause=1,Windows_build_untested=1,CI_only=1",
        "C545D_GIO_GRAPH_SOURCE_AUDIT_PASS,source_tag=2.82.4,"
        "no_runtime_or_host_changed=1,zero_leak_proven=0,"
        "new_windows_runs=0",
    ]
    return results


def selftest() -> None:
    order("X--Y--Z", "X", "Y", "Z")
    bad = 0
    for data in ("X--Z--Y", "X--Y", "Y--Z"):
        try:
            order(data, "X", "Y", "Z")
        except ValueError:
            bad += 1
    if bad != 3:
        raise AssertionError("ordering corrupt-fixture not rejected")
    print("C545D_GIO_GRAPH_SELFTEST_PASS,rejects=3,new_windows_runs=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    for name in ("original", "weak", "package", "balanced"):
        ap.add_argument("--" + name, type=Path)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if any(getattr(args, name) is None
           for name in ("original", "weak", "package", "balanced")):
        ap.error("--original, --weak, --package and --balanced required")
    source = [getattr(args, name).read_text(encoding="utf-8")
              for name in ("original", "weak", "package", "balanced")]
    for result in audit(*source):
        print(result)


if __name__ == "__main__":
    main()
