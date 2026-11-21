#!/usr/bin/env python3
"""CI-only isolated candidate for GLib 2.82.4 UWP parser COM init balance.

Guard CoUninitialize after successful CoInitializeEx, including S_FALSE.
Do not apply this patch to the user-host DLL or production GLib without
Windows build, correctness, and recorder compatibility qualification.
This is a *failure-path correctness* issue; NOT an attributed memory leak.
"""
import sys
from pathlib import Path


def replace_once(s: str, before: str, after: str, description: str) -> str:
    count = s.count(before)
    if count != 1:
        raise ValueError(f"{description}: source anchor count={count} (expected 1)")
    return s.replace(before, after, 1)


def patch(s: str) -> str:
    s = replace_once(
        s,
        "  HRESULT hr;\n  HSTRING packagemanager_name = NULL;",
        "  HRESULT hr;\n  /* CI-only: do not uninitialize COM after failed initialization. */\n"
        "  HRESULT c545d_ci_com_init_result = E_FAIL;\n"
        "  HSTRING packagemanager_name = NULL;",
        "per-call COM state")
    s = replace_once(
        s,
        "  hr = CoInitializeEx (NULL, COINIT_APARTMENTTHREADED);\n",
        "  hr = CoInitializeEx (NULL, COINIT_APARTMENTTHREADED);\n"
        "  c545d_ci_com_init_result = hr;\n",
        "record exact original apartment HRESULT")
    s = replace_once(
        s, "  CoUninitialize ();\n",
        "  if (c545d_ci_com_init_result == S_OK ||\n"
        "      c545d_ci_com_init_result == S_FALSE)\n"
        "    CoUninitialize ();\n",
        "balance only successful COM initializations")
    return s


def selftest() -> None:
    sample = ("  HRESULT hr;\n  HSTRING packagemanager_name = NULL;"
              "\n  hr = CoInitializeEx (NULL, COINIT_APARTMENTTHREADED);\n"
              "  CoUninitialize ();\n")
    changed = patch(sample)
    assert "c545d_ci_com_init_result = hr;" in changed
    assert "c545d_ci_com_init_result == S_FALSE" in changed
    for bad in (sample.replace("  CoUninitialize ();\n", ""),
                sample.replace("  CoUninitialize ();\n",
                               "  CoUninitialize ();\n  CoUninitialize ();\n"),
                sample.replace("HRESULT hr;", "int hr;")):
        try:
            patch(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("drifted source was accepted")
    print("C545D_COM_BALANCE_SOURCE_SELFTEST_PASS,rejects=3,Windows_runner=0")


def main() -> None:
    if sys.argv[1:] == ["--selftest"]:
        selftest()
        return
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_glib_2824_parser_com_balance_ci.py <disposable-packageparser.c>")
    p = Path(sys.argv[1])
    raw = p.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    new = patch(raw.decode("utf-8").replace("\r\n", "\n"))
    p.write_bytes(new.replace("\n", eol).encode("utf-8"))
    print("C545D_COM_BALANCE_CI_SOURCE_PATCHED,only_disposable_source=1,"
          "real_recorder_modified=0,Windows_build_done=0")


if __name__ == "__main__":
    main()
