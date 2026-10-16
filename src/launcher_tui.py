"""Textual terminal UI for the Rewards Farmer launcher."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
	try:
		sys.stdout.reconfigure(encoding="utf-8", errors="replace")
		sys.stderr.reconfigure(encoding="utf-8", errors="replace")
	except Exception:
		pass

import daily_schedule
import dotenv
import launcher_controller as controller
import launcher_runtime as runtime
from constants import DOTENV_PATH
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
	Button,
	Checkbox,
	Footer,
	Header,
	Input,
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

logger = logging.getLogger(__name__)


def save_env_settings(settings: dict[str, str], dotenv_path: str = DOTENV_PATH) -> None:
	"""Persist key-value settings to .env and update os.environ."""
	if not os.path.exists(dotenv_path):
		try:
			with open(dotenv_path, "w", encoding="utf-8") as f:
				f.write("# Rewards Farmer Configuration\n")
		except Exception as exc:
			logger.warning("Could not create .env file at %s: %s", dotenv_path, exc)

	for key, value in settings.items():
		os.environ[key] = str(value)
		try:
			dotenv.set_key(dotenv_path, key, str(value))
		except Exception as exc:
			logger.warning("Could not set %s in .env: %s", key, exc)


class SettingsModal(ModalScreen[bool]):
	"""Modal dialog for viewing and updating runtime configuration."""

	DEFAULT_CSS = """
	SettingsModal {
		align: center middle;
		background: rgba(0, 0, 0, 0.75);
	}

	#settings-dialog {
		width: 68;
		height: auto;
		max-height: 90%;
		border: round #58a6ff;
		background: #161b22;
		color: #e6edf3;
		padding: 1 2;
	}

	#settings-title {
		text-align: center;
		text-style: bold;
		color: #58a6ff;
		margin-bottom: 1;
	}

	.settings-label {
		color: #f0f6fc;
		text-style: bold;
		margin-top: 1;
		margin-bottom: 0;
	}

	.settings-desc {
		color: #8b949e;
		margin-bottom: 0;
	}

	#settings-dialog Input {
		margin-top: 0;
		margin-bottom: 0;
		background: #0d1117;
		border: round #30363d;
		color: #f0f6fc;
	}

	#settings-dialog Input:focus {
		border: round #58a6ff;
	}

	#settings-dialog Select {
		margin-top: 0;
		margin-bottom: 0;
		background: #0d1117;
		border: round #30363d;
		color: #f0f6fc;
	}

	#settings-dialog Select:focus {
		border: round #58a6ff;
	}

	#settings-dialog Checkbox {
		margin-top: 0;
		margin-bottom: 0;
		color: #8b949e;
	}

	#settings-dialog Checkbox.-on {
		color: #3fb950;
		text-style: bold;
	}

	#settings-buttons {
		margin-top: 1;
		align: right middle;
		height: 3;
	}

	#settings-buttons Button {
		margin-left: 1;
		min-width: 10;
		background: #21262d;
		color: #c9d1d9;
		border: none;
	}

	#settings-buttons Button:hover {
		background: #30363d;
		color: #f0f6fc;
	}

	#settings-buttons #btn-save {
		background: #238636;
		color: #ffffff;
		text-style: bold;
	}

	#settings-buttons #btn-save:hover {
		background: #2ea043;
	}
	"""

	BINDINGS = [
		Binding("escape", "cancel", "Cancel"),
	]

	def compose(self) -> ComposeResult:
		with Vertical(id="settings-dialog"):
			yield Static("⚙️ Configuration & Features", id="settings-title")

			with VerticalScroll(id="settings-scroll"):
				yield Label("Discord / Generic Webhook URL", classes="settings-label")
				yield Static("Receive notifications on run completion or failure", classes="settings-desc")
				yield Input(
					value=os.environ.get("WEBHOOK_URL", ""),
					placeholder="https://discord.com/api/webhooks/...",
					id="cfg-webhook-url",
				)

				yield Label("Webhook Failure Only", classes="settings-label")
				yield Checkbox(
					"Only notify when a task or run fails",
					value=os.environ.get("WEBHOOK_NOTIFY_ON_FAILURE_ONLY", "").strip().lower() in ("1", "true", "yes"),
					id="cfg-webhook-failure-only",
				)

				yield Label("Mobile Search Emulation", classes="settings-label")
				yield Checkbox(
					"Run mobile searches under iPhone UA/CDP emulation",
					value=os.environ.get("ENABLE_MOBILE_SEARCH", "").strip().lower() in ("1", "true", "yes"),
					id="cfg-enable-mobile-search",
				)

				yield Label("Search Burst Limit", classes="settings-label")
				yield Static("Searches per burst (0 = full batch, 4 = 15m cooldown)", classes="settings-desc")
				yield Input(
					value=os.environ.get("SEARCH_BURST_LIMIT", "0"),
					placeholder="0",
					id="cfg-burst-limit",
				)

				yield Label("Search Cooldown Delay (seconds)", classes="settings-label")
				yield Static("Delay between bursts (e.g. 900 for 15 min, 0 to skip)", classes="settings-desc")
				yield Input(
					value=os.environ.get("SEARCH_COOLDOWN_DELAY_SECONDS", "0"),
					placeholder="0",
					id="cfg-cooldown-delay",
				)

				yield Label("Query Source Backend", classes="settings-label")
				current_qs = os.environ.get("QUERY_SOURCE", "llm").strip().lower()
				yield Select[str](
					[("Ollama / Local LLM (llm)", "llm"), ("Public Bing Trends (trends)", "trends")],
					value=current_qs if current_qs in ("llm", "trends") else "llm",
					id="cfg-query-source",
					allow_blank=False,
				)

			with Horizontal(id="settings-buttons"):
				yield Button("Cancel", variant="default", id="btn-cancel")
				yield Button("Save", variant="primary", id="btn-save")

	def action_cancel(self) -> None:
		self.dismiss(False)

	def on_button_pressed(self, event: Button.Pressed) -> None:
		if event.button.id == "btn-cancel":
			self.dismiss(False)
		elif event.button.id == "btn-save":
			self._save_settings()

	def _save_settings(self) -> None:
		webhook_url = self.query_one("#cfg-webhook-url", Input).value.strip()
		webhook_fail_only = "true" if self.query_one("#cfg-webhook-failure-only", Checkbox).value else "false"
		enable_mobile = "true" if self.query_one("#cfg-enable-mobile-search", Checkbox).value else "false"
		burst_limit = self.query_one("#cfg-burst-limit", Input).value.strip() or "0"
		cooldown_delay = self.query_one("#cfg-cooldown-delay", Input).value.strip() or "0"
		query_source = str(self.query_one("#cfg-query-source", Select).value or "llm")

		settings = {
			"WEBHOOK_URL": webhook_url,
			"WEBHOOK_NOTIFY_ON_FAILURE_ONLY": webhook_fail_only,
			"ENABLE_MOBILE_SEARCH": enable_mobile,
			"SEARCH_BURST_LIMIT": burst_limit,
			"SEARCH_COOLDOWN_DELAY_SECONDS": cooldown_delay,
			"QUERY_SOURCE": query_source,
		}

		save_env_settings(settings)
		self.dismiss(True)


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
	"task-quests": "Quests",
	"task-searches": "Required searches",
	"task-bonus": "Bonus points",
}


def _is_unicode_supported() -> bool:
	if os.environ.get("REWARDS_FORCE_ASCII", "").strip().lower() in ("1", "true", "yes"):
		return False
	if os.environ.get("TERM") == "dumb":
		return False
	return True


def _icons() -> dict[str, str]:
	if _is_unicode_supported():
		return _UNICODE_ICONS
	return _ASCII_ICONS


_UNICODE_DASHBOARD = {
	"step": "▶",
	"delay": "⏳",
	"daily": "⏰",
}
_ASCII_DASHBOARD = {
	"step": ">",
	"delay": "[delay]",
	"daily": "[daily]",
}


def _dash_glyphs() -> dict[str, str]:
	if _is_unicode_supported():
		return _UNICODE_DASHBOARD
	return _ASCII_DASHBOARD


class RewardsFarmerApp(App):
	"""Launcher screens: configuration, live metrics, progress, and logs."""

	TITLE = "Rewards Farmer"
	CSS = """
	Screen {
		layout: vertical;
		overflow: hidden;
		background: #0d1117;
		color: #e6edf3;
	}

	/* Top command bar */
	#top-bar {
		height: 1;
		width: 100%;
		padding: 0 1;
		background: #161b22;
		color: #8b949e;
	}

	#setup {
		color: #8b949e;
		padding: 0 1;
		width: 1fr;
	}

	#schedule {
		color: #58a6ff;
		padding: 0 1;
		width: auto;
		text-style: bold;
		text-align: right;
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

	/* Main Two-column layout */
	#main-view {
		layout: horizontal;
		height: 1fr;
		width: 100%;
		padding: 0 1;
		background: #0d1117;
	}

	#sidebar-pane {
		width: 38;
		height: 1fr;
		background: #161b22;
		border: round #30363d;
		border-title-align: left;
		border-title-style: bold;
		border-title-color: #58a6ff;
		padding: 0 1;
		margin-right: 1;
	}

	#sidebar-pane:focus-within {
		border: round #58a6ff;
	}

	#content-pane {
		width: 1fr;
		height: 1fr;
		padding: 0;
	}

	/* Sidebar Sections - Seamless integration inside #sidebar-pane */
	#panel-config {
		height: auto;
		border: none;
		background: transparent;
		padding: 0;
		margin: 0;
	}

	#panel-dashboard {
		height: auto;
		border: none;
		border-top: solid #21262d;
		background: transparent;
		padding: 0;
		margin-top: 1;
	}

	/* Execution Pipeline & Tabs */
	#panel-progress {
		border: round #30363d;
		border-title-align: left;
		border-title-style: bold;
		border-title-color: #bc8cff;
		background: #161b22;
		height: auto;
		max-height: 10;
		margin-bottom: 1;
		padding: 0 1;
	}

	#panel-progress:focus-within {
		border: round #bc8cff;
	}

	/* Profile selection */
	#profile-select {
		height: auto;
		margin: 0 0 1 0;
		padding: 0;
		border: none;
		background: #21262d;
		color: #f0f6fc;
	}

	.task-header {
		color: #8b949e;
		text-style: bold;
		margin-top: 1;
		margin-bottom: 0;
		padding: 0;
	}

	/* Task toggle grid */
	#task-toggles-grid {
		layout: grid;
		grid-size: 2;
		grid-columns: 1fr 1fr;
		height: auto;
		margin: 0 0 1 0;
		padding: 0;
	}

	#task-toggles-grid Checkbox {
		height: 1;
		margin: 0;
		padding: 0 1;
		background: transparent;
		border: none;
		color: #8b949e;
	}

	#task-toggles-grid Checkbox:hover {
		color: #f0f6fc;
		background: #21262d;
	}

	#task-toggles-grid Checkbox.-on {
		color: #3fb950;
		text-style: bold;
	}

	/* Telemetry & metrics styling */
	#stat-points, #active-step-label, #timer-search-delay, #timer-schedule-window {
		height: 1;
		padding: 0;
	}

	.points-positive {
		color: #3fb950;
		text-style: bold;
	}

	.points-zero {
		color: #8b949e;
	}

	.step-active {
		color: #58a6ff;
		text-style: bold;
	}

	.step-idle {
		color: #8b949e;
	}

	.timer-active {
		color: #d29922;
		text-style: bold;
	}

	.timer-idle {
		color: #8b949e;
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
		grid-size: 4;
		grid-columns: 1fr 1fr 1fr 1fr;
		grid-gutter: 0 1;
		height: auto;
		margin: 0 0 1 0;
		padding: 0;
	}

	#actions Button {
		height: 1;
		margin: 0;
		padding: 0 1;
		min-width: 4;
		background: #21262d;
		color: #c9d1d9;
		border: none;
		text-align: center;
	}

	#actions Button:hover {
		background: #30363d;
		color: #58a6ff;
	}

	#actions #run {
		column-span: 2;
		background: #238636;
		color: #ffffff;
		text-style: bold;
	}

	#actions #run:hover {
		background: #2ea043;
	}

	#actions #stop {
		column-span: 2;
		background: #21262d;
		color: #f85149;
		text-style: bold;
	}

	#actions #stop:hover {
		background: #da3633;
		color: #ffffff;
	}

	#actions #open-profile {
		column-span: 2;
	}

	#actions #btn-quit {
		column-span: 2;
		background: #161b22;
		color: #8b949e;
	}

	#actions #btn-quit:hover {
		background: #21262d;
		color: #f85149;
	}

	#actions Button:disabled {
		opacity: 25%;
	}

	/* Progress rows and step checklist */
	#progress-summary {
		height: 1;
		padding: 0;
		color: #8b949e;
	}

	#progress {
		height: auto;
		padding: 0;
	}

	.step {
		height: 1;
		padding: 0 1;
		color: #8b949e;
	}

	.step-running {
		color: #58a6ff;
		text-style: bold;
	}

	.step-ok {
		color: #3fb950;
	}

	.step-skip {
		color: #6e7681;
	}

	.step-fail {
		color: #f85149;
		text-style: bold;
	}

	/* Tabbed content */
	#panel-tabs {
		height: 1fr;
		border: round #30363d;
		border-title-align: left;
		border-title-style: bold;
		border-title-color: #58a6ff;
		background: #161b22;
		margin: 0;
		padding: 0;
	}

	#panel-tabs:focus-within {
		border: round #58a6ff;
	}

	#tab-log, #tab-history {
		height: 1fr;
		padding: 0;
	}

	TabbedContent Tabs {
		height: 1;
		margin-bottom: 0;
		background: #161b22;
	}

	TabbedContent Tab {
		height: 1;
		padding: 0 2;
		color: #8b949e;
		background: transparent;
		border: none;
	}

	TabbedContent Tab:hover {
		color: #f0f6fc;
		background: #21262d;
	}

	TabbedContent Tab.-active {
		color: #58a6ff;
		text-style: bold;
		background: #21262d;
		border: none;
	}

	/* Modern subtle scrollbar */
	ScrollBar {
		background: transparent;
		color: #30363d;
		width: 1;
	}

	ScrollBar:hover {
		color: #58a6ff;
	}

	ScrollBarCorner {
		background: transparent;
	}

	#log-banner {
		display: none;
		height: 1;
		padding: 0 1;
		background: #382400;
		color: #e3b341;
		text-style: bold;
	}

	#log-banner.active {
		display: block;
	}

	#log-panel {
		height: 1fr;
		margin: 0;
		border: none;
		scrollbar-size-vertical: 1;
	}

	#log {
		height: 1fr;
		background: #0d1117;
		color: #e6edf3;
		padding: 0 1;
	}

	#history-count {
		height: 1;
		padding: 0 1;
		color: #8b949e;
	}

	#history {
		height: 1fr;
		margin: 0;
		background: #0d1117;
		scrollbar-size-vertical: 1;
	}

	#history ListItem {
		height: 1;
		padding: 0 1;
		color: #c9d1d9;
	}

	#history ListItem:hover {
		background: #161b22;
		color: #58a6ff;
	}

	#history ListItem.-selected, #history:focus > ListItem.--highlight {
		background: #21262d;
		color: #58a6ff;
		text-style: bold;
	}

	/* Bottom status bar */
	#status {
		dock: bottom;
		height: 1;
		padding: 0 1;
		background: #161b22;
		color: #c9d1d9;
	}

	#status.tone-success {
		color: #3fb950;
		text-style: bold;
	}

	#status.tone-warning {
		color: #d29922;
		text-style: bold;
	}

	#status.tone-danger {
		color: #f85149;
		text-style: bold;
	}

	#status.tone-running {
		color: #58a6ff;
		text-style: bold;
	}

	#status.tone-idle {
		color: #8b949e;
	}

	/* Responsive compact rules for short screens (<= 28 rows) */
	Screen.compact-height #sidebar-pane {
		width: 40;
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

	/* Responsive compact rules for narrow screens (< 95 cols) */
	Screen.compact-width #sidebar-pane {
		width: 38;
	}
	"""

	BINDINGS = [
		Binding("r", "run", "Run"),
		Binding("ctrl+enter", "run", "Run", show=False),
		Binding("escape", "stop", "Stop"),
		Binding("l", "toggle_log", "Log"),
		Binding("d", "arm_daily", "Daily"),
		Binding("s", "open_settings", "Config"),
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

	@staticmethod
	def _clean_profile_label(raw: str) -> str:
		if " — " not in raw:
			return raw
		dir_name, details = raw.split(" — ", 1)
		dir_name = dir_name.strip()
		parts = [p.strip() for p in details.split(" · ") if p.strip()]
		if not parts:
			return dir_name
		name_part = parts[0]
		for p in parts:
			if "@" not in p and p.lower() != dir_name.lower():
				name_part = p
				break
		cleaned = f"{dir_name} ({name_part})"
		if len(cleaned) > 34:
			cleaned = cleaned[:33] + "…"
		return cleaned

	def _build_profile_options(self) -> tuple[list[tuple[str, str]], str]:
		profiles = self.controller.get_available_profiles()
		if not profiles:
			profiles = [("Default", "Default profile")]
		profile_options = [(self._clean_profile_label(label), name) for name, label in profiles]
		if len(profiles) > 1:
			profile_options = [("All Profiles", "all")] + profile_options
		if self.controller.selected_profile:
			initial_profile = self.controller.selected_profile
		elif any(name == "Default" for name, _ in profiles):
			initial_profile = "Default"
		else:
			initial_profile = profile_options[0][1]
		return profile_options, initial_profile

	def compose(self) -> ComposeResult:
		yield Header()
		with Horizontal(id="top-bar"):
			yield Static("", id="setup")
			yield Static("", id="schedule")

		profile_options, initial_profile = self._build_profile_options()

		btn_run = "▶ Run" if _is_unicode_supported() else "Run"
		btn_stop = "⏹ Stop" if _is_unicode_supported() else "Stop"
		btn_daily = "⏰ Daily" if _is_unicode_supported() else "Daily"
		btn_config = "⚙ Config" if _is_unicode_supported() else "Config"
		btn_logs = "📁 Logs" if _is_unicode_supported() else "Logs"
		btn_profile = "👤 Profile" if _is_unicode_supported() else "Profile"
		btn_clear = "🧹 Clear" if _is_unicode_supported() else "Clear"
		btn_quit = "✕ Quit" if _is_unicode_supported() else "Quit"

		with Horizontal(id="main-view"):
			sidebar = VerticalScroll(id="sidebar-pane")
			sidebar.border_title = " Control Center "
			with sidebar:
				with Container(id="panel-config"):
					yield Select[str](
						profile_options,
						value=initial_profile,
						id="profile-select",
						compact=True,
						allow_blank=False,
					)
					with Grid(id="actions"):
						yield Button(btn_run, id="run", variant="success")
						yield Button(btn_stop, id="stop", variant="error", disabled=True)
						yield Button(btn_daily, id="daily")
						yield Button(btn_config, id="config")
						yield Button(btn_logs, id="open-logs")
						yield Button(btn_clear, id="clear-log")
						yield Button(btn_profile, id="open-profile")
						yield Button(btn_quit, id="btn-quit")

					yield Static("Automated Tasks", classes="task-header")
					with Grid(id="task-toggles-grid"):
						yield Checkbox("Daily Set", value=True, id="task-daily-set", compact=True)
						yield Checkbox("Explore", value=True, id="task-explore", compact=True)
						yield Checkbox("Visual", value=True, id="task-visual", compact=True)
						yield Checkbox("Misc Cards", value=True, id="task-misc", compact=True)
						yield Checkbox("Quests", value=True, id="task-quests", compact=True)
						yield Checkbox("Searches", value=True, id="task-searches", compact=True)
						yield Checkbox("Bonus", value=True, id="task-bonus", compact=True)

				with Container(id="panel-dashboard"):
					yield Static("Session Telemetry", classes="task-header")
					yield Static("Points: +0  ·  Session: +0", id="stat-points")
					yield Static("▶ Ready", id="active-step-label")
					yield ProgressBar(id="active-step-bar", show_eta=False, show_percentage=True)
					yield Static("⏳ Delay: idle", id="timer-search-delay")
					yield Static("⏰ Daily: idle", id="timer-schedule-window")

			with Vertical(id="content-pane"):
				prog = Container(id="panel-progress")
				prog.border_title = " Step Progress "
				with prog:
					yield Static("Run progress", id="progress-summary")
					yield Vertical(id="progress")

				tabs = TabbedContent(id="panel-tabs")
				tabs.border_title = " Activity Console "
				with tabs:
					with TabPane("Console Log", id="tab-log"):
						yield Static("", id="log-banner")
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
			options, initial_profile = self._build_profile_options()
			select.set_options(options)
			select.value = initial_profile
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
			run_icon = "▶ " if _is_unicode_supported() else ""
			if snapshot.running:
				run.label = f"{run_icon}Running…"
			elif snapshot.run_button_text == "Run again":
				run.label = f"{run_icon}Run again"
			else:
				run.label = f"{run_icon}Run"
			self.query_one("#stop", Button).disabled = not snapshot.stop_enabled

			# Dynamic Daily button label
			is_armed = daily_schedule.load_plan() is not None
			sched_icon = "⏰ " if _is_unicode_supported() else ""
			self.query_one("#daily", Button).label = f"{sched_icon}Undaily" if is_armed else f"{sched_icon}Daily"

			# Live Dashboard widgets
			self._paint_dashboard(snapshot)

			# Controls locked/enabled state
			self._paint_controls_state(snapshot)

			self._paint_progress(snapshot.progress_rows)
			self._paint_history(snapshot.run_history)
		except NoMatches:
			return

	def _paint_dashboard(self, snapshot: controller.LauncherSnapshot) -> None:
		glyphs = _dash_glyphs()
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
				step_label.update(f"{glyphs['step']} {step_name}{detail}")
				step_label.set_classes("step-active")
			elif snapshot.status_text and snapshot.status_text != "Ready to run":
				step_label.update(f"{glyphs['step']} {snapshot.status_text}")
				step_label.set_classes("step-active")
			else:
				step_label.update(f"{glyphs['step']} Ready")
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
				delay_widget.update(f"{glyphs['delay']} Delay: {snapshot.search_delay_remaining:.1f}s")
				delay_widget.set_classes("timer-active")
			else:
				delay_widget.update(f"{glyphs['delay']} Delay: idle")
				delay_widget.set_classes("timer-idle")
		except NoMatches:
			pass

		try:
			sched_widget = self.query_one("#timer-schedule-window", Static)
			if snapshot.daily_schedule_countdown:
				sched_widget.update(f"{glyphs['daily']} Daily: {snapshot.daily_schedule_countdown}")
				sched_widget.set_classes("timer-active")
			elif daily_schedule.claimed_today():
				sched_widget.update(f"{glyphs['daily']} Daily: completed today")
				sched_widget.set_classes("timer-idle")
			else:
				sched_widget.update(f"{glyphs['daily']} Daily: idle")
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
		try:
			banner = self.query_one("#log-banner", Static)
			banner.update(f"◀ Viewing Run #{run_number} (historical) — press 'l' or click here to return to live log")
			banner.add_class("active")
		except NoMatches:
			pass
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
				try:
					banner = self.query_one("#log-banner", Static)
					banner.remove_class("active")
					banner.update("")
				except NoMatches:
					pass
				log = self.query_one("#log", RichLog)
				log.clear()
				for line in self.controller.get_log_text().splitlines()[-200:]:
					log.write(line)
				self._flush_logs()
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
		if self._viewing_run is not None:
			self._viewing_run = None
			try:
				banner = self.query_one("#log-banner", Static)
				banner.remove_class("active")
				banner.update("")
			except NoMatches:
				pass
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
		try:
			sched_icon = "⏰ " if _is_unicode_supported() else ""
			self.query_one("#daily", Button).label = f"{sched_icon}Undaily"
		except NoMatches:
			pass
		self.notify("Daily trigger armed.", timeout=4)

	def action_remove_daily(self) -> None:
		try:
			message = daily_schedule.remove_daily_trigger()
		except RuntimeError as exc:
			self.notify(str(exc), severity="error", timeout=8)
			return
		self._schedule_line = daily_schedule.status_line(None)
		self.query_one("#schedule", Static).update(self._schedule_line)
		try:
			sched_icon = "⏰ " if _is_unicode_supported() else ""
			self.query_one("#daily", Button).label = f"{sched_icon}Daily"
		except NoMatches:
			pass
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

	def on_click(self, event) -> None:
		if getattr(event.widget, "id", None) == "log-banner" and self._viewing_run is not None:
			self.action_toggle_log()

	def on_button_pressed(self, event: Button.Pressed) -> None:
		button_id = event.button.id
		if button_id == "run":
			self.action_run()
		elif button_id == "stop":
			self.action_stop()
		elif button_id == "open-logs":
			self.controller.open_logs_folder()
			self.notify("Logs folder opened in Explorer", timeout=3)
		elif button_id == "open-profile":
			self.controller.open_profile_folder()
			self.notify("Profile folder opened in Explorer", timeout=3)
		elif button_id == "clear-log":
			error = self.controller.clear_log()
			if error:
				self.notify(error, severity="warning")
				return
			self._viewing_run = None
			self._history_key = ""
			try:
				banner = self.query_one("#log-banner", Static)
				banner.remove_class("active")
				banner.update("")
			except NoMatches:
				pass
			self.query_one("#log", RichLog).clear()
			self.notify("Log history cleared", timeout=3)
			self._paint()
		elif button_id == "daily":
			if daily_schedule.load_plan() is not None:
				self.action_remove_daily()
			else:
				self.action_arm_daily()
		elif button_id == "config":
			self.action_open_settings()
		elif button_id == "btn-quit":
			self.action_quit_app()

	def action_open_settings(self) -> None:
		self.push_screen(SettingsModal(), self._on_settings_closed)

	def _on_settings_closed(self, saved: bool | None) -> None:
		if saved:
			self.notify("Settings saved to .env", timeout=3)

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
