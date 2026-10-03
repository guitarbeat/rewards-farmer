"""Which accounts a run works through.

Rewards is per Microsoft account, and the browser profile is what holds the
sign-in, so an account here is just a profile directory. One directory per
account keeps their cookies apart, which is the whole requirement.

    REWARDS_ACCOUNTS=personal,spare python src/main.py

Unset, the run uses the single profile in constants.py exactly as before, so
nothing about an existing setup changes.
"""

import json
import os
import re
from dataclasses import dataclass

from constants import DEFAULT_ROOT_DATA_DIR

ACCOUNTS_ENV_VAR = "REWARDS_ACCOUNTS"
DATA_DIR_ENV_VAR = "USER_DATA_DIR"
EDGE_PROFILES_ENV_VAR = "REWARDS_EDGE_PROFILES"

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


def _root_data_dir() -> str:
	return os.environ.get(DATA_DIR_ENV_VAR, DEFAULT_ROOT_DATA_DIR)


def read_edge_info_cache(user_data_dir: str | None = None) -> dict:
	"""Profile info_cache from Edge Local State, or {} if unreadable."""
	root = user_data_dir or _root_data_dir()
	local_state = os.path.join(root, "Local State")
	try:
		with open(local_state, encoding="utf-8") as handle:
			data = json.load(handle)
	except (OSError, json.JSONDecodeError):
		return {}

	if not isinstance(data, dict):
		return {}

	profile = data.get("profile")
	if not isinstance(profile, dict):
		return {}

	cache = profile.get("info_cache")
	return cache if isinstance(cache, dict) else {}


def list_edge_profiles(user_data_dir: str | None = None) -> list[Account]:
	"""Edge profiles inside a single user-data-dir, from Local State + folders."""
	root = user_data_dir or _root_data_dir()
	cache = read_edge_info_cache(root)
	names: list[str] = []
	seen: set[str] = set()

	for name in cache:
		if not isinstance(name, str) or name in seen:
			continue
		profile_dir = os.path.join(root, name)
		if os.path.isdir(profile_dir):
			names.append(name)
			seen.add(name)

	if PROFILE_NAME not in seen and os.path.isdir(os.path.join(root, PROFILE_NAME)):
		names.insert(0, PROFILE_NAME)

	return [
		Account(name=name, user_data_dir=root, profile_name=name)
		for name in names
	]


def account_display_label(account: Account) -> str:
	"""Human label: directory name plus Edge account names when Local State has them."""
	cache = read_edge_info_cache(account.user_data_dir)
	info = cache.get(account.profile_name)
	if not isinstance(info, dict):
		return account.name

	parts = [
		str(info[key]).strip()
		for key in ("gaia_name", "user_name", "name")
		if info.get(key)
	]
	# Keep unique extra names that are not already the directory name.
	extras = [part for part in parts if part and part.lower() != account.name.lower()]
	seen: list[str] = []
	for extra in extras:
		if extra not in seen:
			seen.append(extra)
	if seen:
		return f"{account.name} — {' · '.join(seen)}"
	return account.name


def _accounts_from_edge_profiles_env() -> list[Account] | None:
	raw = os.environ.get(EDGE_PROFILES_ENV_VAR, "").strip()
	if not raw:
		return None

	root = _root_data_dir()
	available = {account.profile_name: account for account in list_edge_profiles(root)}

	if raw.lower() == "all":
		if available:
			return list(available.values())
		return [get_default_account()]

	names = [part.strip() for part in raw.split(",") if part.strip()]
	if not names:
		return [get_default_account()]

	accounts: list[Account] = []
	seen: set[str] = set()
	for name in names:
		key = name.lower()
		if key in seen:
			continue
		seen.add(key)
		if name in available:
			accounts.append(available[name])
		else:
			accounts.append(Account(name=name, user_data_dir=root, profile_name=name))

	return accounts or [get_default_account()]


def configured() -> list[Account]:
	"""Accounts for this run, in order.

	Raises ValueError on a name that cannot be a directory, rather than
	silently creating something surprising next to the real profiles.
	"""
	raw = os.environ.get(ACCOUNTS_ENV_VAR, "").strip()

	if not raw:
		edge_accounts = _accounts_from_edge_profiles_env()
		if edge_accounts is not None:
			return edge_accounts
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
