"""pywebview desktop shell for the Rewards Farmer launcher."""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import asdict
from typing import Any

import launcher_controller as controller
import launcher_runtime as runtime
from launcher import install_crash_hooks, write_crash_log

REPO_ROOT = runtime.REPO_ROOT
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "launcher_web")
INDEX_HTML = os.path.join(WEB_DIR, "index.html")
ICON_ICO = os.path.join(REPO_ROOT, "assets", "rewards-farmer.ico")
ICON_PNG = os.path.join(REPO_ROOT, "assets", "rewards-farmer.png")


def resolve_window_icon() -> str | None:
	if sys.platform == "win32" and os.path.isfile(ICON_ICO):
		return ICON_ICO
	if os.path.isfile(ICON_PNG):
		return ICON_PNG
	if os.path.isfile(ICON_ICO):
		return ICON_ICO
	return None


def snapshot_to_dict(snapshot: controller.LauncherSnapshot) -> dict[str, Any]:
	payload = asdict(snapshot)
	payload["progress_rows"] = [asdict(row) for row in snapshot.progress_rows]
	return payload


class LauncherBridge:
	"""Methods exposed to JavaScript as pywebview.api.*"""

	def __init__(self) -> None:
		self._pending_logs: list[dict[str, str | None]] = []
		self._latest_snapshot: dict[str, Any] | None = None
		self.controller = controller.LauncherController(
			on_log_line=self._on_log_line,
			on_state_changed=self._on_state_changed,
		)
		self._latest_snapshot = snapshot_to_dict(self.controller.initial_snapshot())

	def _on_log_line(self, line: str, tag: str | None) -> None:
		self._pending_logs.append({"text": line, "tag": tag})

	def _on_state_changed(self, snapshot: controller.LauncherSnapshot) -> None:
		self._latest_snapshot = snapshot_to_dict(snapshot)

	def bootstrap(self) -> dict[str, Any]:
		logs = [
			{"text": line, "tag": tag}
			for line, tag in self.controller.initial_log_lines()
		]
		self._pending_logs = []
		self._latest_snapshot = snapshot_to_dict(self.controller.initial_snapshot())
		return {
			"snapshot": self._latest_snapshot,
			"logs": logs,
		}

	def poll(self) -> dict[str, Any]:
		finished = self.controller.poll_output()
		logs = self._pending_logs
		self._pending_logs = []
		return {
			"finished": finished,
			"logs": logs,
			"snapshot": self._latest_snapshot
			or snapshot_to_dict(self.controller.initial_snapshot()),
		}

	def start_run(self) -> dict[str, str | None]:
		error = self.controller.start_run()
		return {"error": error}

	def stop_run(self) -> dict[str, str | None]:
		self.controller.stop_run()
		return {"error": None}

	def clear_log(self) -> dict[str, str | None]:
		error = self.controller.clear_log()
		return {"error": error}

	def get_run_log(self, run_number: int) -> dict[str, str]:
		return {"text": self.controller.get_run_log(int(run_number))}

	def open_logs(self) -> None:
		self.controller.open_logs_folder()

	def open_profile(self) -> None:
		self.controller.open_profile_folder()

	def request_close(self) -> bool:
		if not self.controller.is_run_active():
			return True
		self.controller.stop_run()
		return False


def main() -> int:
	install_crash_hooks()

	if not os.path.isfile(INDEX_HTML):
		write_crash_log(text=f"Missing web UI: {INDEX_HTML}")
		print(f"Missing web UI: {INDEX_HTML}", file=sys.stderr)
		return 1

	try:
		import webview
	except ImportError as exc:
		write_crash_log(exc)
		print(
			f"pywebview is not installed. Run {runtime.SETUP_HINT}, or use the CustomTkinter launcher.",
			file=sys.stderr,
		)
		return 1

	bridge = LauncherBridge()
	window = webview.create_window(
		"Rewards Farmer",
		url=INDEX_HTML,
		js_api=bridge,
		width=900,
		height=820,
		min_size=(720, 640),
		background_color="#E8EEF5",
		text_select=True,
		confirm_close=False,
	)

	def _on_closing() -> bool:
		if not bridge.controller.is_run_active():
			return True

		bridge.controller.stop_run()

		def _wait_then_destroy() -> None:
			for _ in range(50):
				bridge.controller.poll_output()
				if not bridge.controller.is_run_active():
					break
				threading.Event().wait(0.1)
			try:
				window.destroy()
			except Exception:
				pass

		threading.Thread(target=_wait_then_destroy, daemon=True).start()
		return False

	window.events.closing += _on_closing

	icon = resolve_window_icon()
	if sys.platform == "win32":
		try:
			webview.start(gui="edgechromium", private_mode=True, icon=icon)
			return 0
		except Exception:
			pass

	webview.start(private_mode=True, icon=icon)
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except Exception as exc:
		write_crash_log(exc)
		raise
