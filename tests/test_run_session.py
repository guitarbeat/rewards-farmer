"""Persistence, auto mode, and the CLI profile picker."""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import accounts
import daily_completion
import main
import profile_picker


class DailyCompletionTests(unittest.TestCase):
	def setUp(self) -> None:
		self.tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
		self.tmp.close()
		self.addCleanup(lambda: os.path.exists(self.tmp.name) and os.remove(self.tmp.name))

	def test_reads_only_todays_rows(self) -> None:
		with open(self.tmp.name, "w", encoding="utf-8") as handle:
			handle.write("personal | 1999-01-01 08:00:00\n")
			handle.write(f"spare | {datetime.now():%Y-%m-%d} 09:00:00\n")
			handle.write("not-a-row\n")
		self.assertEqual(daily_completion.load_completed_today(self.tmp.name), {"spare"})

	def test_mark_completed_appends(self) -> None:
		daily_completion.mark_completed("home", path=self.tmp.name, when=datetime(2026, 10, 3, 8, 0, 0))
		with open(self.tmp.name, encoding="utf-8") as handle:
			self.assertIn("home | 2026-10-03 08:00:00", handle.read())

	def test_remaining_skips_completed_when_enabled(self) -> None:
		with open(self.tmp.name, "w", encoding="utf-8") as handle:
			handle.write(f"personal | {datetime.now():%Y-%m-%d} 09:00:00\n")
		items = [
			accounts.Account(name="personal", user_data_dir="a", profile_name="Default"),
			accounts.Account(name="spare", user_data_dir="b", profile_name="Default"),
		]
		left = daily_completion.remaining(items, enabled=True, path=self.tmp.name)
		self.assertEqual([a.name for a in left], ["spare"])
		self.assertEqual(
			[a.name for a in daily_completion.remaining(items, enabled=False, path=self.tmp.name)],
			["personal", "spare"],
		)


class ProfilePickerTests(unittest.TestCase):
	def setUp(self) -> None:
		self.addCleanup(os.environ.pop, profile_picker.AUTO_ENV_VAR, None)
		self.addCleanup(os.environ.pop, profile_picker.PICKER_ENV_VAR, None)
		self.addCleanup(os.environ.pop, profile_picker.GUI_ENV_FLAG, None)
		os.environ.pop(profile_picker.AUTO_ENV_VAR, None)
		os.environ.pop(profile_picker.PICKER_ENV_VAR, None)
		os.environ.pop(profile_picker.GUI_ENV_FLAG, None)

	def test_gui_never_opens_picker(self) -> None:
		os.environ[profile_picker.GUI_ENV_FLAG] = "1"
		os.environ[profile_picker.PICKER_ENV_VAR] = "true"
		self.assertFalse(profile_picker.should_use_picker(3))

	def test_auto_never_opens_picker(self) -> None:
		os.environ[profile_picker.AUTO_ENV_VAR] = "true"
		os.environ[profile_picker.PICKER_ENV_VAR] = "true"
		self.assertFalse(profile_picker.should_use_picker(3))

	def test_forced_picker_with_one_account(self) -> None:
		os.environ[profile_picker.PICKER_ENV_VAR] = "true"
		self.assertTrue(profile_picker.should_use_picker(1))

	def test_choose_account_accepts_one_based_index(self) -> None:
		choices = [
			accounts.Account(name="personal", user_data_dir="a", profile_name="Default"),
			accounts.Account(name="spare", user_data_dir="b", profile_name="Default"),
		]
		answers = iter(["2"])
		picked = profile_picker.choose_account(
			choices,
			prompt=lambda _: next(answers),
			output=lambda _: None,
		)
		self.assertEqual(picked.name, "spare")

	def test_choose_account_quit(self) -> None:
		choices = [accounts.Account(name="personal", user_data_dir="a", profile_name="Default")]
		picked = profile_picker.choose_account(
			choices,
			prompt=lambda _: "q",
			output=lambda _: None,
		)
		self.assertIsNone(picked)

	def test_auto_order_is_shuffled(self) -> None:
		os.environ[profile_picker.AUTO_ENV_VAR] = "true"
		choices = [
			accounts.Account(name="a", user_data_dir="a", profile_name="Default"),
			accounts.Account(name="b", user_data_dir="b", profile_name="Default"),
			accounts.Account(name="c", user_data_dir="c", profile_name="Default"),
		]
		ordered = profile_picker.order_for_auto(choices, rng=random.Random(1))
		self.assertEqual(sorted(a.name for a in ordered), ["a", "b", "c"])
		self.assertNotEqual([a.name for a in ordered], ["a", "b", "c"])


class PersistenceRunLoopTests(unittest.TestCase):
	def setUp(self) -> None:
		self.addCleanup(os.environ.pop, accounts.ACCOUNTS_ENV_VAR, None)
		self.addCleanup(os.environ.pop, "REWARDS_PERSISTENCE", None)
		self.addCleanup(os.environ.pop, "REWARDS_AUTO", None)
		self.addCleanup(os.environ.pop, "REWARDS_PROFILE_PICKER", None)
		self.addCleanup(os.environ.pop, "REWARDS_LAUNCHED_FROM_GUI", None)
		os.environ["REWARDS_PROFILE_PICKER"] = "false"
		os.environ["REWARDS_LAUNCHED_FROM_GUI"] = "1"
		self.isatty = mock.patch("sys.stdin.isatty", return_value=False)
		self.isatty.start()
		self.addCleanup(self.isatty.stop)
		self.calls: list[str] = []
		real = main.run_account
		self.addCleanup(setattr, main, "run_account", real)

		def run_account(account, create_runner=None):
			self.calls.append(account.name)
			return True

		main.run_account = run_account
		self.tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
		self.tmp.close()
		self.addCleanup(lambda: os.path.exists(self.tmp.name) and os.remove(self.tmp.name))
		self.patcher = mock.patch.object(daily_completion, "COMPLETIONS_FILE", self.tmp.name)
		self.patcher.start()
		self.addCleanup(self.patcher.stop)

	def test_skips_accounts_completed_today(self) -> None:
		os.environ[accounts.ACCOUNTS_ENV_VAR] = "personal,spare"
		os.environ["REWARDS_PERSISTENCE"] = "true"
		with open(self.tmp.name, "w", encoding="utf-8") as handle:
			handle.write(f"personal | {datetime.now():%Y-%m-%d} 08:00:00\n")
		self.assertEqual(main.main(), 0)
		self.assertEqual(self.calls, ["spare"])

	def test_marks_successful_runs(self) -> None:
		os.environ[accounts.ACCOUNTS_ENV_VAR] = "personal"
		os.environ["REWARDS_PERSISTENCE"] = "true"
		self.assertEqual(main.main(), 0)
		self.assertIn("personal", daily_completion.load_completed_today(self.tmp.name))

	def test_picker_session_runs_chosen_profile_only(self) -> None:
		os.environ.pop("REWARDS_LAUNCHED_FROM_GUI", None)
		os.environ["REWARDS_PROFILE_PICKER"] = "true"
		os.environ[accounts.ACCOUNTS_ENV_VAR] = "personal,spare"
		personal = accounts.Account(
			name="personal",
			user_data_dir=os.path.join("data-dir", "personal"),
			profile_name="Default",
		)
		with mock.patch.object(profile_picker, "choose_account", side_effect=[personal, None]):
			self.assertEqual(main.main(), 0)
		self.assertEqual(self.calls, ["personal"])


if __name__ == "__main__":
	unittest.main()
