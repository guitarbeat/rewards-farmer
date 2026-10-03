"""Compose timed paths from Bezier + Fitts timing."""

from __future__ import annotations

import math
import random
from typing import Callable

from mouse_trajectory.constants import (
	DEFAULT_DEVIATION_INTERVAL,
	DEFAULT_DISTORTION_FREQUENCY,
	DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	Point,
)
from mouse_trajectory.timing import get_movement_time_from_fitts_law, get_path_with_transformed_velo


def get_final_path_from_real_time(
	movement_time: float,
	start: Point,
	end: Point,
	intermediate_radius_interval: tuple[int, int] = DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	distortion_zone_time_length: float = DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	distortion_frequency: float = DEFAULT_DISTORTION_FREQUENCY,
	deviation_interval: tuple[int, int] = DEFAULT_DEVIATION_INTERVAL,
) -> Callable[[float], Point]:
	path = get_path_with_transformed_velo(
		start,
		end,
		intermediate_radius_interval,
		distortion_zone_time_length,
		distortion_frequency,
		deviation_interval,
	)

	def final_path_function(t: float) -> Point:
		if t < 0:
			return start
		elif t >= movement_time:
			# Not just t > movement_time: the sigmoid below is asymptotic, so a
			# sample taken exactly at movement_time still lands short of the
			# target and the move has to end here instead.
			return end

		normalized_t = (t / movement_time) * 4.5

		return path(normalized_t)

	return final_path_function


def get_final_path_with_fitts_law(
	target_width: float,
	start: Point,
	end: Point,
	intermediate_radius_interval: tuple[int, int] = DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	distortion_zone_time_length: float = DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	distortion_frequency: float = DEFAULT_DISTORTION_FREQUENCY,
	deviation_interval: tuple[int, int] = DEFAULT_DEVIATION_INTERVAL,
) -> Callable[[float], Point]:
	distance = math.dist(start, end)
	movement_time = get_movement_time_from_fitts_law(distance, target_width)

	return get_final_path_from_real_time(
		movement_time,
		start,
		end,
		intermediate_radius_interval,
		distortion_zone_time_length,
		distortion_frequency,
		deviation_interval,
	)


def choose_target_in_element(x: int, y: int, height: int, width: int) -> Point:
	# choose a random point near the center of the element

	left_bound_x = x + width * 0.25
	right_bound_x = x + width * 0.75
	top_bound_y = y + height * 0.25
	bottom_bound_y = y + height * 0.75

	return (
		random.randint(int(left_bound_x), int(right_bound_x)),
		random.randint(int(top_bound_y), int(bottom_bound_y)),
	)
