#!/usr/bin/env python3
"""Fail-closed C545D memory classification ownership and release gate.

Does NOT infer leak from private commit or lack of growth from HeapWalk BUSY.
An unresolved observation must document the failed inference and the
next measurable, automation-owned falsification step. Cannot close silently.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

IDS = {
    "GIO16_OWNER_AND_COMMIT",
    "GIO_COMBO256_LATE",
    "GIO_ASYNC_QUIESCENCE",
    "ACTUAL_TAPO_POSTPATCH",
}
TERMINAL = {"leak_confirmed", "bounded_retention", "transient_lifetime"}
ALL = TERMINAL | {"evidence_gap"}
REQUIRED = (
    "id", "status", "scope", "source_runs", "observed",
    "why_previous_did_not_resolve", "missing_observable",
    "existing_reuse", "next_automatic_action",
    "decisive_rule", "next_test_dependency",
    "request_user_now", "blocks_classification"
)
EXPECTED_RUNS = {
    "GIO16_OWNER_AND_COMMIT": {45015173260, 45030562503, 45046446784, 45051751198, 45052226913, 45052837535, 45053779999, 45058803441},
    "GIO_COMBO256_LATE": {44918598339},
    "GIO_ASYNC_QUIESCENCE": {45015173260, 45046446784},
    "ACTUAL_TAPO_POSTPATCH": set(),
}

def validate(data: dict) -> tuple[int, str]:
    if not isinstance(data, dict):
        raise ValueError("invalid_root")
    for key, expected in (
        ("schema_version", 1),
        ("contract", "docs/C545D_MEMORY_CLASSIFICATION_EXIT_GATE.md"),
        ("install_approved", 0),
        ("live_test_authorized", 0),
        ("real_host_verified", 0),
    ):
        if type(data.get(key)) is not type(expected) or data[key] != expected:
            raise ValueError("release_or_schema_safety_changed")
    if data.get("release_state") != "HOLD":
        raise ValueError("release_not_validated")
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != len(IDS):
        raise ValueError("missing_or_extra_case")
    seen: set[str] = set()
    byid = {}
    for case in cases:
        if not isinstance(case, dict) or set(case) != set(REQUIRED):
            raise ValueError("incomplete_case_schema")
        name = case["id"]
        if not isinstance(name, str) or name not in IDS or name in seen:
            raise ValueError("duplicate_or_wrong_case")
        seen.add(name)
        byid[name] = case
        if case["status"] not in ALL:
            raise ValueError("unknown_status_not_a_classification")
        for namefield in ("scope", "observed", "why_previous_did_not_resolve",
                          "missing_observable", "next_automatic_action", "decisive_rule"):
            value = case[namefield]
            if not isinstance(value, str) or len(value.strip()) < 40:
                raise ValueError("evidence_gap_not_actionable")
        if not isinstance(case["source_runs"], list) or any(
                type(v) is not int or v <= 0 for v in case["source_runs"]):
            raise ValueError("invalid_source_run")
        if set(case["source_runs"]) != EXPECTED_RUNS[case["id"]]:
            raise ValueError("source_provenance_changed")
        reuse = case["existing_reuse"]
        if not isinstance(reuse, list) or not reuse or any(
                not isinstance(s, str) or not (s.startswith("tests/") or
                    s.startswith("docs/")) or ".." in s for s in reuse):
            raise ValueError("missing_existing_reuse")
        if case["request_user_now"] is not False:
            raise ValueError("unapproved_real_host_measurement")
        if case["blocks_classification"] is not (case["status"] == "evidence_gap"):
            raise ValueError("unresolved_case_silently_closed")
        if case["status"] in TERMINAL:
            # The ledger must be extended with a new, reviewed evidence
            # schema before permitting any case to close. Do not accept
            # hand-written assertions of 'zero leak' or 'bounded' as proof.
            raise ValueError("terminal_classification_requires_verified_evidence_extension")
        dep = case["next_test_dependency"]
        if dep != "none" and dep not in IDS - {case["id"]}:
            raise ValueError("invalid_test_dependency")
    for name in seen:
        path: set[str] = set()
        cur = name
        while cur != "none":
            if cur in path:
                raise ValueError("cyclic_investigation_dependency")
            path.add(cur)
            cur = byid[cur]["next_test_dependency"]
    gaps = sum(c["status"] == "evidence_gap" for c in cases)
    if gaps and data.get("classification_state") != "OPEN":
        raise ValueError("classification_falsely_closed")
    if not gaps:
        raise ValueError("release_policy_change_requires_review")
    return gaps, (
        "C545D_CLASSIFICATION_CONTRACT_VALID,"
        f"cases={len(cases)},evidence_gaps={gaps},"
        "missing_evidence_and_recovery_plan=4,"
        "silent_unknowns=0,classification_complete=0,"
        "release_gate=HOLD,install_approved=0,real_host_untested=1"
    )

def selftest(doc: dict) -> None:
    gaps, msg = validate(doc)
    assert gaps == 4 and msg.startswith("C545D_CLASSIFICATION_CONTRACT_VALID")
    tests = []
    mutant = copy.deepcopy(doc)
    mutant["cases"][0]["why_previous_did_not_resolve"] = "unknown"
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][1]["next_automatic_action"] = ""
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][2]["status"] = "bounded_retention"
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["classification_state"] = "COMPLETE"
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][0]["request_user_now"] = True
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][1]["next_test_dependency"] = "GIO_COMBO256_LATE"
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][3]["source_runs"].append(44918598339)
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["release_state"] = "PASS"
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][0]["existing_reuse"] = []
    tests.append(mutant)
    mutant = copy.deepcopy(doc)
    mutant["cases"][0]["id"] = "GIO_COMBO256_LATE"
    tests.append(mutant)
    for candidate in tests:
        try:
            validate(candidate)
        except ValueError:
            continue
        raise AssertionError("unsafe_investigation_contract_mutation_accepted")
    print("C545D_CLASSIFICATION_CONTRACT_SELFTEST_PASS,negative=10,positive=1,new_windows_runs=0")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--assert-closed", action="store_true")
    args = ap.parse_args()
    doc = json.loads(args.source.read_text(encoding="utf-8"))
    if args.selftest:
        selftest(doc)
        return
    gaps, msg = validate(doc)
    print(msg)
    if args.assert_closed and gaps:
        print("C545D_CLASSIFICATION_COMPLETION_BLOCKED,"
              "reason=MISSING_ALLOCATION_LIFETIME_AND_HOST_VALIDATION,"
              "next_auto_actions_in=docs/MEMORY_CLASSIFICATION_CASES.json")
        raise SystemExit(3)

if __name__ == "__main__":
    main()
