"""Daily completion records for persistence mode.

When REWARDS_PERSISTENCE is on, accounts that already finished today are
skipped until the next calendar day. The terminal launcher still runs one
pass, and only skips names already recorded if the env flag is set.
"""

from __future__ import annotations

import os
from datetime import date, datetime

from constants import REPO_ROOT

COMPLETIONS_FILE = os.path.join(REPO_ROOT, "logs", "completed_profiles.txt")
PERSISTENCE_ENV_VAR = "REWARDS_PERSISTENCE"


def persistence_enabled() -> bool:
	return os.environ.get(PERSISTENCE_ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def load_completed_today(path: str | None = None) -> set[str]:
	"""Profile names recorded as completed on today's local calendar date."""
	completions_path = path or COMPLETIONS_FILE
	completed: set[str] = set()
	today = date.today().isoformat()

	try:
		with open(completions_path, encoding="utf-8") as handle:
			lines = handle.readlines()
	except OSError:
		return completed

	for raw in lines:
		line = raw.strip()
		if not line or "|" not in line:
			continue
		name, timestamp = line.rsplit("|", 1)
		name = name.strip()
		timestamp = timestamp.strip()
		if name and timestamp.startswith(today):
			completed.add(name)

	return completed


def mark_completed(profile_name: str, path: str | None = None, when: datetime | None = None) -> None:
	completions_path = path or COMPLETIONS_FILE
	stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
	os.makedirs(os.path.dirname(completions_path), exist_ok=True)
	with open(completions_path, "a", encoding="utf-8") as handle:
		handle.write(f"{profile_name} | {stamp}\n")


def remaining(accounts: list, *, enabled: bool | None = None, path: str | None = None) -> list:
	"""Accounts that still need a run today when persistence is on."""
	if enabled is None:
		enabled = persistence_enabled()
	if not enabled:
		return list(accounts)

	done = load_completed_today(path)
	return [account for account in accounts if account.name not in done]
