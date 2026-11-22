#!/usr/bin/env python3
"""Fail-closed, source-only audit of GStreamer 1.28.8 RTSP TEARDOWN error leak.

Official 1.28.9 commit bcae292 adds GstRTSPMessage response unref in the
send_error branch of gst_rtspsrc_close(). Only verifies an isolated source
candidate. NOT a runnable recorder patch, runtime leak measurement, or
permission to replace GStreamer files on a Windows recording host.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

OLD_BLOB = "2203fb5a5d6d100d1a0a6ec566a7a4adb1cce996"
FIX_BLOB = "19511e0b53e9a77d59ae032a3d1df1dd2720749f"
FUNC = "\ngst_rtspsrc_close (GstRTSPSrc * src, gboolean async, gboolean only_close)\n{"
OLD = ("send_error:\n  {\n"
       "    gst_rtsp_message_unset (&request);\n"
       "\n"
       "    if (res == GST_RTSP_EEOF)\n")
FIX = ("send_error:\n  {\n"
       "    gst_rtsp_message_unset (&request);\n"
       "    gst_rtsp_message_unset (&response);\n"
       "\n"
       "    if (res == GST_RTSP_EEOF)\n")


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def close_body(source: str) -> str:
    if source.count(FUNC) != 1:
        raise ValueError("close_function_anchor_not_unique")
    start = source.index(FUNC)
    stop = source.find("\nnot_supported:\n", start + len(FUNC))
    if stop < 0:
        raise ValueError("not_supported_label_missing")
    end = source.find("\n}\n", stop)
    if end < 0:
        raise ValueError("close_function_end_missing")
    body = source[start:end + 3]
    if body.count("send_error:") != 1 or body.count("not_supported:") != 1:
        raise ValueError("error_labels_not_unique")
    return body


def audit(old: str, fixed: str) -> str:
    old_func = close_body(old)
    fix_func = close_body(fixed)
    if old_func.count(OLD) != 1 or old.count(OLD) != 1:
        raise ValueError("old_teardown_error_anchor_mismatch")
    if fix_func.count(FIX) != 1 or fixed.count(FIX) != 1:
        raise ValueError("upstream_fixed_error_anchor_mismatch")
    if old_func.count("gst_rtsp_message_unset (&response);") != 1:
        # The success path already clears response, error path did not.
        raise ValueError("old_response_cleanup_scope_changed")
    if fix_func.count("gst_rtsp_message_unset (&response);") != 2:
        raise ValueError("new_response_cleanup_scope_changed")
    proposed = old.replace(OLD, FIX, 1)
    if close_body(proposed) != fix_func:
        raise ValueError("upstream_close_function_not_identical")
    if proposed == old:
        raise ValueError("patch_not_applied")
    return proposed


def selftest() -> None:
    fixture = (FUNC + "\n  GstRTSPMessage response = { 0 };\n"
               "  gst_rtsp_message_unset (&response);\n"
               + OLD + "      goto close;\n"
               "\nnot_supported:\n  { goto close; }\n}\n")
    good = fixture.replace(OLD, FIX)
    assert audit(fixture, good) == good
    failures = [
        (fixture.replace("gst_rtsp_message_unset (&request);", "broken ();"), good),
        (fixture.replace(OLD, OLD + OLD), good),
        (good, good),
        (fixture, fixture),
        (fixture, good.replace("goto close;", "goto nowhere;", 1)),
        (fixture, good.replace(FIX, FIX + "    gst_rtsp_message_unset (&response);\n")),
        (fixture.replace(FUNC, "\nwrong_function(void)\n{"), good),
    ]
    for a, b in failures:
        try:
            audit(a, b)
        except ValueError:
            continue
        raise AssertionError("source corruption fixture accepted")
    print("C545D_RTSP_TEARDOWN_SOURCE_SELFTEST_PASS,negative=7,positive=1,"
          "new_windows_runs=0,real_recorder_untouched=1")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--old", type=Path)
    p.add_argument("--fixed", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.old or not a.fixed or not a.out:
        p.error("--old --fixed --out required")
    old_bytes, fixed_bytes = a.old.read_bytes(), a.fixed.read_bytes()
    if blob_sha(old_bytes) != OLD_BLOB or blob_sha(fixed_bytes) != FIX_BLOB:
        raise ValueError("upstream_tag_source_blob_changed")
    old = old_bytes.decode("utf-8")
    fixed = fixed_bytes.decode("utf-8")
    proposed = audit(old, fixed)
    if a.out.resolve() in (a.old.resolve(), a.fixed.resolve()):
        raise ValueError("refuse_to_overwrite_upstream_source")
    a.out.write_text(proposed, encoding="utf-8")
    print("C545D_RTSP_TEARDOWN_SOURCE_AUDIT_PASS,"
          "gst_old=1.28.8,gst_fixed=1.28.9,"
          "upstream_commit=bcae292,one_error_branch_response_unset=1,"
          "upstream_close_function_equal=1,SDK_upgrade_performed=0,"
          "allocation_owner_proven=0,normal_stream_leak_fixed=0,"
          "Windows10_recorder_untested=1")


if __name__ == "__main__":
    main()
