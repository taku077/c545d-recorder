# C545D GLib 2.82.4 active watcher lifetime vs globally closed epoch (2026-11-23 JST)

## Executive finding

**The previous proposed rule “wait until every GIO registry watcher, APC and worker is closed before measuring a stable 24/7 recorder” is *not a valid default*.** Pinned GLib AppInfo actively maintains registry subscriptions across updates. The registered watchers can remain alive while no update worker is running. Forcing all remaining registry subscriptions to close or DLLs to unload mid-recording is prohibited. Separate **stable subscribed baseline** from **complete terminal producer closure**.

This is directly sourced, not a theoretical account:

- GNOME official **GLib 2.82.4** [`gio/gwin32appinfo.c`](https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32appinfo.c), Git blob `f2b9cf346a18e4a525885fbd49f8bf77dc973bb5`: 8 possible watched root keys; `keys_updated()` first calls `watch_keys()`, increments update counter and queues `g_thread_pool_push`; the AppInfo pool is created with max **1 worker**. `gio_win32_appinfo_init` uses `GET_MODULE_HANDLE_EX_FLAG_PIN` to keep GIO loaded; its `g_cond_wait` responds to the tree-update counter, not a global APC/COM shutdown ack.
- Official [`gio/gwin32registrykey.c`](https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32registrykey.c), Git blob `bd83b38b5ec0de126e94fd3b8b2372c492f0fc5d`: `g_win32_registry_key_watch` retains the key with `g_object_ref` until `key_changed` APC resets its watch state, invokes callback, then `g_object_unref`. The public [`gwin32registrykey.h`](https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32registrykey.h), blob `e2b25da4648c3e842a1d10285a88590c581c15d9`, declares `watch` but **no corresponding public `unwatch` API** in this pinned version. This does not prove there is no possible lower-level internal cancellation mechanism. It *does* make a naïve “invoke GLib unwatch and wait for zero references” solution invalid without source changes and a safety proof.
- The package enumeration in official [`gio/gwin32packageparser.c`](https://github.com/GNOME/glib/blob/2.82.4/gio/gwin32packageparser.c), Git blob `a73dbba642c842606e30e6cf6cf339264fd18e70`, uses a synchronous WinRT iterator, invokes owned XML parsing/notification in that call and `CoUninitialize` before returning. AppInfo's parser/worker boundary can scope **its own enumeration call**, but there is no proof every lower-level process COM cache or APC is globally empty.
- Microsoft [RegNotifyChangeKeyValue docs](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-regnotifychangekeyvalue) distinguish persistent subscription and one-shot notification re-arm. Pinned GLib actually uses native `NtNotifyChangeMultipleKeys` APC, not this particular Win32 wrapper, so the Microsoft page is **conceptual background**, not proof of its specific internal implementation.

## Verified source CI, and no new Windows tests

[`tests/audit_c545d_glib_2824_producer_epoch_ci.py`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/audit_c545d_glib_2824_producer_epoch_ci.py) fetches exact GNOME tag paths, validates **Git blob SHA** of all four files, checks the eight watch registrations, APC reference lifetime and callback re-arm order, worker pool limit, package parser's synchronous iterator and COM cleanup order. It also implements a deliberately fail-closed hypothetical *globally closed source epoch* predicate requiring rearm disabled, registration closed, pending watch=0, callback/APC/WinRT=0, queued+active worker=0, complete ETW origin tracing, lost events0 and original owner mapping. These required gates **are not currently certified by the unmodified pinned GLib source**.

- Initial [source CI #45161050289 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45161050289): exact 3-file GLib watcher source, 1 positive/13 negative guards; no host changes.
- Addition of pinned package parser initially caused [CI #45161388998 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45161388998) from Python string literal editing, corrected; **[CI #45161578777 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45161578777)** verifies all 4 exact source blobs, package iterator and COM cleanup. The failure was *test formatting*, not a real GIO leak.

## Independently reused REAL saved Windows2022 GIO results

The original [Windows paired GIO run #45133754345](https://github.com/taku077/c545d-recorder/actions/runs/45133754345), job `137554982677` includes allowlisted original runtime watcher lines:

| bounded 16-cycle trial | No-change arm | Registry notifications arm |
|---|---:|---:|
| Watch registrations cumulative | **6** | **23** |
| Notification completions cumulative | **0** | **17** |
| Pending watch status blocks (registrations minus completions) | **6** | **6** |
| Maximum simultaneously pending | **6** | **6** |
| AppInfo worker instance count | 1 | 18 |
| Worker return after ETW-stop acknowledgement | 0 | **1** |

Thus in this bounded disposable Windows trial, `23-17=6`, and the additional **17 registration operations were matched by 17 completion operations**. There was **no observed growth in the number of pending watch status blocks** during this run. Not all eight possible roots were present (six were watched). This observation does *not* prove that no registry/APC object ever leaks or that pending watchers will remain six indefinitely.

The new [`tests/analyze_c545d_gio_watch_active_epoch_saved_ci.py`](https://github.com/taku077/c545d-recorder/blob/investigate/c545d-status-only-monitor-20261120/tests/analyze_c545d_gio_watch_active_epoch_saved_ci.py) consumes **only the original archived job logs locally**, validates both exact watcher/QPC records, 1 positive/14 corrupt negative fixtures and rejects false global quiet or memory-stable assertions. No raw logs or addresses are uploaded. Initial [CI #45161866666 FAILURE](https://github.com/taku077/c545d-recorder/actions/runs/45161866666) was GH CLI refusing ANSI in private downloaded source log; allowed local ANSI only, then **[CI #45161976486 SUCCESS](https://github.com/taku077/c545d-recorder/actions/runs/45161976486)** with no new Windows capture and no user work.

**Important independent memory result in that GIO run:** same-run controlled cycle0→16 PSAPI PrivateUsage `+331776 B`, heap REGION commit `+303104 B`, HeapWalk BUSY `-7734 B`; last4 registry Xperf global outstanding `16062` allocations, including `31` realloc-compatible groups totaling `466` outstanding (and `3604` Realloc events). These are distinct time scopes and cannot be subtracted causally. A stable pending watcher count and increasing PrivateUsage *coexist*. The former does NOT explain or refute the latter.

## Corrected acceptance logic and next work

1. In a **live 24/7 recorder**, it is valid for a bounded, actively subscribed set of registry watchers to remain; “all watcher refs freed” is **not** a sensible default release criterion. Use observation milestones (AppInfo rebuild finished, updated counter zero, registered roots count stable, queues accounted) and separate known persistent subscriptions from newly retained allocation identities.
2. A **terminal GIO producer-closed epoch** could only be certified after validated source-specific watcher cancellation and callbacks/drain, or disposal/exit of an isolated *dedicated test process*; a 2.5 s passive wait, no currently active worker or `g_cond_wait` alone never suffices. Do **not** force-unload GIO (it is PINned), force-close handles, alter the user's registry or restart the production recorder to simulate closure.
3. Generalize the now-verified native C# typed ETW HeapAlloc→HeapReAlloc→HeapFree adapter from fixed 360→720 into a **fail-closed complete-preworkload GIO owner census**. Within the same disposable process, identify original allocating stack and eventual Free; classify permanent baseline retention separately from growth after equivalent AppInfo work epochs. Do not claim these 466 group counters represent distinct objects until actual identity pairing confirms.
4. Do not schedule another identical 16-cycle/top8192 test, another four-hour host measurement or a source-only parser rerun without a **new discriminator**. Only one new bounded disposable GIO experiment should be considered after the generic identity reader and stable epoch observables are proven with negative fixtures. Record numeric phase-aligned PrivateUsage, REGION, HeapWalk and CPU/handles together; keep full RTSP, quality, A/V, MP4, SDK ABI and EOS regression gates unchanged.

**Overall status:** active PR #62; four classification cases still `evidence_gap`, production `HOLD`, actual Windows10/Tapo postpatch **not tested**, no user action, no production changes.
