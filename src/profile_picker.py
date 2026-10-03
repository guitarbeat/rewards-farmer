"""TTY profile picker and auto-selection for CLI runs.

The GUI sets REWARDS_LAUNCHED_FROM_GUI and never uses this menu. Headless and
REWARDS_AUTO runs skip it too.
"""

from __future__ import annotations

import os
import random
import sys
from collections.abc import Callable, Sequence

import accounts
import browser

AUTO_ENV_VAR = "REWARDS_AUTO"
PICKER_ENV_VAR = "REWARDS_PROFILE_PICKER"
GUI_ENV_FLAG = "REWARDS_LAUNCHED_FROM_GUI"


def auto_enabled() -> bool:
	return os.environ.get(AUTO_ENV_VAR, "").strip().lower() in ("1", "true", "yes")


def _picker_env() -> str | None:
	raw = os.environ.get(PICKER_ENV_VAR)
	return None if raw is None else raw.strip().lower()


def should_use_picker(account_count: int, *, stdin=None) -> bool:
	if os.environ.get(GUI_ENV_FLAG) == "1":
		return False
	if browser.HEADLESS:
		return False
	headless_env = os.environ.get("REWARDS_HEADLESS", "").strip().lower()
	if headless_env in ("1", "true", "yes"):
		return False
	if auto_enabled():
		return False

	flag = _picker_env()
	if flag in ("1", "true", "yes"):
		return account_count >= 1
	if flag in ("0", "false", "no"):
		return False

	stream = sys.stdin if stdin is None else stdin
	try:
		is_tty = stream.isatty()
	except Exception:
		is_tty = False
	return bool(is_tty) and account_count > 1


def format_menu(choices: Sequence[accounts.Account]) -> str:
	lines = ["Choose a profile to run, or q to finish:"]
	for index, account in enumerate(choices, start=1):
		lines.append(f"  {index}) {accounts.account_display_label(account)}")
	return "\n".join(lines)


def choose_account(
	choices: Sequence[accounts.Account],
	*,
	prompt: Callable[[str], str] | None = None,
	output: Callable[[str], None] | None = None,
) -> accounts.Account | None:
	"""Ask for a 1-based index. Empty / q returns None (end the session)."""
	if not choices:
		return None

	read = input if prompt is None else prompt
	write = print if output is None else output
	write(format_menu(choices))

	while True:
		try:
			raw = read("Profile number: ").strip().lower()
		except EOFError:
			return None

		if raw in {"", "q", "quit", "exit"}:
			return None
		if not raw.isdigit():
			write("Enter a number from the list, or q to finish.")
			continue

		index = int(raw)
		if 1 <= index <= len(choices):
			return choices[index - 1]
		write(f"Pick between 1 and {len(choices)}.")


def order_for_auto(choices: Sequence[accounts.Account], *, rng: random.Random | None = None) -> list[accounts.Account]:
	"""Random order in auto mode (Michael's AUTOMATIC), otherwise configured order."""
	items = list(choices)
	if auto_enabled():
		(rng or random.Random()).shuffle(items)
	return items
