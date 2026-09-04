import logging
import os
import sys

import log_utils
import accounts
import queries
import site_registry
from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException

HEADLESS = os.environ.get("REWARDS_HEADLESS", "").strip().lower() in ("1", "true", "yes")

logger = logging.getLogger(__name__)


def build_options(account: accounts.Account) -> webdriver.EdgeOptions:
	options = webdriver.EdgeOptions()

	options.add_experimental_option("excludeSwitches", ["enable-automation"])
	options.add_experimental_option('useAutomationExtension', False)
	options.add_argument("--disable-blink-features=AutomationControlled")
	options.add_argument(f"--user-data-dir={account.user_data_dir}")
	options.add_argument(f"--profile-directory={account.profile_name}")

	if HEADLESS:
		# A container has no display. The window size is set explicitly because
		# the pointer code works in viewport coordinates, and the default
		# headless window is small enough to put cards out of reach.
		options.add_argument("--headless=new")
		options.add_argument("--window-size=1920,1080")
		options.add_argument("--no-sandbox")
		options.add_argument("--disable-dev-shm-usage")

	return options


def run_account(account: accounts.Account, create_runner: site_registry.SiteFactory) -> bool:
	"""Work one account. Returns whether the browser started."""
	try:
		driver = webdriver.Edge(options=build_options(account))
	except SessionNotCreatedException as exc:
		# Chromium allows one process per user data directory. When the profile
		# is already open the driver's copy exits during startup, and selenium
		# reports it as the browser crashing with a message that names neither
		# the profile nor the other window.
		logger.error("[FAIL] %s: could not start Edge with this profile.", account.name)
		logger.error("       profile directory: %s", account.user_data_dir)
		logger.error("       The usual cause is that this profile is already open in another")
		logger.error("       Edge window, including one left over from a previous run.")
		logger.error("       driver said: %s", log_utils.exception_summary(exc))

		return False

	logger.info("[STEP] Starting browser")

	try:
		runner = create_runner(driver)
		runner.complete_all_tasks()
	finally:
		try:
			driver.quit()
		except Exception as exc:
			# quit() raises when the browser is already gone. Letting it out
			# here would replace whatever actually went wrong with the tidy-up's
			# own error, and the process it is meant to end is dead anyway.
			logger.warning(
				"%s: the driver did not shut down cleanly: %s",
				account.name, log_utils.exception_summary(exc)
			)

	return True


def main() -> int:
	log_utils.setup_logging()

	try:
		site_key, site_label, create_runner = site_registry.resolve()
	except ValueError as exc:
		logger.error("[FAIL] %s", exc)

		return 2

	logger.info("Automation site: %s (%s)", site_label, site_key)

	queries.log_resolved_source()

	try:
		configured = accounts.configured()
	except ValueError as exc:
		logger.error("[FAIL] %s", exc)

		return 2

	started = 0

	for account in configured:
		if len(configured) > 1:
			logger.info("=== account: %s ===", account.name)

		# One account must not be able to end the batch. complete_all_tasks
		# already contains a task that fails, and run_account names the profile
		# that is already open, but everything else - a driver that will not
		# start for some other reason, the browser dying mid-run, a page that
		# never loads - reached here and took the remaining accounts with it.
		# KeyboardInterrupt is deliberately not caught: Ctrl-C means stop.
		try:
			if run_account(account, create_runner):
				started += 1
		except Exception as exc:
			logger.error(
				"[FAIL] %s: %s: %s",
				account.name, type(exc).__name__, log_utils.exception_summary(exc),
				exc_info=logger.isEnabledFor(logging.DEBUG)
			)

	if len(configured) > 1:
		logger.info("%s/%s accounts ran", started, len(configured))

	# Interactive pause only for manual CLI runs. The GUI launcher sets
	# REWARDS_LAUNCHED_FROM_GUI so a headless subprocess is not left waiting
	# forever on a Press Enter prompt nobody can see.
	if not HEADLESS and os.environ.get("REWARDS_LAUNCHED_FROM_GUI") != "1":
		try:
			if sys.stdin.isatty():
				input("Press Enter to exit...")
		except EOFError:
			pass

	return 0 if started else 1


if __name__ == "__main__":
	sys.exit(main())
