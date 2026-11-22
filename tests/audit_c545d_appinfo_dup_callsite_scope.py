#!/usr/bin/env python3
"""Read-only GLib 2.82.4 Win32 GAppInfo duplication callsite-scope audit.

This is a *negative direct-call* source audit, NOT proof of absence of
runtime dispatch, GStreamer plugin/dynamic symbol resolution or a surviving
heap owner. No raw ETW/UMDH files are fetched. Only bounded source files
that are included in the recorder launcher and two already used GIO probes
are checked. The g_app_info_get_all() diagnostic route is NOT g_app_info_dup().

Never conclude that the unrelated GAppInfo dup buffer-corruption fix is
responsible for or fixes the user's PrivateUsage growth without a real
callsite and outstanding-allocation evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

LAUNCH_FILES = (
    "Record.ps1", "RecordGUIWorker.ps1", "C545D_App.ps1",
    "C545D_SettingsBridge.ps1", "CommonSettings.ps1",
    "C545D_Start.vbs", "src/C545D.Launcher/Program.cs",
    "src/C545D.Launcher/RecorderForm.cs",
    "native/sei_filter/gstc545dsei.c",
)
PROBES = (
    "tests/gio_appinfo_key_handle_probe.c",
    "tests/gio_appinfo_umdh_gate_probe.c",
    "tests/gio_appinfo_public_api_regression.c",
    "tests/gio_appinfo_displayname_snapshot.c",
)
CALL = re.compile(r"\bg_app_info_dup\s*\(")
LIST = re.compile(r"\bg_app_info_get_all\s*\(")
DUP_DEF = "g_win32_app_info_dup (GAppInfo *appinfo)"
NEW_DEF = "g_win32_app_info_new_from_app (GWin32AppInfoApplication *app,"
ALL_DEF = "g_app_info_get_all_impl (void)"
PUB = "iface->dup = g_win32_app_info_dup;"


def source_region(text: str, start: str, stop: str) -> str:
    if text.count(start) != 1:
        raise ValueError("upstream_source_signature_ambiguous")
    i = text.index(start)
    j = text.find(stop, i + len(start))
    if j < 0:
        raise ValueError("upstream_source_function_order_changed")
    return text[i:j]


def audit(launch: dict[str, str], probes: dict[str, str], upstream: str) -> list[str]:
    if set(launch) != set(LAUNCH_FILES) or set(probes) != set(PROBES):
        raise ValueError("missing_or_extra_project_source")
    if not all(launch.values()) or not all(probes.values()):
        raise ValueError("empty_project_source")
    for path, text in {**launch, **probes}.items():
        if len(text) > 1_000_000:
            raise ValueError("unbounded_source")
        # This audit only rules out an explicit call in the inspected files.
        if CALL.search(text):
            raise ValueError("direct_dup_call_found_in_" + path.replace("/", "_"))
    for path in PROBES:
        if not LIST.search(probes[path]):
            raise ValueError("original_GIO_probe_no_longer_calls_get_all")
    if upstream.count(PUB) != 1:
        raise ValueError("upstream_GAppInfo_vtable_disconnected")
    body = source_region(upstream, NEW_DEF,
                         "\nstatic GAppInfo *\ng_win32_app_info_dup (")
    if "g_win32_app_info_new_from_app" not in body or (
            "new_info->supported_types = g_new (gchar *, i + 1)" not in body):
        raise ValueError("unrecognised_appinfo_constructor")
    dup = source_region(upstream, DUP_DEF,
                        "\nstatic gboolean\ng_win32_app_info_equal (")
    if dup.count("for (i = 0; info->supported_types[i]; i++)") != 2 or (
        "        break;" not in dup or
        "new_info->supported_types = g_new (gchar *, i + 1);" not in dup
    ):
        raise ValueError("different_upstream_dup_copy_path")
    apps = source_region(upstream, ALL_DEF,
                         "\nGList *\ng_app_info_get_all_for_type_impl (")
    if ("g_win32_app_info_new_from_app (apps_i->data, NULL)" not in apps or
            "g_win32_app_info_dup (" in apps or
            "g_app_info_dup (" in apps):
        raise ValueError("upstream_get_all_route_not_simple_constructor")
    return [
        "C545D_APPINFO_DUP_CALLSITE_SCOPE_PASS,"
        "recording_launcher_files=9,diagnostic_probe_files=4,"
        "production_explicit_dup_calls=0,probe_explicit_dup_calls=0,"
        "probe_get_all_present=4,get_all_creates_new_info=1,"
        "dup_requires_separate_iface_dispatch=1,"
        "dynamic_sdk_callers_excluded=1,"
        "runtime_call_frequency_unobserved=1,"
        "ETW_UMDH_function_level_provenance_unavailable=1,"
        "residual_PrivateUsage_causality_unproven=1,"
        "new_windows_runs=0,real_recorder_untested=1"
    ]


def selftest() -> None:
    launch = {p: "/* recorder source */\n" for p in LAUNCH_FILES}
    probes = {p: "g_app_info_get_all();\n" for p in PROBES}
    upstream = (
        NEW_DEF + "\n{\nnew_info->supported_types = g_new (gchar *, i + 1);\n"
        "}\nstatic GAppInfo *\n"
        + DUP_DEF + "\n{\n"
        "for (i = 0; info->supported_types[i]; i++)\n"
        "        break;\n"
        "new_info->supported_types = g_new (gchar *, i + 1);\n"
        "for (i = 0; info->supported_types[i]; i++)\n"
        "}\nstatic gboolean\ng_win32_app_info_equal ("
        "\n" + ALL_DEF + "\n{"
        "\ng_win32_app_info_new_from_app (apps_i->data, NULL)\n"
        "}\nGList *\ng_app_info_get_all_for_type_impl ("
        + "\n" + PUB + "\n"
    )
    assert len(audit(launch, probes, upstream)) == 1
    failures = [
        ({**launch, LAUNCH_FILES[0]:"g_app_info_dup (x);"}, probes, upstream),
        (launch, {**probes, PROBES[0]:"g_app_info_dup (a);"}, upstream),
        (launch, {**probes, PROBES[0]:"g_app_info_get_default_for_type (x);"}, upstream),
        (launch, probes, upstream.replace(PUB, "iface->dup = other;")),
        (launch, probes, upstream.replace("        break;", "        continue;")),
        (launch, probes, upstream.replace(
            "g_win32_app_info_new_from_app (apps_i->data, NULL)",
            "g_win32_app_info_dup (apps_i->data)")),
        ({p:v for p,v in launch.items() if p != LAUNCH_FILES[-1]}, probes, upstream),
    ]
    for one, two, three in failures:
        try:
            audit(one, two, three)
        except ValueError:
            continue
        raise AssertionError("source drift or direct call falsely accepted")
    print("C545D_APPINFO_DUP_CALLSITE_SCOPE_SELFTEST_PASS,"
          "positive=1,negative=7,uninspected_SDK_plugin_calls=unknown,"
          "windows_runs=0,host_untouched=1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--upstream", type=Path)
    args=parser.parse_args()
    try:
        if args.selftest:
            selftest()
        else:
            if not args.upstream:
                parser.error("--upstream required")
            print("\n".join(audit(
                {p:(args.repo / p).read_text(encoding="utf-8-sig") for p in LAUNCH_FILES},
                {p:(args.repo / p).read_text(encoding="utf-8-sig") for p in PROBES},
                args.upstream.read_text(encoding="utf-8-sig")
            )))
    except (ValueError, OSError):
        print("C545D_APPINFO_DUP_CALLSITE_SCOPE_FAIL,"
              "reason=SOURCE_MISMATCH_OR_DIRECT_CALL,"
              "no_runtime_owner_inferred=1")
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
