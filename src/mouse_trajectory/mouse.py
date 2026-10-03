"""Selenium pointer control: tracking, movement, scroll, click."""

from __future__ import annotations

import math
import random
import time
from typing import Callable

from selenium import webdriver
from selenium.common.exceptions import JavascriptException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.remote.webelement import WebElement

from mouse_trajectory.constants import Point
from mouse_trajectory.path import choose_target_in_element, get_final_path_from_real_time
from mouse_trajectory.timing import get_movement_time_from_fitts_law


class MouseUtils:
	def __init__(self, driver: webdriver.Edge):
		self.driver = driver
		self.fallback_init_pos = (0, 0)  # default fallback position if mouse position is not initialized
		self.reinitialize()

	def reinitialize(self):
		self.init_driver_with_mouse_tracking()
		self.init_driver_with_cursor_visualization()

	def init_driver_with_mouse_tracking(self):
		initial_pos = self.fallback_init_pos

		js_tracker = f"""
	window.cursorX = {int(initial_pos[0])};
	window.cursorY = {int(initial_pos[1])};
	document.addEventListener('mousemove', function(event) {{
		console.log('Mouse moved to: ' + event.clientX + ', ' + event.clientY);
		window.cursorX = event.clientX;
		window.cursorY = event.clientY;
	}});
	"""
		self.driver.execute_script(js_tracker)

	def init_driver_with_cursor_visualization(self):
		cursor_script = """
	var visualCursor = document.createElement('div');
	visualCursor.id = 'selenium-visual-cursor';
	visualCursor.style.position = 'fixed';
	visualCursor.style.zIndex = '99999';
	visualCursor.style.width = '15px';
	visualCursor.style.height = '15px';
	visualCursor.style.background = 'red';
	visualCursor.style.borderRadius = '50%';
	visualCursor.style.border = '2px solid white';
	visualCursor.style.pointerEvents = 'none'; // Prevents blocking element clicks
	visualCursor.style.top = '0px';
	visualCursor.style.left = '0px';
	visualCursor.style.transition = 'all 0.3s ease;'; // Optional: adds smooth sliding visual
	document.body.appendChild(visualCursor);

	window.moveVisualCursor = function(x, y) {
		var cursor = document.getElementById('selenium-visual-cursor');
		cursor.style.left = x + 'px';
		cursor.style.top = y + 'px';
	};
	"""
		self.driver.execute_script(cursor_script)

	def get_current_mouse_position(self) -> Point:
		pos: dict[str, int] = self.driver.execute_script("return { x: window.cursorX, y: window.cursorY };")

		x, y = pos['x'], pos['y']

		if (x, y) == (None, None):
			self.reinitialize()
			return self.get_current_mouse_position()

		self.fallback_init_pos = (x, y)

		return (x, y)

	def move_mouse(self, move_time: float, path_function: Callable[[float], Point], visualize: bool = True):
		start_time = time.monotonic()
		end_time = start_time + move_time

		# The distorted bezier path can overshoot the window edge, which the
		# driver rejects, so keep every sampled point inside the viewport.
		viewport = self.driver.execute_script(
			"return [window.innerWidth, window.innerHeight];"
		)
		max_x, max_y = int(viewport[0]) - 2, int(viewport[1]) - 2

		while True:
			current_time = time.monotonic()

			# Clamped, because the loop is driven by wall clock: without this the
			# last sample is taken an iteration short of move_time and the pointer
			# never lands on the target.
			t = min(current_time - start_time, move_time)
			point = path_function(t)

			point = (
				min(max(0, point[0]), max_x),
				min(max(0, point[1]), max_y)
			)

			actions = ActionBuilder(self.driver, duration=0)
			actions.pointer_action.move_to_location(point[0], point[1])
			actions.perform()

			self.fallback_init_pos = point

			if visualize:
				try:
					self.driver.execute_script(f"window.moveVisualCursor({point[0]}, {point[1]});")
				except JavascriptException:  # some uninitialization has happened, reinitialize the cursor visualization
					self.reinitialize()
					self.driver.execute_script(f"window.moveVisualCursor({point[0]}, {point[1]});")

			if current_time >= end_time:
				break

	def wheel_scroll_element_into_view(self, element: WebElement, max_wheel_events: int = 60):
		"""Scroll the element into the viewport with simulated wheel input.

		Wheel steps of varying size with short pauses, the way a person scrolls,
		instead of a fixed-size burst. The loop is bounded on purpose: an element
		that never fits the viewport completely, for example one taller than the
		window, must not hang the run forever. When the budget runs out the
		caller proceeds with the element as visible as it got.
		"""
		for _ in range(max_wheel_events):
			top, bottom, height = self.driver.execute_script(
				"var r = arguments[0].getBoundingClientRect();"
				"return [r.top, r.bottom, window.innerHeight];",
				element
			)

			if top >= 0 and bottom <= height:
				break

			# Aim the element at the middle of the viewport, one notch at a time.
			distance = (top + bottom) / 2 - height / 2
			step = max(-320, min(320, distance))
			step = int(step * random.uniform(0.6, 1.0))

			if abs(step) < 40:
				step = 40 if distance > 0 else -40

			ActionChains(self.driver).scroll_by_amount(0, step).perform()

			time.sleep(random.uniform(0.04, 0.12))

	def wheel_scroll_to_top(self, max_wheel_events: int = 80):
		"""Scroll back to the top of the page with simulated wheel input.

		Reads the actual scroll position instead of unwinding a counted number
		of steps, because the page height can change while cards update and a
		symmetric unwind then lands in the wrong place.
		"""
		for _ in range(max_wheel_events):
			offset = self.driver.execute_script("return window.scrollY || window.pageYOffset;")

			if offset <= 0:
				break

			step = min(340, int(offset))
			step = max(60, int(step * random.uniform(0.6, 1.0)))

			ActionChains(self.driver).scroll_by_amount(0, -step).perform()

			time.sleep(random.uniform(0.04, 0.12))

	def move_to_element(self, element: WebElement, visualize: bool = True):
		# The pointer is moved to viewport coordinates, so an element below the
		# fold yields a target outside the window and the driver rejects the move
		# with MoveTargetOutOfBoundsException. Bring it into view first, but only
		# when it actually is out of view: unconditionally re-centering visible
		# elements is what caused the page to jump between tasks. When scrolling
		# is needed it is smooth, and since smooth scrolling is asynchronous, the
		# rect is polled until it stops moving before the path is computed.
		fully_in_view = self.driver.execute_script("""
			var r = arguments[0].getBoundingClientRect();
			return (
				r.top >= 0 && r.left >= 0 &&
				r.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
				r.right <= (window.innerWidth || document.documentElement.clientWidth)
			);
		""", element)

		if not fully_in_view:
			self.driver.execute_script(
				"arguments[0].scrollIntoView({block: 'center', inline: 'center', behavior: 'smooth'});",
				element
			)

			last_rect = None

			for _ in range(20):
				time.sleep(0.15)

				rect = self.driver.execute_script(
					"var r = arguments[0].getBoundingClientRect();"
					"return [Math.round(r.top), Math.round(r.left)];",
					element
				)

				if rect == last_rect:
					break

				last_rect = rect

		current_mouse_position = self.get_current_mouse_position()

		rect = self.driver.execute_script("""
			var rect = arguments[0].getBoundingClientRect();
			return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
		""", element)

		target_position = choose_target_in_element(
			rect['x'],
			rect['y'],
			rect['height'],
			rect['width']
		)

		move_time = get_movement_time_from_fitts_law(
			math.dist(current_mouse_position, target_position),
			(rect['width'] + rect['height']) / 2
		)

		path_fn = get_final_path_from_real_time(
			movement_time=move_time,
			start=current_mouse_position,
			end=target_position
		)

		self.move_mouse(move_time, path_fn, visualize)

	def human_like_click(self, time_interval: tuple[int, int] = (200, 300)):
		ActionChains(self.driver, duration=random.randint(time_interval[0], time_interval[1])).click().perform()
