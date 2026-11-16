# Public-repository security and change control

This repository is **publicly readable**, but being public does not grant
strangers write or merge access. Anyone may fork or submit a pull request.
Only repository collaborators or apps with the necessary permissions can push,
merge, change settings, or delete the repository.

## Protect `main` (repository-owner UI task)

At `Settings > Rules > Rulesets`, add an **active branch ruleset** for the
default branch `main`. Recommended for a single-maintainer GitHub Free repo:

- Require a pull request before merging; use no mandatory outside review yet
  (the sole maintainer cannot approve their own PR).
- Require the existing Windows CI status check (`validate`) before merging.
- Block force-pushes and branch deletions.
- Do not grant bypass to external contributors.
- Avoid automatic merging of untrusted fork pull requests.
- Keep Actions workflow token `contents: read` (as configured).

As of 2026-11-16, the GitHub API reported `main` as
`protected: false` and the repository had no active rulesets.
This is *not* public write access; it only means extra branch safeguards
are not configured.

## Handling external pull requests
External contributors may propose changes, but do not merge until reviewing
their code and workflow changes. For fork PRs, GitHub's regular
`pull_request` workflows run with read-only token and no secrets.
Do not change this workflow to run untrusted PR code with
`pull_request_target` or a write-capable token.

## Data boundary
Never commit camera usernames/passwords, camera address/IP, real RTSP URLs,
`settings.json`, `camera_password.dpapi`, raw recordings, ETL traces, or
unredacted logs to **either** repository. Store these only locally.

## CI is not a camera test
CI validates source syntax and guardrails; it cannot prove long-term CPU,
memory, synchronized recordings, MP4 completion, or safe stop/restart.
Keep the last good on-device build when trying changes from pull requests.

References:
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
