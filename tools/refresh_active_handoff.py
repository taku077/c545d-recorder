#!/usr/bin/env python3
"""Deterministically refresh main handoff from the active PR without running PR code."""
import base64
import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = os.getenv("GITHUB_REPOSITORY", "taku077/c545d-recorder")
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "docs/ACTIVE_HANDOFF_CONFIG.json"
OUTPUT = ROOT / "docs/ACTIVE_HANDOFF.md"


def api(path):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "c545d-handoff", "X-GitHub-Api-Version": "2022-11-28"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=30) as stream:
        return json.load(stream)


def extract_current(source, boundary, guard):
    marker = "<!-- CURRENT_HANDOFF_START:"
    pos = source.find(marker)
    if pos < 0:
        raise ValueError("Missing active handoff marker")
    start = source.find("\n", pos) + 1
    end = source.find(boundary, start)
    if start < 1 or end < 0:
        raise ValueError("Missing archive boundary; refusing to fall back to old current")
    current = source[start:end].strip()
    if guard and guard not in current:
        raise ValueError("Latest handoff lost required validated evidence")
    if len(current) <= 22000:
        if len(current) < 100:
            raise ValueError("Active handoff is empty")
        return current
    # Handoff history grows monotonically. It is not safe to abort all future
    # updates merely because the current section exceeded a fixed byte cap.
    # Preserve the full history at the exact-SHA source link and retain newest
    # complete, chronological UPDATE sections in the generated entry point.
    import re
    headers = list(re.finditer(r"(?m)^### UPDATE .+$", current))
    if not headers or headers[0].start() != 0:
        raise ValueError("Oversized handoff has no first UPDATE heading")
    chunks = [current[m.start():headers[i + 1].start() if i + 1 < len(headers)
                      else len(current)].strip()
              for i, m in enumerate(headers)]
    retained = []
    for chunk in chunks:
        if sum(map(len, retained)) + len(chunk) + 2 * len(retained) > 18000:
            break
        retained.append(chunk)
    if not retained:
        raise ValueError("Newest UPDATE section is unexpectedly long")
    excerpt = "\n\n".join(retained) + (
        "\n\nOlder UPDATE sections remain at the exact-commit source link "
        "above; do not treat their omission here as forgotten validation."
    )
    if guard and guard not in excerpt:
        # The full exact-SHA current section DID pass the required-evidence
        # check above. Do not permanently stop updating the central handoff
        # merely because newer UPDATE sections pushed that verified older
        # evidence outside the size-bounded excerpt. Keep the guard visible
        # and point to the authoritative full history; never invent a pass.
        excerpt += ("\n\nProtected evidence exists in the exact-commit full "
                    "handoff but was omitted from this size-limited excerpt: "
                    + guard + ". Read the verified snapshot source above.")
    return excerpt


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    number = cfg["active_pr_number"]
    pr = api(f"/repos/{REPO}/pulls/{number}")
    if pr["head"]["repo"]["full_name"].lower() != REPO.lower():
        raise ValueError("Untrusted cross-repository PR; refusing to mirror")
    sha, branch = pr["head"]["sha"], pr["head"]["ref"]
    frozen = api(f"/repos/{REPO}/contents/docs/HANDOFF_CURRENT.md?ref={quote(sha)}")
    if frozen.get("encoding") != "base64":
        raise ValueError("Cannot decode source handoff")
    source = base64.b64decode(frozen["content"]).decode("utf-8")
    current = extract_current(source, cfg["archive_heading_marker"], cfg.get("required_evidence", ""))
    runs = api(f"/repos/{REPO}/actions/runs?head_sha={quote(sha)}&per_page=100")["workflow_runs"]
    runs = sorted((r for r in runs if r["head_sha"] == sha),
                  key=lambda r: (r["created_at"], r["id"]), reverse=True)
    entries = []
    for run in runs[:16]:
        title = run["name"].replace("|", "/").replace("\n", " ")
        outcome = run.get("conclusion") or run["status"]
        entries.append(f"| {title} | {outcome} | [#{run['id']}]({run['html_url']}) |")
    if not entries:
        entries = ["| Same-SHA CI not found | unknown | - |"]
    body = (
        "# C545D — ACTIVE DEVELOPMENT HANDOFF (AUTO-GENERATED)\n\n"
        "**Read this before the old main-branch HANDOFF_CURRENT.** "
        "The experiment branch is not installed on the user's recording PC.\n\n"
        f"- **Active PR:** [#{number}]({pr['html_url']}) / state `{pr['state']}`\n"
        f"- **Exact branch HEAD:** `{branch}` / `{sha}`\n"
        f"- **PR updated at (UTC):** `{pr['updated_at']}`\n"
        f"- **Verified snapshot source:** [HANDOFF_CURRENT.md at that commit](https://github.com/{REPO}/blob/{sha}/docs/HANDOFF_CURRENT.md)\n\n"
        "## CI runs at exactly this HEAD\n\n"
        "| Workflow | Outcome | Evidence |\n|---|---|---|\n"
        + "\n".join(entries) + "\n\n"
        "## Current development findings from the active PR\n\n"
        + current + "\n\n"
        "## Resume rules (fail closed)\n\n"
        "1. Compare the HEAD above against the current live PR HEAD; if different, re-read the live PR before using this snapshot.\n"
        "2. Verify both success and **latest failed** CI jobs; do not quietly regress to an earlier successful run.\n"
        "3. The 96.29% PrivateUsage improvement and zero handle delta in 16 cycles were **camera-free CI** results, not real-PC improvements.\n"
        "4. Do not deploy unverified DLLs, restart the active recorder, run new multi-hour host tests, or re-request completed WPA/ETL work.\n"
        "5. To switch projects or active PR, deliberately update ACTIVE_HANDOFF_CONFIG.json.\n\n"
        "This file is generated by tools/refresh_active_handoff.py, using API reads and the selected PR's existing public handoff.\n"
    )
    OUTPUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"HANDOFF_OK PR={number} SHA={sha} runs={len(runs)}")


if __name__ == "__main__":
    main()
