"""Which accounts a run works through.

Rewards is per Microsoft account, and the browser profile is what holds the
sign-in, so an account here is just a profile directory. One directory per
account keeps their cookies apart, which is the whole requirement.

    REWARDS_ACCOUNTS=personal,spare python src/main.py

Unset, the run uses the single profile in constants.py exactly as before, so
nothing about an existing setup changes.
"""

import os
import re
from dataclasses import dataclass

from constants import DEFAULT_ROOT_DATA_DIR

ACCOUNTS_ENV_VAR = "REWARDS_ACCOUNTS"
DATA_DIR_ENV_VAR = "USER_DATA_DIR"

PROFILE_NAME = "Default"

# Names become directory names, so keep them to something a filesystem and a
# command line both handle without quoting. The character set alone is not
# enough: "." and ".." are made of allowed characters and still walk out of the
# directory, so they are rejected by name below and the resolved path is
# checked as well.
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

# Reserved by every filesystem that has directories at all.
RESERVED_NAMES = {".", ".."}


def is_valid_account_name(name: str) -> bool:
	return bool(SAFE_NAME.match(name)) and name not in RESERVED_NAMES and not name.endswith(".")


def is_edge_user_data_dir(path: str) -> bool:
	"""True when a directory looks like an Edge/Chromium user-data-dir root."""
	return (
		os.path.isdir(path)
		and os.path.isdir(os.path.join(path, PROFILE_NAME))
		and os.path.isfile(os.path.join(path, "Local State"))
	)


def discover_named_accounts() -> list[str]:
	"""Return configured multi-account names under USER_DATA_DIR, if any.

	When data-dir itself is the Edge profile, return an empty list so callers
	use the default single-profile behaviour. Edge component folders such as
	"Ad Blocking" are ignored.
	"""
	root = os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_ROOT_DATA_DIR)
	if not os.path.isdir(root):
		return []

	if is_edge_user_data_dir(root):
		return []

	names: list[str] = []

	for entry in sorted(os.listdir(root)):
		if not is_valid_account_name(entry):
			continue

		path = os.path.join(root, entry)

		if is_edge_user_data_dir(path):
			names.append(entry)

	return names


@dataclass(frozen=True)
class Account:
	"""A named browser profile to run the tasks against."""

	name: str
	user_data_dir: str
	profile_name: str

	@property
	def is_default(self) -> bool:
		return self.user_data_dir == os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_ROOT_DATA_DIR)

def directory_name_is_valid(name: str) -> bool:
	"""Whether a name is usable as a directory name.

	Does not check whether the directory exists, only that the name is safe to
	use as a directory name.
	"""

	# The trailing dot is not cosmetic. Win32 strips one off a path component
	# and python's normalisation does not, so such a name means a different
	# directory than it reads as: "work." is "work", and "..." is the profile
	# directory itself. Either way two entries end up sharing one profile,
	# which is the one thing this module exists to prevent.
	return bool(SAFE_NAME.match(name)) and name not in RESERVED_NAMES and not name.endswith(".")

def _named(name: str) -> Account:
	# Each account gets its own directory under the configured one, so the
	# existing data-dir stays where it is and the new ones sit beside the
	# profile it already holds.
	user_data_dir = os.path.join(os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_ROOT_DATA_DIR), name)

	# The name passed the character check, but that only constrains the
	# characters, not where they end up pointing. Confirm against the resolved
	# path, which is the thing Edge is actually handed. realpath rather than
	# abspath, so a link or a junction under the profile directory is followed
	# to where it really goes instead of being taken at face value.
	root = os.path.realpath(os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_ROOT_DATA_DIR))
	resolved = os.path.realpath(user_data_dir)

	if os.path.commonpath([root, resolved]) != root or resolved == root:
		raise ValueError(
			f"{ACCOUNTS_ENV_VAR} entry {name!r} resolves outside the profile directory"
		)

	return Account(
		name=name,
		user_data_dir=user_data_dir,
		profile_name=PROFILE_NAME,
	)

def get_default_account() -> Account:
	"""The account used when REWARDS_ACCOUNTS is unset or empty."""

	return Account(
		name="default",
		user_data_dir=os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_ROOT_DATA_DIR),
		profile_name=PROFILE_NAME,
	)

def configured() -> list[Account]:
	"""Accounts for this run, in order.

	Raises ValueError on a name that cannot be a directory, rather than
	silently creating something surprising next to the real profiles.
	"""
	raw = os.environ.get(ACCOUNTS_ENV_VAR, "").strip()

	if not raw:
		return [get_default_account()]

	names = [part.strip() for part in raw.split(",")]
	names = [name for name in names if name]

	if not names:
		return [get_default_account()]

	seen: set[str] = set()
	accounts: list[Account] = []

	for name in names:
		if not directory_name_is_valid(name):
			raise ValueError(
				f"{ACCOUNTS_ENV_VAR} entry {name!r} is not usable as a directory name; "
				"use letters, digits, dot, dash or underscore, and do not end in a dot"
			)

		# Duplicates would run the same profile twice, which earns nothing the
		# second time and doubles the run length.
		if name.lower() in seen:
			continue

		seen.add(name.lower())
		accounts.append(_named(name))

	return accounts
