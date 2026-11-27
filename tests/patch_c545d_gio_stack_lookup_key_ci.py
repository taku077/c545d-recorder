#!/usr/bin/env python3
"""CI-only ASCII stack lookup key experiment; never modify production runtime.

Apply AFTER the existing DisplayName cache and event bridge overlays.
Keep stored UTF-8 key ownership, exact case-sensitive equality, owned UTF-16
result and both native generation polls. Non-ASCII/long input uses GLib.
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

HELPER = r'''static gboolean
c545d_ascii_stack_key (const gunichar2 *input, gchar out[128])
{
  guint i;
  if (input == NULL)
    return FALSE;
  for (i = 0; i < 128; i++)
    {
      gunichar2 ch = input[i];
      if (ch > 0x7f)
        return FALSE;
      out[i] = (gchar) ch;
      if (ch == 0)
        return TRUE;
    }
  return FALSE;
}
'''
ANCHOR = "static gunichar2 *\nc545d_cache_display_lookup (const wchar_t *full_name)"
OLD = """  gchar *key = g_utf16_to_utf8 ((const gunichar2 *) full_name, -1,
                                NULL, NULL, NULL);
  if (key == NULL)
    return NULL;"""
NEW = """  gchar stack_key[128];
  gchar *owned_key = NULL;
  const gchar *key;
  if (c545d_ascii_stack_key ((const gunichar2 *) full_name, stack_key))
    key = stack_key;
  else
    {
      owned_key = g_utf16_to_utf8 ((const gunichar2 *) full_name, -1,
                                   NULL, NULL, NULL);
      key = owned_key;
    }
  if (key == NULL)
    return NULL;"""
FREE = """  g_free (key);
  if (result != NULL && !c545d_bridge_epoch_still_valid (before))"""
def once(s, a, b):
    if s.count(a) != 1:
        raise ValueError("stack_lookup_anchor")
    return s.replace(a, b, 1)

def patch(s):
    if "c545d_ascii_stack_key" in s:
        raise ValueError("already_patched")
    start = s.index(ANCHOR)
    end = s.index("\nstatic void\nc545d_cache_display_store", start)
    body = s[start:end]
    if body.count("c545d_bridge_read_epoch ()") != 1 or body.count("c545d_bridge_epoch_still_valid (before)") != 1 or body.count("if (!before.valid)") != 1:
        raise ValueError("bridge_race_guard")
    body = once(body, OLD, NEW)
    body = once(body, FREE, FREE.replace("g_free (key)", "g_free (owned_key)"))
    # Do not touch store, invalidation, or any other lookup code.
    return s[:start] + HELPER + "\n" + body + s[end:]

def selftest():
    fixture = ANCHOR + "\n{\n  C545DBridgeEpoch before = c545d_bridge_read_epoch ();\n  if (!before.valid) return NULL;\n" + OLD + "\n" + FREE + "\n    g_clear_pointer (&result, g_free);\n  return result;\n}\nstatic void\nc545d_cache_display_store (void) { /* unchanged */ }\n"
    got = patch(fixture)
    if got.count("c545d_bridge_read_epoch ()") != 1 or got.count("c545d_bridge_epoch_still_valid (before)") != 1 or got.count("g_free (owned_key)") != 1 or not got.endswith(fixture[fixture.index("\nstatic void"):]):
        raise ValueError("ownership_guard")
    for bad in (got, fixture.replace("c545d_bridge_epoch_still_valid (before)", "bad ()", 1), fixture.replace(OLD, "")):
        try:
            patch(bad)
        except ValueError:
            continue
        raise ValueError("bad_patch_accepted")
    # Compile and execute the EXACT C helper, not a Python reimplementation.
    c = r'''#include <stdint.h>
#include <string.h>
#include <stddef.h>
typedef uint16_t gunichar2;
typedef char gchar;
typedef unsigned guint;
typedef int gboolean;
#define FALSE 0
#define TRUE 1
''' + HELPER + r'''
int main(void) {
  gunichar2 in[130] = {0};
  gchar out[128];
  unsigned i;
  if (c545d_ascii_stack_key(NULL,out)) return 8;
  if (!c545d_ascii_stack_key(in,out) || out[0]) return 1;
  for (i=1;i<128;i++) {
    in[0]=(gunichar2)i; in[1]=0;
    if (!c545d_ascii_stack_key(in,out) || (unsigned char)out[0]!=i || out[1]) return 2;
  }
  for (i=0;i<127;i++) in[i]='A';
  in[127]=0;
  if (!c545d_ascii_stack_key(in,out) || strlen(out)!=127) return 3;
  in[127]='B'; in[128]=0;
  if (c545d_ascii_stack_key(in,out)) return 4;
  in[0]=0x65e5; in[1]=0;
  if (c545d_ascii_stack_key(in,out)) return 5;
  in[0]=0xd800;
  if (c545d_ascii_stack_key(in,out)) return 6;
  in[0]='A';in[1]='b';in[2]=0;
  if (!c545d_ascii_stack_key(in,out) || strcmp(out,"Ab")) return 7;
  return 0;
}
'''
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "test.c"
        exe = Path(d) / "test"
        src.write_text(c, encoding="utf-8")
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("C545D_STACK_KEY_SELFTEST_PASS,ascii=127,boundary=2,nonascii=2,case=1,empty=1,null=1,negative_patch=3,native_windows=0")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--patch", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
    elif a.patch:
        if a.patch.name != "gwin32packageparser.c" or a.patch.parent.name != "gio":
            raise ValueError("source_name")
        raw = a.patch.read_bytes()
        nl = "\r\n" if b"\r\n" in raw else "\n"
        s = patch(raw.decode("utf-8").replace("\r\n", "\n"))
        a.patch.write_bytes(s.replace("\n", nl).encode("utf-8"))
        print("C545D_STACK_KEY_CI_PATCH_PASS,store_unchanged=1,epoch_guards=2")
    else:
        p.error("mode required")
if __name__ == "__main__":
    main()
