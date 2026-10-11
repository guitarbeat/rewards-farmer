"""Tests for where a simulated move actually leaves the pointer (#74).

The move is driven by two things that both stop short of the target. The path
normalises elapsed time onto the sigmoid's input range with a 4.5 multiplier,
and logistic_sigmoid(4.5) is 0.978, so the bezier is never evaluated at its
endpoint. On top of that move_mouse sampled on the wall clock with a strict
`< end_time`, so it never asked for a sample at movement_time either. The
pointer was left a few pixels short of the point move_to_element picked, on
every move, which costs clicks on the smallest controls and reports nothing
when it does.

None of them need a browser.

	python -m unittest discover -s tests
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import mouse_trajectory
from mouse_trajectory import (
	MouseUtils,
	choose_target_in_element,
	get_final_path_from_real_time,
	get_movement_time_from_fitts_law,
	logistic_sigmoid,
)

# Long enough to take several samples, short enough that the suite stays quick.
BRIEF_MOVE = 0.05


class RecordingActionBuilder:
	"""Stands in for ActionBuilder and keeps every location it is asked for."""

	def __init__(self, driver, duration=0):
		self.locations = driver.locations
		self.pointer_action = self

	def move_to_location(self, x, y):
		self._pending = (x, y)
		return self

	def perform(self):
		self.locations.append(self._pending)


class FakeMouseDriver:
	"""Answers the one script move_mouse runs and records nothing else."""

	def __init__(self):
		self.locations = []

	def execute_script(self, script, *args):
		if "innerWidth" in script:
			return [1920, 1080]

		return None


def make_mouse_utils(driver):
	"""A MouseUtils without the cursor visualization its __init__ injects."""
	mouse = MouseUtils.__new__(MouseUtils)
	mouse.driver = driver
	mouse.fallback_init_pos = (0, 0)

	return mouse


class PathEndsOnTheTarget(unittest.TestCase):
	def test_a_sample_at_movement_time_is_the_target(self):
		random.seed(7)
		start, end = (100, 100), (400, 300)
		path = get_final_path_from_real_time(1.0, start, end)

		self.assertEqual(path(1.0), end)

	def test_a_sample_before_the_end_still_follows_the_path(self):
		"""The endpoint must come from reaching the end, not from short-circuiting."""
		random.seed(7)
		start, end = (100, 100), (400, 300)
		path = get_final_path_from_real_time(1.0, start, end)

		midpoint = path(0.5)

		self.assertNotEqual(midpoint, end)
		self.assertNotEqual(midpoint, start)

	def test_the_sigmoid_alone_does_not_reach_the_end(self):
		"""Why the branch above exists. If 4.5 ever changes, this says what it cost."""
		self.assertLess(logistic_sigmoid(4.5), 1.0)
		self.assertAlmostEqual(logistic_sigmoid(4.5), 0.978026, places=6)


class MoveMouseLandsOnTheTarget(unittest.TestCase):
	def setUp(self):
		self._real_builder = mouse_trajectory.mouse.ActionBuilder
		mouse_trajectory.mouse.ActionBuilder = RecordingActionBuilder

	def tearDown(self):
		mouse_trajectory.mouse.ActionBuilder = self._real_builder

	def test_the_last_move_is_to_the_target(self):
		random.seed(11)
		driver = FakeMouseDriver()
		mouse = make_mouse_utils(driver)

		start, end = (200, 200), (600, 450)
		path = get_final_path_from_real_time(BRIEF_MOVE, start, end)

		mouse.move_mouse(BRIEF_MOVE, path, visualize=False)

		self.assertEqual(driver.locations[-1], end)

	def test_the_move_is_sampled_along_the_way_not_jumped(self):
		random.seed(11)
		driver = FakeMouseDriver()
		mouse = make_mouse_utils(driver)

		start, end = (200, 200), (600, 450)
		path = get_final_path_from_real_time(BRIEF_MOVE, start, end)

		mouse.move_mouse(BRIEF_MOVE, path, visualize=False)

		self.assertGreater(len(driver.locations), 1)
		self.assertNotEqual(driver.locations[0], end)

	def test_a_move_with_no_time_left_still_lands_on_the_target(self):
		"""A zero-length move must not leave the pointer wherever it started."""
		random.seed(11)
		driver = FakeMouseDriver()
		mouse = make_mouse_utils(driver)

		start, end = (200, 200), (600, 450)
		path = get_final_path_from_real_time(0.0, start, end)

		mouse.move_mouse(0.0, path, visualize=False)

		self.assertTrue(driver.locations, "the pointer was never moved at all")
		self.assertEqual(driver.locations[-1], end)


class FakeMoveDriver(FakeMouseDriver):
	"""Also answers the scripts move_to_element runs before it moves."""

	def __init__(self, cursor, rect):
		super().__init__()
		self.cursor = cursor
		self.rect = rect

	def execute_script(self, script, *args):
		if "cursorX" in script:
			return {"x": self.cursor[0], "y": self.cursor[1]}

		if "r.top >= 0" in script:
			# Already in view, so nothing scrolls.
			return True

		if "rect.width" in script:
			return dict(self.rect)

		return super().execute_script(script, *args)


class MoveWhenAlreadyOnTheTarget(unittest.TestCase):
	"""A second click on the same control can pick the point the pointer is on.

	The search loop clicks the same clear button after every query, and since
	the move ends on the chosen point a repeat pick means a distance of 0.
	log2(0) raised ValueError and took the search task down with it.
	"""

	def setUp(self):
		self._real_builder = mouse_trajectory.mouse.ActionBuilder
		mouse_trajectory.mouse.ActionBuilder = RecordingActionBuilder

	def tearDown(self):
		mouse_trajectory.mouse.ActionBuilder = self._real_builder

	def test_no_distance_takes_no_time(self):
		self.assertEqual(get_movement_time_from_fitts_law(0, 20), 0.0)

	def test_a_distance_still_follows_fitts_law(self):
		self.assertGreater(get_movement_time_from_fitts_law(300, 20), 0.0)

	def test_clicking_where_the_pointer_already_is_lands_there(self):
		rect = {"x": 300, "y": 200, "width": 24, "height": 24}

		# The point this click is going to pick, so the pointer can be left
		# there first, the way the previous click on the same button leaves it.
		random.seed(5)
		target = choose_target_in_element(rect["x"], rect["y"], rect["height"], rect["width"])
		random.seed(5)

		driver = FakeMoveDriver(cursor=target, rect=rect)
		mouse = make_mouse_utils(driver)

		mouse.move_to_element(element=None, visualize=False)

		self.assertEqual(driver.locations[-1], target)


class BusyPageDriver(FakeMouseDriver):
	"""A page that does not run the cursor overlay script in time.

	overlay_timeouts is how many times adding the overlay runs into the script
	timeout before the page keeps up. Moving the overlay fails the way it does
	in a browser while the overlay is not there.
	"""

	def __init__(self, overlay_timeouts):
		super().__init__()
		self.overlay_timeouts = overlay_timeouts
		self.overlay_added = False

	def execute_script(self, script, *args):
		if "selenium-visual-cursor" in script and "createElement" in script:
			if self.overlay_timeouts > 0:
				self.overlay_timeouts -= 1
				raise mouse_trajectory.TimeoutException("script timeout")

			self.overlay_added = True

			return None

		if "moveVisualCursor" in script and not self.overlay_added:
			raise mouse_trajectory.JavascriptException("window.moveVisualCursor is not a function")

		return super().execute_script(script, *args)


class CursorOverlayOnABusyPage(unittest.TestCase):
	"""The overlay is cosmetic, so a page too busy to add it must not end the run.

	It was added in MouseUtils.__init__, which RewardsTaskUtils builds before
	the first task, so its script timeout took every task of the run with it.
	"""

	def setUp(self):
		self._real_builder = mouse_trajectory.mouse.ActionBuilder
		mouse_trajectory.mouse.ActionBuilder = RecordingActionBuilder

	def tearDown(self):
		mouse_trajectory.mouse.ActionBuilder = self._real_builder

	def test_a_busy_page_does_not_stop_the_setup(self):
		driver = BusyPageDriver(overlay_timeouts=1)

		with self.assertLogs(mouse_trajectory.logger, level="WARNING") as captured:
			MouseUtils(driver)

		self.assertIn("cursor overlay not added", "\n".join(captured.output))
		self.assertFalse(driver.overlay_added)

	def test_the_first_move_adds_the_overlay_once_the_page_keeps_up(self):
		driver = BusyPageDriver(overlay_timeouts=1)

		with self.assertLogs(mouse_trajectory.logger, level="WARNING"):
			mouse = MouseUtils(driver)

		start, end = (200, 200), (600, 450)
		mouse.move_mouse(BRIEF_MOVE, get_final_path_from_real_time(BRIEF_MOVE, start, end), visualize=True)

		self.assertTrue(driver.overlay_added)
		self.assertEqual(driver.locations[-1], end)


if __name__ == "__main__":
	unittest.main()
