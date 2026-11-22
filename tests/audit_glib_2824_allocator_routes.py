#!/usr/bin/env python3
"""GLib 2.82.4 default-heap attribution guard (SOURCE-ONLY).

The Win32 process default heap is a *shared endpoint*, not a proof of
GLib, GIO, WinRT, or a given allocation callsite. Verify GLib system
allocator delegation and retired slice allocator using EXACT pinned
upstream 2.82.4 sources in disposable Ubuntu CI. No new Windows runs.
Never use old g_mem_set_vtable to profile: it is a no-op stub.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def function(src: str, name: str) -> str:
    sig = re.compile(r"(?m)^" + re.escape(name) + r"\s*\(")
    hits = list(sig.finditer(src))
    if len(hits) != 1:
        raise ValueError(f"pinned allocator function {name} not unique")
    begin = src.find("{", hits[0].end())
    if begin < 0 or begin - hits[0].end() > 220:
        raise ValueError(f"function {name} has no nearby body")
    nesting = 0
    for i in range(begin, len(src)):
        if src[i] == "{":
            nesting += 1
        elif src[i] == "}":
            nesting -= 1
            if nesting == 0:
                return src[begin:i + 1]
    raise ValueError(f"unterminated function {name}")


def required_once(body: str, expr: str, name: str) -> None:
    if body.count(expr) != 1:
        raise ValueError(f"{name} doesn't follow pinned allocator path {expr}")


def audit(mem: str, slice_src: str) -> list[str]:
    implementations = {
        "g_malloc": (mem, "mem = malloc (n_bytes);"),
        "g_malloc0": (mem, "mem = calloc (1, n_bytes);"),
        "g_realloc": (mem, "newmem = realloc (mem, n_bytes);"),
        "(g_free)": (mem, "free (mem);"),
        "g_slice_alloc": (slice_src, "mem = g_malloc (mem_size);"),
        "g_slice_free1": (slice_src, "g_free_sized (mem_block, mem_size);"),
        "g_slice_free_chain_with_offset": (
            slice_src, "g_free_sized (current, mem_size);"),
    }
    for name, (src, call) in implementations.items():
        required_once(function(src, name), call, name)
    sized = function(mem, "g_free_sized")
    required_once(sized, "#ifdef HAVE_FREE_SIZED", "g_free_sized")
    required_once(sized, "free_sized (mem, size);", "g_free_sized")
    required_once(sized, "free (mem);", "g_free_sized")
    required_once(function(mem, "g_mem_is_system_malloc"),
                  "return TRUE;", "system malloc")
    old_vtable = function(mem, "g_mem_set_vtable")
    required_once(old_vtable,
                  'g_warning (G_STRLOC ": custom memory allocation vtable not supported");',
                  "retired allocator hook")
    if "g_mem_profile ()" in old_vtable:
        raise ValueError("profiling callback unexpectedly enabled")
    if "Since GLib 2.76 this always uses the system malloc()" not in slice_src:
        raise ValueError("removed custom slice allocator version not pinned")
    return [
        "C545D_GLIB2824_ALLOCATOR_ROUTE,glib_source_tag=2.82.4,"
        "g_malloc=libc_malloc,g_malloc0=libc_calloc,"
        "g_realloc=libc_realloc,g_free=libc_free,"
        "g_slice_alloc=g_malloc,g_slice_free1=g_free_sized,"
        "g_slice_chain_free=g_free_sized,glib_custom_allocator_hook=stub",
        "C545D_GLIB2824_ALLOCATOR_INFERENCE,"
        "glib_gio_can_use_system_CRT_allocator=1,"
        "windows_default_heap_allocation_owner_identified=0,"
        "winrt_COM_memory_is_covered_by_glib_hooks_proven=0,"
        "slice_specific_cache_exists_proven=0,"
        "no_proof_of_private_commit_allocation_site=1,"
        "no_assertion_of_256_plateau=1",
        "C545D_GLIB2824_ALLOCATOR_ROUTE_PASS,"
        "source_tag=2.82.4,real_device_untested=1,"
        "new_windows_runs=0,recorder_dll_unchanged=1",
    ]


def selftest() -> None:
    names = {
        "g_malloc": "mem = malloc (n_bytes);",
        "g_malloc0": "mem = calloc (1, n_bytes);",
        "g_realloc": "newmem = realloc (mem, n_bytes);",
        "(g_free)": "free (mem);",
        "g_free_sized": (
            "#ifdef HAVE_FREE_SIZED\nfree_sized (mem, size);\n"
            "#else\nfree (mem);\n#endif"),
        "g_mem_is_system_malloc": "return TRUE;",
        "g_mem_set_vtable": (
            'g_warning (G_STRLOC ": custom memory allocation vtable not supported");'),
    }
    mem = "\n".join(f"void\n{name} (void)\n{{\n{body}\n}}\n"
                    for name, body in names.items())
    slices = {
        "g_slice_alloc": "mem = g_malloc (mem_size);",
        "g_slice_free1": "g_free_sized (mem_block, mem_size);",
        "g_slice_free_chain_with_offset": "g_free_sized (current, mem_size);",
    }
    sl = ("/* Since GLib 2.76 this always uses the system malloc() */\n" +
          "\n".join(f"void\n{name} (void)\n{{\n{body}\n}}"
                    for name, body in slices.items()))
    assert len(audit(mem, sl)) == 3
    defects = [
        (mem.replace("malloc (n_bytes)", "HeapAlloc(heap, 0, n_bytes)"), sl),
        (mem.replace("calloc (1, n_bytes)", "custom_calloc (n_bytes)"), sl),
        (mem.replace("realloc (mem, n_bytes)", "other_realloc (mem, n_bytes)"), sl),
        (mem.replace("return TRUE;", "return FALSE;"), sl),
        (mem.replace("custom memory allocation vtable not supported", "vtable enabled"), sl),
        (mem.replace("free_sized (mem, size)", "fake_free (mem)"), sl),
        (mem, sl.replace("g_malloc (mem_size)", "custom_slice_pool (mem_size)")),
        (mem, sl.replace("g_free_sized (mem_block, mem_size)",
                         "custom_slice_free (mem_block)")),
        (mem, sl.replace("Since GLib 2.76", "Since GLib 1.76")),
    ]
    for m, s in defects:
        try:
            audit(m, s)
        except ValueError:
            pass
        else:
            raise AssertionError("unverified allocator owner path accepted")
    print("C545D_GLIB2824_ALLOCATOR_ROUTE_SELFTEST_PASS,"
          "positive_cases=1,negative_cases=9,"
          "windows_runs=0,user_host_untouched=1")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--glib-root", type=Path)
    args = p.parse_args()
    if args.selftest:
        selftest()
        return
    if args.glib_root is None:
        p.error("--glib-root is required")
    root = args.glib_root / "glib"
    for line in audit(
        (root / "gmem.c").read_text(encoding="utf-8"),
        (root / "gslice.c").read_text(encoding="utf-8")
    ):
        print(line)


if __name__ == "__main__":
    main()
