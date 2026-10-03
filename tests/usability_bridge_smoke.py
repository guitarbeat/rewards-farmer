"""Scripted usability path for the webview bridge (no native mouse)."""

from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import launcher_controller as ctl
import launcher_webview as web


class FakeProc:
	def __init__(self) -> None:
		self.stdout = iter([])
		self._code = None

	def poll(self):
		return self._code

	def wait(self):
		self._code = 0
		return 0


def main() -> int:
	tmp = tempfile.TemporaryDirectory()
	log_file = os.path.join(tmp.name, "runs.log")
	image = os.path.join(tmp.name, "visual_search.jpg")
	open(image, "wb").write(b"x")

	patches = [
		mock.patch.object(ctl, "RUN_LOG_FILE", log_file),
		mock.patch.object(ctl.runtime, "preflight_issues", return_value=[]),
		mock.patch.object(ctl.runtime, "preflight_warnings", return_value=[]),
		mock.patch.object(ctl.runtime, "read_log_tail", return_value=""),
		mock.patch.object(ctl.runtime, "readiness_summary", return_value="Ready for usability check"),
		mock.patch.object(ctl.runtime, "ensure_visual_search_image", return_value=True),
		mock.patch.object(ctl.runtime, "VISUAL_SEARCH_IMAGE", image),
	]
	for patcher in patches:
		patcher.start()

	bridge = web.LauncherBridge()
	boot = bridge.bootstrap()
	assert boot["snapshot"]["run_enabled"], boot
	assert boot["snapshot"]["run_button_text"] == "Run"

	fake = FakeProc()
	# Keep the fake process "running" until we stop; don't auto-finish via empty stdout.
	with mock.patch.object(ctl.runtime, "spawn_run_process", return_value=fake), mock.patch.object(
		ctl.LauncherController, "_reader_thread", lambda self, process: None
	):
		err = bridge.start_run()
		assert err["error"] is None, err

		bridge.controller._process_log_text("[STEP] Starting browser\n", to_file=False)
		bridge.controller._process_log_text("[OK] Starting browser\n", to_file=False)
		bridge.controller._process_log_text("[STEP] Bing daily set\n", to_file=False)
		polled = bridge.poll()
		assert polled["logs"], polled
		assert any(r["state"] == "running" for r in polled["snapshot"]["progress_rows"]), polled["snapshot"]["progress_rows"]
		assert polled["snapshot"]["stop_enabled"], polled["snapshot"]

		bridge.stop_run()
		fake._code = 0
		bridge.controller.output_queue.put(None)
		finished = bridge.poll()
		assert finished["snapshot"]["run_enabled"]
		assert finished["snapshot"]["run_button_text"] == "Run again"

		cleared = bridge.clear_log()
		assert cleared["error"] is None

		print("USABILITY_BRIDGE_OK")
		print("status:", finished["snapshot"]["status_text"])
		print("rows:", len(finished["snapshot"]["progress_rows"]))
	tmp.cleanup()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
