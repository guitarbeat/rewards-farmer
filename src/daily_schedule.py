"""Smart daily trigger for an unattended rewards run.

The clock time is learned from successful local runs and kept inside the
daytime. The operating system fires once a day and catches up after sleep.
The run itself waits until a stable instant inside that window, skips when
today is already finished, and refuses to start while the terminal UI is open
so progress stays on screen.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import accounts
import daily_completion
import launcher_runtime as runtime

TASK_NAME = "RewardsFarmerDaily"
LAUNCHD_LABEL = "com.rewardsfarmer.daily"
SYSTEMD_STEM = "rewards-farmer"
WINDOW_MINUTES = 75
DAY_START_HOUR = 8
DAY_END_HOUR = 20
DEFAULT_START_MINUTE = 9 * 60 + 15
GRACE = timedelta(hours=3)
PLAN_FILE = os.path.join(runtime.LOG_DIR, "daily_trigger.json")
CLAIM_FILE = os.path.join(runtime.LOG_DIR, "daily_trigger_claim.txt")


@dataclass(frozen=True)
class DailyPlan:
	start_minute: int
	window_minutes: int
	learned_from: int
	clamped: bool


@dataclass(frozen=True)
class InstallResult:
	status_line: str
	plan: DailyPlan


def format_clock(minute_of_day: int) -> str:
	minute = minute_of_day % (24 * 60)
	return f"{minute // 60:02d}:{minute % 60:02d}"


def plan_from_history(log_text: str) -> DailyPlan:
	"""Pick a daytime window from successful run start hours."""
	hours = _successful_hours(log_text)
	if not hours:
		return DailyPlan(DEFAULT_START_MINUTE, WINDOW_MINUTES, 0, False)

	median = int(round(statistics.median(hours)))
	clamped = median < DAY_START_HOUR or median > DAY_END_HOUR
	hour = min(DAY_END_HOUR, max(DAY_START_HOUR, median))
	# Fifteen minutes past the hour avoids a pile-up on :00.
	return DailyPlan(hour * 60 + 15, WINDOW_MINUTES, len(hours), clamped)


def status_line(plan: DailyPlan | None) -> str:
	if plan is None:
		return "Daily off. Press d to arm a daytime run."

	start = format_clock(plan.start_minute)
	end = format_clock(plan.start_minute + plan.window_minutes)
	if plan.learned_from == 1:
		source = "from 1 run"
	elif plan.learned_from:
		source = f"from {plan.learned_from} runs"
	else:
		source = "morning window"
	daytime = ", daytime only" if plan.clamped else ""
	return f"Daily {start}-{end} {source}{daytime}. Skips finished accounts."


def load_plan(path: str | None = None) -> DailyPlan | None:
	plan_path = path or PLAN_FILE
	try:
		with open(plan_path, encoding="utf-8") as handle:
			payload = json.load(handle)
	except (OSError, json.JSONDecodeError, TypeError):
		return None

	try:
		return DailyPlan(
			start_minute=int(payload["start_minute"]),
			window_minutes=int(payload["window_minutes"]),
			learned_from=int(payload.get("learned_from", 0)),
			clamped=bool(payload.get("clamped", False)),
		)
	except (KeyError, TypeError, ValueError):
		return None


def save_plan(plan: DailyPlan, path: str | None = None) -> None:
	plan_path = path or PLAN_FILE
	os.makedirs(os.path.dirname(plan_path), exist_ok=True)
	payload = {
		"start_minute": plan.start_minute,
		"window_minutes": plan.window_minutes,
		"learned_from": plan.learned_from,
		"clamped": plan.clamped,
	}
	with open(plan_path, "w", encoding="utf-8", newline="\n") as handle:
		json.dump(payload, handle, indent=2)
		handle.write("\n")


def wait_seconds(now: datetime, plan: DailyPlan, rng: random.Random) -> int:
	"""Seconds until today's instant inside the window.

	A fire before the window returns a wait longer than the window so the
	caller can exit and let the calendar trigger try again. After the window,
	the wait is zero so a missed boot still runs.
	"""
	window_start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=plan.start_minute)
	offset = rng.randrange(0, plan.window_minutes * 60)
	target = window_start + timedelta(seconds=offset)
	if now >= target:
		return 0
	return int((target - now).total_seconds())


def autostart_due(now: datetime, plan: DailyPlan | None, *, claimed: bool, unfinished: bool) -> bool:
	"""Whether the open terminal UI should start the daily run itself."""
	if plan is None or claimed or not unfinished:
		return False

	window_start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=plan.start_minute)
	window_end = window_start + timedelta(minutes=plan.window_minutes)
	target = window_start + timedelta(seconds=_day_offset(now, plan))
	if now < target:
		return False
	return now <= window_end + GRACE


def claim_today(path: str | None = None, today: str | None = None) -> bool:
	"""Return True when this process won the single daily attempt."""
	claim_path = path or CLAIM_FILE
	stamp = today or datetime.now().date().isoformat()
	os.makedirs(os.path.dirname(claim_path), exist_ok=True)

	try:
		with open(claim_path, encoding="utf-8") as handle:
			if handle.read().strip() == stamp:
				return False
	except OSError:
		pass

	temporary = claim_path + ".tmp"
	with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
		handle.write(stamp + "\n")

	try:
		os.replace(temporary, claim_path)
	except OSError:
		return False

	try:
		with open(claim_path, encoding="utf-8") as handle:
			return handle.read().strip() == stamp
	except OSError:
		return False


def release_claim(path: str | None = None, today: str | None = None) -> None:
	claim_path = path or CLAIM_FILE
	stamp = today or datetime.now().date().isoformat()
	try:
		with open(claim_path, encoding="utf-8") as handle:
			current = handle.read().strip()
	except OSError:
		return
	if current != stamp:
		return
	try:
		os.remove(claim_path)
	except OSError:
		pass


def claimed_today(path: str | None = None, today: str | None = None) -> bool:
	claim_path = path or CLAIM_FILE
	stamp = today or datetime.now().date().isoformat()
	try:
		with open(claim_path, encoding="utf-8") as handle:
			return handle.read().strip() == stamp
	except OSError:
		return False


def unfinished_accounts() -> bool:
	"""True when persistence still has something to do, or the account list is empty."""
	found = accounts.configured()
	if not found:
		return True
	return bool(daily_completion.remaining(found, enabled=True))


def read_history_text() -> str:
	log_path = os.path.join(runtime.LOG_DIR, "launcher_runs.log")
	try:
		with open(log_path, encoding="utf-8") as handle:
			return handle.read()
	except OSError:
		return ""


def install_daily_trigger(
	*,
	platform: str | None = None,
	home: str | None = None,
	log_text: str | None = None,
	runner=subprocess.run,
) -> InstallResult:
	"""Install or refresh the OS daily trigger and remember the learned window."""
	system = platform or sys.platform
	plan = plan_from_history(log_text if log_text is not None else read_history_text())
	_install_os(plan, system=system, home=home or os.path.expanduser("~"), runner=runner)
	save_plan(plan)
	return InstallResult(status_line(plan), plan)


def remove_daily_trigger(
	*,
	platform: str | None = None,
	home: str | None = None,
	runner=subprocess.run,
) -> str:
	system = platform or sys.platform
	_remove_os(system=system, home=home or os.path.expanduser("~"), runner=runner)
	try:
		os.remove(PLAN_FILE)
	except OSError:
		pass
	return "Daily trigger removed."


def run_scheduled(
	*,
	now: datetime | None = None,
	sleep=None,
	spawn=None,
	plan: DailyPlan | None = None,
) -> int:
	"""Entry point for the OS trigger. Returns a process exit code."""
	if runtime.launcher_ui_is_open():
		return 0

	current = now or datetime.now()
	active = plan if plan is not None else load_plan()
	if active is None:
		active = plan_from_history(read_history_text())

	if not unfinished_accounts():
		return 0
	stamp = current.date().isoformat()
	if claimed_today(today=stamp):
		return 0

	wait = wait_seconds(current, active, _rng_for_day(current))
	if wait > active.window_minutes * 60:
		return 0
	if wait > 0:
		(sleep or time.sleep)(wait)

	if not claim_today(today=stamp):
		return 0

	launch = spawn or _spawn_bot
	code = launch()
	if code != 0:
		release_claim(today=stamp)
	return code


def bot_command() -> list[str]:
	return [runtime.resolve_python_executable(), "-u", runtime.MAIN_SCRIPT]


def bot_env() -> dict[str, str]:
	env = os.environ.copy()
	env["REWARDS_AUTO"] = "true"
	env["REWARDS_PERSISTENCE"] = "true"
	env["REWARDS_PROFILE_PICKER"] = "false"
	env["REWARDS_LAUNCHED_FROM_GUI"] = "1"
	env["OPENBLAS_NUM_THREADS"] = "1"
	env["OMP_NUM_THREADS"] = "1"
	return env


def windows_task_xml(plan: DailyPlan, *, python: str, script: str, workdir: str, day: datetime) -> str:
	stamp = day.replace(
		hour=plan.start_minute // 60,
		minute=plan.start_minute % 60,
		second=0,
		microsecond=0,
	).strftime("%Y-%m-%dT%H:%M:%S")
	command = _xml(python)
	arguments = _xml(f'"{script}" --run')
	folder = _xml(workdir)
	return textwrap.dedent(
		f"""\
		<?xml version="1.0" encoding="UTF-16"?>
		<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
		  <Triggers>
		    <CalendarTrigger>
		      <StartBoundary>{stamp}</StartBoundary>
		      <Enabled>true</Enabled>
		      <ScheduleByDay>
		        <DaysInterval>1</DaysInterval>
		      </ScheduleByDay>
		    </CalendarTrigger>
		  </Triggers>
		  <Principals>
		    <Principal>
		      <LogonType>InteractiveToken</LogonType>
		      <RunLevel>LeastPrivilege</RunLevel>
		    </Principal>
		  </Principals>
		  <Settings>
		    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
		    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
		    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
		    <StartWhenAvailable>true</StartWhenAvailable>
		    <Enabled>true</Enabled>
		    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
		  </Settings>
		  <Actions>
		    <Exec>
		      <Command>{command}</Command>
		      <Arguments>{arguments}</Arguments>
		      <WorkingDirectory>{folder}</WorkingDirectory>
		    </Exec>
		  </Actions>
		</Task>
		"""
	)


def systemd_units(plan: DailyPlan, *, python: str, script: str, workdir: str) -> tuple[str, str]:
	clock = format_clock(plan.start_minute)
	service = textwrap.dedent(
		f"""\
		[Unit]
		Description=Rewards Farmer daily run

		[Service]
		Type=oneshot
		WorkingDirectory={workdir}
		ExecStart="{python}" "{script}" --run
		Environment=OPENBLAS_NUM_THREADS=1
		Environment=OMP_NUM_THREADS=1
		"""
	)
	timer = textwrap.dedent(
		f"""\
		[Unit]
		Description=Rewards Farmer daily trigger

		[Timer]
		OnCalendar=*-*-* {clock}:00
		Persistent=true
		Unit={SYSTEMD_STEM}.service

		[Install]
		WantedBy=timers.target
		"""
	)
	return service, timer


def launchd_plist(plan: DailyPlan, *, python: str, script: str, workdir: str) -> str:
	hour = plan.start_minute // 60
	minute = plan.start_minute % 60
	return textwrap.dedent(
		f"""\
		<?xml version="1.0" encoding="UTF-8"?>
		<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
		<plist version="1.0">
		<dict>
		  <key>Label</key>
		  <string>{LAUNCHD_LABEL}</string>
		  <key>ProgramArguments</key>
		  <array>
		    <string>{_xml(python)}</string>
		    <string>{_xml(script)}</string>
		    <string>--run</string>
		  </array>
		  <key>WorkingDirectory</key>
		  <string>{_xml(workdir)}</string>
		  <key>StartCalendarInterval</key>
		  <dict>
		    <key>Hour</key>
		    <integer>{hour}</integer>
		    <key>Minute</key>
		    <integer>{minute}</integer>
		  </dict>
		  <key>RunAtLoad</key>
		  <true/>
		</dict>
		</plist>
		"""
	)


def _successful_hours(log_text: str) -> list[int]:
	hours: list[int] = []
	for entry in runtime.parse_run_history(log_text, limit=60):
		if entry.exit_code != 0 or entry.tone == "danger":
			continue
		parsed = _hour_from_started(entry.started)
		if parsed is not None:
			hours.append(parsed)
	return hours


def _hour_from_started(started: str) -> int | None:
	for piece in started.split():
		if len(piece) >= 2 and piece[0:2].isdigit() and ":" in piece:
			try:
				return int(piece.split(":", 1)[0])
			except ValueError:
				return None
	return None


def _day_offset(now: datetime, plan: DailyPlan) -> int:
	return _rng_for_day(now).randrange(0, plan.window_minutes * 60)


def _rng_for_day(now: datetime) -> random.Random:
	return random.Random(now.date().isoformat())


def _xml(text: str) -> str:
	return (
		text.replace("&", "&amp;")
		.replace("<", "&lt;")
		.replace(">", "&gt;")
		.replace('"', "&quot;")
	)


def _script_path() -> str:
	return os.path.abspath(__file__)


def _install_os(plan: DailyPlan, *, system: str, home: str, runner) -> None:
	python = runtime.resolve_python_executable()
	script = _script_path()
	workdir = runtime.REPO_ROOT

	if system == "win32":
		xml_path = os.path.join(runtime.LOG_DIR, "RewardsFarmerDaily.xml")
		os.makedirs(runtime.LOG_DIR, exist_ok=True)
		xml = windows_task_xml(plan, python=python, script=script, workdir=workdir, day=datetime.now())
		with open(xml_path, "w", encoding="utf-16", newline="\r\n") as handle:
			handle.write(xml)
		result = runner(
			["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
			capture_output=True,
			text=True,
			check=False,
		)
		if getattr(result, "returncode", 1) != 0:
			detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "schtasks failed").strip()
			raise RuntimeError(detail)
		return

	if system == "darwin":
		folder = os.path.join(home, "Library", "LaunchAgents")
		os.makedirs(folder, exist_ok=True)
		path = os.path.join(folder, f"{LAUNCHD_LABEL}.plist")
		with open(path, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(launchd_plist(plan, python=python, script=script, workdir=workdir))
		runner(["launchctl", "unload", path], capture_output=True, text=True, check=False)
		result = runner(["launchctl", "load", path], capture_output=True, text=True, check=False)
		if getattr(result, "returncode", 1) != 0:
			detail = (getattr(result, "stderr", "") or "launchctl load failed").strip()
			raise RuntimeError(detail)
		return

	folder = os.path.join(home, ".config", "systemd", "user")
	os.makedirs(folder, exist_ok=True)
	service, timer = systemd_units(plan, python=python, script=script, workdir=workdir)
	service_path = os.path.join(folder, f"{SYSTEMD_STEM}.service")
	timer_path = os.path.join(folder, f"{SYSTEMD_STEM}.timer")
	with open(service_path, "w", encoding="utf-8", newline="\n") as handle:
		handle.write(service)
	with open(timer_path, "w", encoding="utf-8", newline="\n") as handle:
		handle.write(timer)
	runner(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True, check=False)
	result = runner(
		["systemctl", "--user", "enable", "--now", f"{SYSTEMD_STEM}.timer"],
		capture_output=True,
		text=True,
		check=False,
	)
	if getattr(result, "returncode", 1) != 0:
		detail = (getattr(result, "stderr", "") or "systemctl enable failed").strip()
		raise RuntimeError(detail)


def _remove_os(*, system: str, home: str, runner) -> None:
	if system == "win32":
		runner(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True, check=False)
		return

	if system == "darwin":
		path = os.path.join(home, "Library", "LaunchAgents", f"{LAUNCHD_LABEL}.plist")
		runner(["launchctl", "unload", path], capture_output=True, text=True, check=False)
		try:
			os.remove(path)
		except OSError:
			pass
		return

	folder = os.path.join(home, ".config", "systemd", "user")
	runner(
		["systemctl", "--user", "disable", "--now", f"{SYSTEMD_STEM}.timer"],
		capture_output=True,
		text=True,
		check=False,
	)
	for name in (f"{SYSTEMD_STEM}.service", f"{SYSTEMD_STEM}.timer"):
		try:
			os.remove(os.path.join(folder, name))
		except OSError:
			pass
	runner(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True, check=False)


def _spawn_bot() -> int:
	log_path = os.path.join(runtime.LOG_DIR, "launcher_runs.log")
	os.makedirs(runtime.LOG_DIR, exist_ok=True)
	stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	clock = datetime.now().strftime("%H:%M:%S")
	try:
		previous = open(log_path, encoding="utf-8").read()
	except OSError:
		previous = ""
	number = previous.count("=== Run #") + 1

	with open(log_path, "a", encoding="utf-8") as handle:
		handle.write(f"\n=== Run #{number} started {stamp} ===\n")
		handle.flush()
		process = subprocess.Popen(
			bot_command(),
			cwd=runtime.REPO_ROOT,
			env=bot_env(),
			stdout=handle,
			stderr=subprocess.STDOUT,
			text=True,
		)
		code = process.wait()
		handle.write(f"=== Run finished {clock} (exit {code}) ===\n")
	return code


def main(argv: list[str] | None = None) -> int:
	args = list(sys.argv[1:] if argv is None else argv)
	try:
		if "--remove" in args:
			print(remove_daily_trigger())
			return 0
		if "--install" in args:
			print(install_daily_trigger().status_line)
			return 0
		if "--run" in args:
			return run_scheduled()
	except RuntimeError as exc:
		print(exc, file=sys.stderr)
		return 1

	print("Use --install, --remove, or --run.", file=sys.stderr)
	return 2


if __name__ == "__main__":
	raise SystemExit(main())
