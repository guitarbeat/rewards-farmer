"""Unit tests for mobile search emulation and cooldown pacing (Milestone 4)."""

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import rewards_tasks
from fakes import FakeDriver
from sites.ms_rewards.tasks.searches import MOBILE_UA, SearchTasks


class FakeCDPDriver(FakeDriver):
	def __init__(self):
		super().__init__()
		self.cdp_calls = []

	def execute_cdp_cmd(self, cmd, params):
		self.cdp_calls.append((cmd, params))
		return {}


def make_search_tasks(driver=None):
	tasks = rewards_tasks.RewardsTaskUtils.__new__(rewards_tasks.RewardsTaskUtils)
	tasks.driver = driver or FakeCDPDriver()
	tasks.tab_utils = types.SimpleNamespace(
		close_all_other_tabs=lambda: None,
		ensure_focus=lambda: None,
	)
	tasks.keyboard = types.SimpleNamespace(send_keys=lambda text: None)
	tasks.elements = types.SimpleNamespace(
		get_points_breakdown_button=lambda: "btn",
		get_generic_sidebar_close_button=lambda: "close",
		get_bing_search_bar=lambda: "bar",
		get_clear_bing_search_query_button=lambda: "clear",
		get_mobile_search_points_on_points_breakdown=lambda: (0, 60),
		get_points_earned_from_searches_on_points_breakdown=lambda: (0, 30),
	)
	tasks.wait_for_then_click = lambda getter, timeout=10: None
	tasks.wait_for_element = lambda getter, timeout=10: getter()
	tasks.move_to_and_click = lambda el: None
	tasks.switch_to_earn_page = lambda: None
	return tasks


class MobileSearchEmulationTests(unittest.TestCase):
	def test_set_mobile_emulation_enables_cdp(self):
		driver = FakeCDPDriver()
		tasks = make_search_tasks(driver)

		tasks.set_mobile_emulation(True)

		cmds = [call[0] for call in driver.cdp_calls]
		self.assertIn("Network.setUserAgentOverride", cmds)
		self.assertIn("Emulation.setDeviceMetricsOverride", cmds)

		ua_call = next(call for call in driver.cdp_calls if call[0] == "Network.setUserAgentOverride")
		self.assertEqual(ua_call[1].get("userAgent"), MOBILE_UA)

	def test_set_mobile_emulation_disables_cdp(self):
		driver = FakeCDPDriver()
		tasks = make_search_tasks(driver)

		tasks.set_mobile_emulation(False)

		cmds = [call[0] for call in driver.cdp_calls]
		self.assertIn("Emulation.clearDeviceMetricsOverride", cmds)
		self.assertIn("Network.setUserAgentOverride", cmds)

		ua_call = next(call for call in driver.cdp_calls if call[0] == "Network.setUserAgentOverride")
		self.assertEqual(ua_call[1].get("userAgent"), "")

	def test_set_mobile_emulation_tolerates_driver_without_cdp(self):
		driver = FakeDriver()  # FakeDriver does not have execute_cdp_cmd
		tasks = make_search_tasks(driver)

		# Should execute without throwing AttributeError or Exception
		tasks.set_mobile_emulation(True)
		tasks.set_mobile_emulation(False)

	def test_run_mobile_searches_executes_batches_and_restores_desktop(self):
		driver = FakeCDPDriver()
		tasks = make_search_tasks(driver)

		# Simulate 0/60 points initially, then 15/60 after batch 1, then 60/60 after batch 2
		readings = iter([(0, 60), (15, 60), (60, 60)])
		tasks.read_mobile_search_points = lambda: next(readings)

		batches_run = []
		tasks.run_search_batch = lambda count, already_sent=0: (batches_run.append(count), count)[1]

		tasks.run_mobile_searches(max_rounds=5)

		self.assertTrue(len(batches_run) >= 1)
		# Verify that desktop emulation was restored at the end
		last_cdp_cmd = driver.cdp_calls[-1][0]
		self.assertEqual(last_cdp_cmd, "Network.setUserAgentOverride")
		self.assertEqual(driver.cdp_calls[-1][1].get("userAgent"), "")

	def test_run_mobile_searches_stops_on_zero_points_yield(self):
		driver = FakeCDPDriver()
		tasks = make_search_tasks(driver)

		# Simulate 0/60 points initially, then 0/60 again (no yield / cooldown)
		readings = iter([(0, 60), (0, 60)])
		tasks.read_mobile_search_points = lambda: next(readings)

		batches_run = []
		tasks.run_search_batch = lambda count, already_sent=0: (batches_run.append(count), count)[1]

		tasks.run_mobile_searches(max_rounds=5)

		# Should only run 1 round and abort early
		self.assertEqual(len(batches_run), 1)

	def test_complete_required_searches_triggers_mobile_when_flag_enabled(self):
		tasks = make_search_tasks()
		tasks.read_search_points = lambda: (30, 30)  # Desktop searches already complete

		mobile_called = []
		tasks.run_mobile_searches = lambda: mobile_called.append(True)

		with mock.patch.dict(os.environ, {"ENABLE_MOBILE_SEARCH": "1"}):
			tasks.complete_required_searches()

		self.assertEqual(mobile_called, [True])

	def test_complete_required_searches_skips_mobile_when_flag_disabled(self):
		tasks = make_search_tasks()
		tasks.read_search_points = lambda: (30, 30)

		mobile_called = []
		tasks.run_mobile_searches = lambda: mobile_called.append(True)

		with mock.patch.dict(os.environ, {"ENABLE_MOBILE_SEARCH": "0"}):
			tasks.complete_required_searches()

		self.assertEqual(mobile_called, [])

	def test_search_burst_limit_caps_searches(self):
		tasks = make_search_tasks()
		# 0/60 requires 20 searches, but burst limit is 4
		readings = iter([(0, 60), (60, 60)])
		tasks.read_search_points = lambda: next(readings)

		batch_sizes = []
		tasks.run_search_batch = lambda count, already_sent=0: (batch_sizes.append(count), count)[1]

		with mock.patch.dict(os.environ, {"SEARCH_BURST_LIMIT": "4"}):
			tasks.complete_required_searches()

		self.assertEqual(batch_sizes, [4])


if __name__ == "__main__":
	unittest.main()
