from constants import DOTENV_PATH
import logging
import os
import sys
import dotenv
import log_utils
import accounts
import browser
import daily_completion
import desktop_utils
import profile_picker
import queries
import site_registry

HEADLESS = browser.HEADLESS

logger = logging.getLogger(__name__)


def run_account(account: accounts.Account, create_runner: site_registry.SiteFactory | None = None) -> bool:
	"""Work one account. Returns whether the browser started."""
	if create_runner is None:
		_, _, create_runner = site_registry.resolve()

	try:
		if not desktop_utils.prepare_desktop_before_launch():
			return False
		driver = browser.start_driver(account)
	finally:
		desktop_utils.switch_back_after_launch()

	if driver is None:
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
				account.name,
				log_utils.exception_summary(exc),
			)

	return True


def _run_one(account: accounts.Account, create_runner) -> bool:
	if run_account(account, create_runner):
		if daily_completion.persistence_enabled():
			daily_completion.mark_completed(account.name)
		return True
	return False


def _run_selected_accounts(selected: list[accounts.Account], create_runner) -> int:
	started = 0
	total = len(selected)

	for account in selected:
		if total > 1:
			logger.info("=== account: %s ===", account.name)

		try:
			if _run_one(account, create_runner):
				started += 1
		except Exception as exc:
			logger.error(
				"[FAIL] %s: %s: %s",
				account.name,
				type(exc).__name__,
				log_utils.exception_summary(exc),
				exc_info=logger.isEnabledFor(logging.DEBUG),
			)

	return started


def main() -> int:
	log_utils.setup_logging()
	desktop_utils.reset_virtual_desktop_state()

	if desktop_utils.is_virtual_desktop_enabled() and not desktop_utils.is_windows():
		logger.warning("USE_VIRTUAL_DESKTOP is enabled, but virtual desktops are only supported on Windows.")

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

	remaining = daily_completion.remaining(configured)
	if daily_completion.persistence_enabled():
		skipped = len(configured) - len(remaining)
		if skipped:
			logger.info("Persistence: skipping %s account(s) already completed today.", skipped)

	if not remaining:
		logger.info("All configured accounts already completed today.")
		desktop_utils.cleanup_virtual_desktop()
		return 0

	started = 0

	if profile_picker.should_use_picker(len(remaining)):
		while True:
			remaining = daily_completion.remaining(configured)
			if not remaining:
				logger.info("All configured accounts already completed today.")
				break

			choice = profile_picker.choose_account(remaining)
			if choice is None:
				logger.info("Profile picker finished.")
				break

			logger.info("Selected profile: %s", choice.name)
			try:
				if _run_one(choice, create_runner):
					started += 1
			except Exception as exc:
				logger.error(
					"[FAIL] %s: %s: %s",
					choice.name,
					type(exc).__name__,
					log_utils.exception_summary(exc),
					exc_info=logger.isEnabledFor(logging.DEBUG),
				)
	else:
		selected = profile_picker.order_for_auto(remaining)
		started = _run_selected_accounts(selected, create_runner)

	if len(configured) > 1:
		logger.info("%s/%s accounts ran", started, len(configured))

	# Interactive pause only for manual CLI runs. The terminal launcher sets
	# REWARDS_LAUNCHED_FROM_GUI so a headless subprocess is not left waiting
	# forever on a Press Enter prompt nobody can see.
	if not HEADLESS and os.environ.get("REWARDS_LAUNCHED_FROM_GUI") != "1":
		try:
			if sys.stdin.isatty() and not profile_picker.auto_enabled():
				input("Press Enter to exit...")
		except EOFError:
			pass

	desktop_utils.cleanup_virtual_desktop()

	return 0 if started else 1


if __name__ == "__main__":
	if os.path.isfile(DOTENV_PATH): dotenv.load_dotenv(DOTENV_PATH)
	sys.exit(main())
