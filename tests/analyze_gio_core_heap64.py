#!/usr/bin/env python3
"""Core-only MSVC GIO 64-cycle heap census, same-run official control.

Disposable Windows CI artifacts only. HeapWalk busy bytes are not necessarily
lifetime leaks and exact-size bins do not identify allocation call stacks.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

MODES = ("official", "candidate")
ARMS = ("nochange", "registry")
CHECKS = (("baseline", 0), ("cycle", 16), ("cycle", 32), ("cycle", 48),
          ("cycle", 64), ("after_cleanup", 65), ("settled_cleanup", 66))


def parse(text: str, changed: bool) -> dict[str, object]:
    done = re.findall(r'^GIO_PROBE_DONE,cycles=(\d+),notifications=(\d+),reg_changes=(\d+)$', text, re.M)
    if len(done) != 1 or done[0][0] != '64' or done[0][2] != str(int(changed)):
        raise ValueError('missing/wrong probe completion')
    heaps = {}
    bins = {}
    key = {}
    mem = {}
    handles = {}
    for line in text.splitlines():
        a = line.split(',')
        if a[0] == 'GIO_HEAP':
            if len(a) != 7: raise ValueError('bad heap width')
            k = (a[1], int(a[2]))
            if k in heaps or int(a[6]) != 0 or int(a[5]) < 1:
                raise ValueError('bad heap census')
            heaps[k] = int(a[4])
        elif a[0] == 'GIO_HEAPSIZE' and len(a) == 5 and a[3] == '360':
            k = (a[1], int(a[2]))
            if k in bins or int(a[4]) < 0: raise ValueError('bad 360 bin')
            bins[k] = int(a[4])
        elif a[0] == 'GIO_KEY' and len(a) == 4:
            k = (a[1], int(a[2]))
            if k in key: raise ValueError('duplicate Key sample')
            key[k] = int(a[3])
        elif a[0] == 'GIO_PROBE' and len(a) == 6:
            k = (a[1], int(a[2]))
            if k in mem: raise ValueError('duplicate process sample')
            handles[k] = int(a[4]); mem[k] = int(a[5])
    if set(heaps) != set(CHECKS):
        raise ValueError('missing 7 exact heap checkpoints')
    if not all(k in key for k in (('baseline',0),('settled_cleanup',66))):
        raise ValueError('missing Key census')
    if not all(k in mem for k in (('baseline',0),('settled_cleanup',66))):
        raise ValueError('missing memory/handle census')
    if any(v < 0 for v in (*heaps.values(), *key.values(), *mem.values(), *handles.values())):
        raise ValueError('negative absolute census')
    return {'heap': heaps,'size360': {k: bins.get(k,0) for k in CHECKS},
            'key': key,'mem': mem,'handles':handles}


def effect(a: dict, b: dict, metric: str, first: tuple, last: tuple) -> int:
    return ((b[metric][last] - b[metric][first]) -
            (a[metric][last] - a[metric][first]))


def analyze(root: Path) -> list[dict[str,int|str]]:
    parsed = {}
    for mode in MODES:
        for arm in ARMS:
            path = root / f'{mode}-{arm}-64.txt'
            parsed[mode,arm] = parse(path.read_text(encoding='utf-8-sig'), arm=='registry')
    result = []
    base, prior, last, settled = CHECKS[0], CHECKS[3], CHECKS[4], CHECKS[-1]
    for mode in MODES:
        ctrl = parsed[mode,'nochange']; treatment = parsed[mode,'registry']
        row = dict(mode=mode,
            heap_busy_effect=effect(ctrl,treatment,'heap',base,last),
            heap_busy_last16_effect=effect(ctrl,treatment,'heap',prior,last),
            heap_busy_settled_effect=effect(ctrl,treatment,'heap',base,settled),
            exact360_effect=effect(ctrl,treatment,'size360',base,last),
            exact360_last16_effect=effect(ctrl,treatment,'size360',prior,last),
            exact360_settled_effect=effect(ctrl,treatment,'size360',base,settled),
            private_effect=effect(ctrl,treatment,'mem',base,settled),
            key_effect=effect(ctrl,treatment,'key',base,settled),
            candidate_absolute_handle_delta=(treatment['handles'][settled]-treatment['handles'][base]))
        result.append(row)
    old, candidate = result
    if old['key_effect'] < 100 or candidate['key_effect'] > 4 or candidate['candidate_absolute_handle_delta'] > 4:
        raise ValueError('original Key growth/candidate Key plateau not reproduced')
    if candidate['private_effect'] >= old['private_effect']:
        raise ValueError('candidate private memory reduction not reproduced')
    return result


def selftest() -> None:
    sample = ['GIO_PROBE_DONE,cycles=64,notifications=0,reg_changes=1']
    for phase,cycle in CHECKS:
        sample.extend((f'GIO_HEAP,{phase},{cycle},1,1000,1,0',
                       f'GIO_HEAPSIZE,{phase},{cycle},360,1',
                       f'GIO_PROBE,{phase},{cycle},0,100,12345'))
        if phase in ('baseline','settled_cleanup'):
            sample.append(f'GIO_KEY,{phase},{cycle},10')
    good = '\n'.join(sample)
    assert parse(good,True)['size360'][('cycle',64)] == 1
    broken = [good.replace('cycles=64,','cycles=63,'),
              good.replace('GIO_HEAP,cycle,32,1,1000,1,0', 'GIO_HEAP,cycle,32,1,1000,1,1'),
              good.replace('GIO_HEAPSIZE,cycle,48,360,1','GIO_HEAPSIZE,cycle,48,360,-1'),
              good.replace('GIO_HEAP,cycle,16,1,1000,1,0',''),
              good.replace('GIO_KEY,settled_cleanup,66,10',''),
              good + '\nGIO_HEAPSIZE,cycle,16,360,1']
    for s in broken:
        try: parse(s,True)
        except ValueError: pass
        else: raise AssertionError('corrupt numeric record accepted')
    print('C545D_CORE_HEAP64_SELFTEST_PASS,negative_cases=6,host=0')


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path)
    p.add_argument('--selftest',action='store_true')
    args=p.parse_args()
    if args.selftest: selftest();return
    if args.root is None: p.error('--root is required')
    out=analyze(args.root)
    for row in out:
        print('C545D_CORE_HEAP64,mode={mode},heap_busy_effect={heap_busy_effect},'
              'heap_busy_last16_effect={heap_busy_last16_effect},'
              'heap_busy_settled_effect={heap_busy_settled_effect},'
              'exact360_effect={exact360_effect},'
              'exact360_last16_effect={exact360_last16_effect},'
              'exact360_settled_effect={exact360_settled_effect},'
              'private_effect={private_effect},key_effect={key_effect},'
              'candidate_absolute_handle_delta={candidate_absolute_handle_delta},'
              'real_host=0'.format(**row))
    print('C545D_CORE_HEAP64_DIAGNOSTIC_PASS,modes=2,matched_controls=1,'
          'heap_busy_and_exact360_reported=1,zero_leak_proven=0,'
          'allocation_stack_attributed=0,real_camera=0,install_approved=0')


if __name__=='__main__':main()
