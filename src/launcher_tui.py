"""Textual terminal UI for the Rewards Farmer launcher."""

from __future__ import annotations

import sys
from datetime import datetime

import daily_schedule
import launcher_controller as controller
import launcher_runtime as runtime
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import (
	Button,
	Checkbox,
	Footer,
	Header,
	Label,
	ListItem,
	ListView,
	ProgressBar,
	RichLog,
	Select,
	Static,
	TabbedContent,
	TabPane,
)

_UNICODE_ICONS = {
	"pending": "○",
	"running": "●",
	"ok": "✓",
	"skip": "–",
	"fail": "✕",
}
_ASCII_ICONS = {
	"pending": "[ ]",
	"running": "[>]",
	"ok": "[ok]",
	"skip": "[-]",
	"fail": "[x]",
}

TASK_TOGGLE_MAP: dict[str, str] = {
	"task-daily-set": "Bing daily set",
	"task-explore": "Explore on Bing",
	"task-visual": "Visual search",
	"task-misc": "Misc cards",
	"task-searches": "Required searches",
	"task-bonus": "Bonus points",
}


def _icons() -> dict[str, str]:
	encoding = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
	if encoding in {"utf8", "utf16", "cp65001"}:
		return _UNICODE_ICONS
	return _ASCII_ICONS


class RewardsFarmerApp(App):
	"""Launcher screens: configuration, live metrics, progress, and logs."""

	TITLE = "Rewards Farmer"
	CSS = """
	Screen {
		layout: vertical;
		overflow: hidden;
	}

	#setup, #schedule {
		height: 1;
		padding: 0 1;
		color: $text-muted;
	}

	ToastRack {
		margin-bottom: 0;
		height: auto;
	}

	Toast {
		margin-top: 0;
		padding: 0 1;
		height: 1;
		width: 1fr;
		max-width: 100%;
	}

	/* Two-column layout */
	#main-view {
		layout: horizontal;
		height: 1fr;
		width: 100%;
	}

	#sidebar-pane {
		width: 38;
		height: 1fr;
		padding: 0 1 0 0;
	}

	#content-pane {
		width: 1fr;
		height: 1fr;
		padding: 0;
	}

	/* Cohesive panel framing */
	#panel-config, #panel-dashboard, #panel-progress {
		border: round $surface-lighten-2;
		border-title-align: left;
		border-title-style: bold;
		border-title-color: $text-muted;
		height: auto;
		margin-bottom: 0;
		padding: 0 1;
	}

	#panel-config:focus-within, #panel-dashboard:focus-within {
		border: round $primary;
		border-title-color: $primary;
	}

	#panel-progress {
		max-height: 8;
	}

	/* Profile selection */
	#profile-select {
		height: auto;
		margin: 0;
		padding: 0;
		border: none;
	}

	/* Task toggle grid */
	#task-toggles-grid {
		layout: grid;
		grid-size: 2;
		grid-columns: 1fr 1fr;
		height: auto;
		margin: 0;
		padding: 0;
	}

	#task-toggles-grid Checkbox {
		height: 1;
		margin: 0;
		padding: 0;
		background: transparent;
		border: none;
	}

	/* Telemetry & metrics styling */
	#stat-points, #active-step-label, #timer-search-delay, #timer-schedule-window {
		height: 1;
		padding: 0;
	}

	.points-positive {
		color: $success;
		text-style: bold;
	}

	.points-zero {
		color: $text-muted;
	}

	.step-active {
		color: $accent;
		text-style: bold;
	}

	.step-idle {
		color: $text-muted;
	}

	.timer-active {
		color: $warning;
		text-style: bold;
	}

	.timer-idle {
		color: $text-muted;
	}

	#active-step-bar {
		height: 1;
		margin: 0;
		padding: 0;
		border: none;
	}

	/* Action buttons */
	#actions {
		layout: grid;
		grid-size: 3 2;
		grid-columns: 1fr 1fr 1fr;
		height: 2;
		margin: 0;
		padding: 0;
	}

	#actions Button {
		height: 1;
		margin: 0;
		padding: 0 1;
		border: none;
		min-width: 5;
		background: $surface-lighten-1;
		color: $text;
	}

	#actions Button:hover {
		background: $surface-lighten-2;
	}

	#actions #run {
		background: $success 28%;
		color: $success;
		text-style: bold;
	}

	#actions #run:hover {
		background: $success 45%;
	}

	#actions #stop {
		background: $error 28%;
		color: $error;
		text-style: bold;
	}

	#actions #stop:hover {
		background: $error 45%;
	}

	#actions Button:disabled {
		opacity: 35%;
	}

	/* Progress rows and step checklist */
	#progress-summary {
		height: 1;
		padding: 0;
		color: $text-muted;
	}

	#progress {
		height: auto;
		padding: 0;
	}

	.step {
		height: 1;
		padding: 0 1;
		color: $text-muted;
	}

	.step-running {
		color: $accent;
		text-style: bold;
	}

	.step-ok {
		color: $success;
	}

	.step-skip {
		color: $text-muted;
	}

	.step-fail {
		color: $error;
		text-style: bold;
	}

	/* Tabbed content */
	#panel-tabs {
		height: 1fr;
		margin: 0;
		padding: 0;
	}

	#tab-log, #tab-history {
		height: 1fr;
		padding: 0;
	}

	#log-panel {
		height: 1fr;
		margin: 0;
		border: none;
		scrollbar-size: 1 1;
	}

	#log {
		height: 1fr;
		background: $surface-darken-1;
		color: $text;
	}

	#history-count {
		height: 1;
		padding: 0 1;
		color: $text-muted;
	}

	#history {
		height: 1fr;
		margin: 0;
		background: $surface-darken-1;
	}

	#history ListItem {
		height: 1;
		padding: 0 1;
	}

	/* Bottom status bar */
	#status {
		dock: bottom;
		height: 1;
		padding: 0 1;
		background: $surface;
		color: $text;
	}

	#status.tone-success {
		color: $success;
		text-style: bold;
	}

	#status.tone-warning {
		color: $warning;
		text-style: bold;
	}

	#status.tone-danger {
		color: $error;
		text-style: bold;
	}

	#status.tone-running {
		color: $accent;
		text-style: bold;
	}

	#status.tone-idle {
		color: $text-muted;
	}

	/* Responsive compact rules for short screens (<= 28 rows) */
	Screen.compact-height #sidebar-pane {
		width: 36;
		padding: 0;
	}

	Screen.compact-height #content-pane {
		padding: 0;
	}

	Screen.compact-height #panel-progress {
		max-height: 6;
	}

	Screen.compact-height #actions Button {
		padding: 0;
	}

	/* Responsive compact rules for narrow screens (< 90 cols) */
	Screen.compact-width #sidebar-pane {
		width: 36;
	}
	"""

	BINDINGS = [
		Binding("r", "run", "Run"),
		Binding("ctrl+enter", "run", "Run", show=False),
		Binding("escape", "stop", "Stop"),
		Binding("l", "toggle_log", "Log"),
		Binding("d", "arm_daily", "Daily"),
		Binding("ctrl+d", "remove_daily", "Undaily", show=False),
		Binding("ctrl+c", "quit_app", "Quit", show=False),
		Binding("q", "quit_app", "Quit"),
	]

	def __init__(self) -> None:
		super().__init__()
		self.controller = controller.LauncherController(
			on_log_line=self._on_log_line,
			on_state_changed=self._on_state_changed,
		)
		self._pending_logs: list[tuple[str, str | None]] = []
		self._snapshot: controller.LauncherSnapshot | None = None
		self._progress_key: tuple = ()
		self._history_key = ""
		self._viewing_run: int | None = None
		self._log_visible = False
		self._quit_after_stop = False
		self._schedule_line = daily_schedule.status_line(None)

	def compose(self) -> ComposeResult:
		yield Header()
		yield Static("", id="setup")
		yield Static("", id="schedule")

		profiles = self.controller.get_available_profiles()
		if not profiles:
			profiles = [("Default", "Default profile")]
		profile_options = [(label, name) for name, label in profiles]
		if len(profiles) > 1:
			profile_options = [("All Profiles", "all")] + profile_options
		if self.controller.selected_profile:
			initial_profile = self.controller.selected_profile
		elif any(name == "Default" for name, _ in profiles):
			initial_profile = "Default"
		else:
			initial_profile = profile_options[0][1]

		with Horizontal(id="main-view"):
			with Vertical(id="sidebar-pane"):
				cfg = Container(id="panel-config")
				cfg.border_title = " Profile & Tasks "
				with cfg:
					yield Select[str](
						profile_options,
						value=initial_profile,
						id="profile-select",
						compact=True,
						allow_blank=False,
					)
					with Grid(id="task-toggles-grid"):
						yield Checkbox("Daily Set", value=True, id="task-daily-set", compact=True)
						yield Checkbox("Explore", value=True, id="task-explore", compact=True)
						yield Checkbox("Visual", value=True, id="task-visual", compact=True)
						yield Checkbox("Misc Cards", value=True, id="task-misc", compact=True)
						yield Checkbox("Searches", value=True, id="task-searches", compact=True)
						yield Checkbox("Bonus", value=True, id="task-bonus", compact=True)

				dash = Container(id="panel-dashboard")
				dash.border_title = " Session Telemetry "
				with dash:
					yield Static("Points: +0  ·  Session: +0", id="stat-points")
					yield Static("▶ Ready", id="active-step-label")
					yield ProgressBar(id="active-step-bar", show_eta=False, show_percentage=True)
					yield Static("⏳ Delay: idle", id="timer-search-delay")
					yield Static("⏰ Daily: idle", id="timer-schedule-window")

				with Horizontal(id="actions"):
					yield Button("Run", id="run", variant="success")
					yield Button("Stop", id="stop", variant="error", disabled=True)
					yield Button("Daily", id="daily")
					yield Button("Logs", id="open-logs")
					yield Button("Profile", id="open-profile")
					yield Button("Clear", id="clear-log")

			with Vertical(id="content-pane"):
				prog = Container(id="panel-progress")
				prog.border_title = " Step Progress "
				with prog:
					yield Static("Run progress", id="progress-summary")
					yield Vertical(id="progress")

				with TabbedContent(id="panel-tabs"):
					with TabPane("Console Log", id="tab-log"):
						with VerticalScroll(id="log-panel"):
							yield RichLog(id="log", markup=False, wrap=True, highlight=False)
					with TabPane("Past Runs", id="tab-history"):
						yield Static("Past runs", id="history-count")
						yield ListView(id="history")

		yield Static("Ready to run", id="status")
		yield Footer()

	def on_mount(self) -> None:
		if self.size.height <= 28:
			self.screen.add_class("compact-height")
		if self.size.width < 90:
			self.screen.add_class("compact-width")

		self._log_visible = True
		self.query_one("#log-panel").display = True
		for line, tag in self.controller.initial_log_lines():
			self._pending_logs.append((line, tag))
		self._snapshot = self.controller.initial_snapshot()
		self._schedule_line = daily_schedule.status_line(daily_schedule.load_plan())

		# Populate #profile-select
		try:
			select = self.query_one("#profile-select", Select)
			profiles = self.controller.get_available_profiles()
			if not profiles:
				profiles = [("Default", "Default profile")]
			options = [(label, name) for name, label in profiles]
			if len(profiles) > 1:
				options = [("All Profiles", "all")] + options
			select.set_options(options)
			if self.controller.selected_profile:
				select.value = self.controller.selected_profile
			elif any(name == "Default" for name, _ in profiles):
				select.value = "Default"
		except NoMatches:
			pass

		# Sync initial checkbox states with controller
		for cb_id, task_name in TASK_TOGGLE_MAP.items():
			try:
				cb = self.query_one(f"#{cb_id}", Checkbox)
				cb.value = self.controller.is_task_enabled(task_name)
			except NoMatches:
				pass

		# Set active tab based on history existence
		try:
			tabs = self.query_one("#panel-tabs", TabbedContent)
			if self._snapshot and self._snapshot.run_history:
				tabs.active = "tab-history"
			else:
				tabs.active = "tab-log"
		except NoMatches:
			pass

		self._flush_logs()
		self._paint()
		self.set_interval(0.25, self._poll)
		self.set_interval(30, self._maybe_daily)

	def on_resize(self, event) -> None:
		self.screen.set_class(event.size.height <= 28, "compact-height")
		self.screen.set_class(event.size.width < 90, "compact-width")

	def on_select_changed(self, event: Select.Changed) -> None:
		if event.select.id == "profile-select":
			val = None if (event.value is Select.BLANK or event.value is None) else str(event.value)
			if self.controller.selected_profile != val:
				self.controller.set_selected_profile(val)

	def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
		cb_id = event.checkbox.id or ""
		task_name = TASK_TOGGLE_MAP.get(cb_id)
		if task_name is not None:
			if self.controller.is_task_enabled(task_name) != bool(event.value):
				self.controller.set_task_enabled(task_name, bool(event.value))
			has_tasks = any(self.controller.enabled_tasks)
			try:
				run_btn = self.query_one("#run", Button)
				if not has_tasks:
					run_btn.disabled = True
				elif self._snapshot is not None:
					run_btn.disabled = not self._snapshot.run_enabled
			except NoMatches:
				pass

	def _on_log_line(self, line: str, tag: str | None) -> None:
		self._pending_logs.append((line, tag))

	def _on_state_changed(self, snapshot: controller.LauncherSnapshot) -> None:
		self._snapshot = snapshot
		if self.is_running:
			self._paint()

	def _poll(self) -> None:
		if not self.is_running or not self.query("#setup"):
			return
		self.controller.poll_output()
		self._flush_logs()
		self._paint()
		if self._quit_after_stop and not self.controller.is_run_active():
			self.exit()

	def _maybe_daily(self) -> None:
		if not self.is_running or self.controller.is_run_active():
			return
		plan = daily_schedule.load_plan()
		if not daily_schedule.autostart_due(
			datetime.now(),
			plan,
			claimed=daily_schedule.claimed_today(),
			unfinished=daily_schedule.unfinished_accounts() if plan is not None else False,
		):
			return
		if not daily_schedule.claim_today():
			return
		error = self.controller.start_run()
		if error:
			daily_schedule.release_claim()
			self.notify(error, severity="error", timeout=8)
			return
		self._set_log_visible(True)
		try:
			self.query_one("#panel-tabs", TabbedContent).active = "tab-log"
		except NoMatches:
			pass
		self.notify("Starting today's daily run. Esc stops it.", timeout=5)
		self._schedule_line = daily_schedule.status_line(daily_schedule.load_plan())
		self._paint()

	def _flush_logs(self) -> None:
		if self._viewing_run is not None or not self._pending_logs:
			if self._viewing_run is not None:
				self._pending_logs.clear()
			return
		log = self.query_one("#log", RichLog)
		for line, _tag in self._pending_logs:
			log.write(line.rstrip("\r\n"))
		self._pending_logs.clear()

	def _paint(self) -> None:
		snapshot = self._snapshot
		if snapshot is None or not self.query("#setup"):
			return

		try:
			self.sub_title = snapshot.subtitle
			self.query_one("#setup", Static).update(snapshot.setup_strip)
			self.query_one("#schedule", Static).update(self._schedule_line)
			summary = snapshot.progress_summary
			if snapshot.running:
				summary = f"{summary}  ·  {snapshot.status_text}"
			self.query_one("#progress-summary", Static).update(f"Run progress  {summary}")
			status = self.query_one("#status", Static)
			status.update(f"{snapshot.status_text}   {snapshot.run_count_label}")
			status.set_classes(f"tone-{snapshot.status_tone}")

			# Button disabled states
			has_tasks = any(snapshot.enabled_tasks.values()) if snapshot.enabled_tasks else bool(self.controller.enabled_tasks)
			run = self.query_one("#run", Button)
			run.disabled = (not snapshot.run_enabled) or (not has_tasks)
			run.label = snapshot.run_button_text
			self.query_one("#stop", Button).disabled = not snapshot.stop_enabled

			# Live Dashboard widgets
			self._paint_dashboard(snapshot)

			# Controls locked/enabled state
			self._paint_controls_state(snapshot)

			self._paint_progress(snapshot.progress_rows)
			self._paint_history(snapshot.run_history)
		except NoMatches:
			return

	def _paint_dashboard(self, snapshot: controller.LauncherSnapshot) -> None:
		try:
			pts_w = self.query_one("#stat-points", Static)
			pts_w.update(
				f"Points: +{snapshot.points_earned}  ·  Session: +{snapshot.session_points}"
			)
			pts_w.set_classes("points-positive" if (snapshot.points_earned > 0 or snapshot.session_points > 0) else "points-zero")
		except NoMatches:
			pass

		try:
			step_label = self.query_one("#active-step-label", Static)
			if snapshot.running:
				step_name = snapshot.active_step or snapshot.status_text or "Running…"
				detail = f": {snapshot.active_step_detail}" if snapshot.active_step_detail else ""
				step_label.update(f"▶ {step_name}{detail}")
				step_label.set_classes("step-active")
			elif snapshot.status_text and snapshot.status_text != "Ready to run":
				step_label.update(f"▶ {snapshot.status_text}")
				step_label.set_classes("step-active")
			else:
				step_label.update("▶ Ready")
				step_label.set_classes("step-idle")
		except NoMatches:
			pass

		try:
			total_steps = max(1, len(snapshot.progress_rows))
			completed_steps = sum(1 for row in snapshot.progress_rows if row.state in ("ok", "skip", "fail"))
			self.query_one("#active-step-bar", ProgressBar).update(total=total_steps, progress=completed_steps)
		except NoMatches:
			pass

		try:
			delay_widget = self.query_one("#timer-search-delay", Static)
			if snapshot.search_delay_remaining is not None and snapshot.search_delay_remaining > 0:
				delay_widget.update(f"⏳ Delay: {snapshot.search_delay_remaining:.1f}s")
				delay_widget.set_classes("timer-active")
			else:
				delay_widget.update("⏳ Delay: idle")
				delay_widget.set_classes("timer-idle")
		except NoMatches:
			pass

		try:
			sched_widget = self.query_one("#timer-schedule-window", Static)
			if snapshot.daily_schedule_countdown:
				sched_widget.update(f"⏰ Daily: {snapshot.daily_schedule_countdown}")
				sched_widget.set_classes("timer-active")
			elif daily_schedule.claimed_today():
				sched_widget.update("⏰ Daily: completed today")
				sched_widget.set_classes("timer-idle")
			else:
				sched_widget.update("⏰ Daily: idle")
				sched_widget.set_classes("timer-idle")
		except NoMatches:
			pass

	def _paint_controls_state(self, snapshot: controller.LauncherSnapshot) -> None:
		is_running = snapshot.running
		try:
			self.query_one("#profile-select", Select).disabled = is_running
		except NoMatches:
			pass

		for cb_id in TASK_TOGGLE_MAP:
			try:
				self.query_one(f"#{cb_id}", Checkbox).disabled = is_running
			except NoMatches:
				pass

	def _paint_progress(self, rows) -> None:
		key = tuple((row.name, row.state, row.detail) for row in rows)
		if key == self._progress_key:
			return
		box = self.query_one("#progress", Vertical)
		children = list(box.children)
		if len(children) != len(rows):
			box.remove_children()
			box.mount(*(Static("", classes="step") for _row in rows))
			children = list(box.children)
		if len(children) != len(rows):
			return
		icons = _icons()
		for widget, row in zip(children, rows):
			icon = icons.get(row.state, icons["pending"])
			detail = f"  {row.detail}" if row.detail else ""
			widget.update(f"{icon} {row.name}{detail}")
			widget.set_classes(f"step step-{row.state}")
		self._progress_key = key

	def _paint_history(self, entries: list[dict]) -> None:
		count = self.query_one("#history-count", Static)
		count.update(f"Past runs  {len(entries)}")
		key = "|".join(
			f"{entry.get('number')}:{entry.get('finished')}:{entry.get('summary')}"
			for entry in entries
		)
		if key == self._history_key:
			return
		self._history_key = key
		history = self.query_one("#history", ListView)
		history.clear()
		if not entries:
			history.append(ListItem(Label("No past runs yet."), name="empty"))
			return
		for entry in entries:
			number = entry.get("number")
			label = f"#{number}  {entry.get('started') or ''}  —  {entry.get('summary') or ''}"
			history.append(ListItem(Label(label), name=str(number)))

	def _show_run_log(self, run_number: int) -> None:
		self._viewing_run = run_number
		text = self.controller.get_run_log(run_number)
		log = self.query_one("#log", RichLog)
		log.clear()
		for line in text.splitlines():
			log.write(line)
		self._set_log_visible(True)
		try:
			self.query_one("#panel-tabs", TabbedContent).active = "tab-log"
		except NoMatches:
			pass

	def _set_log_visible(self, visible: bool) -> None:
		self._log_visible = visible
		try:
			self.query_one("#log-panel").display = visible
		except NoMatches:
			pass

	def action_toggle_log(self) -> None:
		try:
			tabs = self.query_one("#panel-tabs", TabbedContent)
			if self._viewing_run is not None:
				self._viewing_run = None
				log = self.query_one("#log", RichLog)
				log.clear()
				for line in self.controller.get_log_text().splitlines()[-200:]:
					log.write(line)
				self._set_log_visible(True)
				tabs.active = "tab-log"
				return
			if tabs.active == "tab-log":
				tabs.active = "tab-history"
				self._set_log_visible(False)
			else:
				tabs.active = "tab-log"
				self._set_log_visible(True)
		except NoMatches:
			pass

	def action_run(self) -> None:
		if not self.controller.enabled_tasks:
			self.notify("No tasks enabled — select at least one task to run.", severity="warning")
			return
		self._viewing_run = None
		error = self.controller.start_run()
		if error:
			title = "Setup required" if any(word in error for word in ("Setup", "Missing", "data-dir")) else "Could not start"
			self.notify(f"{title}\n{error}", severity="error", timeout=8)
			return
		daily_schedule.claim_today()
		self._set_log_visible(True)
		try:
			self.query_one("#panel-tabs", TabbedContent).active = "tab-log"
		except NoMatches:
			pass
		self._paint()

	def action_arm_daily(self) -> None:
		try:
			result = daily_schedule.install_daily_trigger()
		except RuntimeError as exc:
			self.notify(str(exc), severity="error", timeout=8)
			return
		self._schedule_line = result.status_line
		self.query_one("#schedule", Static).update(result.status_line)
		self.notify("Daily trigger armed.", timeout=4)

	def action_remove_daily(self) -> None:
		try:
			message = daily_schedule.remove_daily_trigger()
		except RuntimeError as exc:
			self.notify(str(exc), severity="error", timeout=8)
			return
		self._schedule_line = daily_schedule.status_line(None)
		self.query_one("#schedule", Static).update(self._schedule_line)
		self.notify(message, timeout=4)

	def action_stop(self) -> None:
		self.controller.stop_run()
		self._paint()

	def action_quit_app(self) -> None:
		if self.controller.is_run_active():
			self.controller.stop_run()
			self._quit_after_stop = True
			self.notify("Stopping the run…", timeout=3)
			return
		self.exit()

	def on_button_pressed(self, event: Button.Pressed) -> None:
		button_id = event.button.id
		if button_id == "run":
			self.action_run()
		elif button_id == "stop":
			self.action_stop()
		elif button_id == "open-logs":
			self.controller.open_logs_folder()
		elif button_id == "open-profile":
			self.controller.open_profile_folder()
		elif button_id == "clear-log":
			error = self.controller.clear_log()
			if error:
				self.notify(error, severity="warning")
				return
			self._viewing_run = None
			self._history_key = ""
			self.query_one("#log", RichLog).clear()
			self._paint()
		elif button_id == "daily":
			self.action_arm_daily()

	def on_list_view_selected(self, event: ListView.Selected) -> None:
		name = event.item.name or ""
		if not name.isdigit():
			return
		self._show_run_log(int(name))


def main() -> int:
	runtime.install_crash_hooks()
	lock = runtime.acquire_single_instance()
	if lock is None:
		print("Rewards Farmer is already open in another terminal.", file=sys.stderr)
		return 1
	try:
		RewardsFarmerApp().run()
	except Exception as exc:
		runtime.write_crash_log(exc)
		raise
	finally:
		runtime.release_single_instance(lock)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
