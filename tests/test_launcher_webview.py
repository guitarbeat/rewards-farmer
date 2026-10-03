"""Tests for the pywebview launcher bridge (no native window required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import launcher_controller as ctl
import launcher_webview as web


class SnapshotSerializationTests(unittest.TestCase):
	def test_snapshot_to_dict_includes_progress_rows(self) -> None:
		controller = ctl.LauncherController()
		payload = web.snapshot_to_dict(controller.initial_snapshot())

		self.assertIn("subtitle", payload)
		self.assertIn("progress_rows", payload)
		self.assertGreaterEqual(len(payload["progress_rows"]), 1)
		self.assertIn("name", payload["progress_rows"][0])
		self.assertIn("state", payload["progress_rows"][0])


class LauncherBridgeTests(unittest.TestCase):
	def setUp(self) -> None:
		self._tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self._tmp.cleanup)
		self.log_file = os.path.join(self._tmp.name, "runs.log")
		self.patchers = [
			mock.patch.object(ctl, "RUN_LOG_FILE", self.log_file),
			mock.patch.object(ctl.runtime, "preflight_issues", return_value=[]),
			mock.patch.object(ctl.runtime, "preflight_warnings", return_value=[]),
			mock.patch.object(ctl.runtime, "read_log_tail", return_value=""),
			mock.patch.object(ctl.runtime, "readiness_summary", return_value="Ready"),
		]
		for patcher in self.patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

		self.bridge = web.LauncherBridge()

	def test_bootstrap_returns_snapshot_and_logs(self) -> None:
		payload = self.bridge.bootstrap()
		self.assertIn("snapshot", payload)
		self.assertIn("logs", payload)
		self.assertTrue(payload["snapshot"]["run_enabled"])
		self.assertIn("run_history", payload["snapshot"])

	def test_get_run_log_returns_selected_run(self) -> None:
		self.bridge.controller._history_cache = None
		self.bridge.controller._process_log_text(
			"=== Run #1 started 2026-01-01 10:00:00 ===\n"
			"[OK] Bing daily set\n"
			"=== Run finished 10:01:00 (exit 0) ===\n",
			to_file=False,
		)
		self.bridge.controller._history_cache = None
		history = self.bridge.controller.run_history()
		self.assertEqual(len(history), 1)
		self.assertEqual(history[0]["number"], 1)
		result = self.bridge.get_run_log(1)
		self.assertIn("Run #1 started", result["text"])
		self.assertIn("[OK] Bing daily set", result["text"])

	def test_start_run_returns_error_when_preflight_fails(self) -> None:
		self.bridge.controller._preflight_issues = ["Missing data-dir"]
		result = self.bridge.start_run()
		self.assertIn("Missing data-dir", result["error"] or "")

	def test_poll_drains_pending_log_lines(self) -> None:
		self.bridge.controller._process_log_text("[OK] Bing daily set\n", to_file=False)
		result = self.bridge.poll()
		self.assertTrue(any("[OK]" in (entry["text"] or "") for entry in result["logs"]))
		self.assertIn("snapshot", result)


if __name__ == "__main__":
	unittest.main()
