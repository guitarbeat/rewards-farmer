"""Velocity shaping and Fitts's law movement timing."""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from mouse_trajectory.bezier import get_distorted_bezier_path
from mouse_trajectory.constants import (
	DEFAULT_DEVIATION_INTERVAL,
	DEFAULT_DISTORTION_FREQUENCY,
	DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	FITTS_LAW_A,
	FITTS_LAW_B,
	Point,
)


def logistic_sigmoid(x: float) -> float:
	return 2 / (1 + np.exp(-x)) - 1


def get_path_with_transformed_velo(
	start: Point,
	end: Point,
	intermediate_radius_interval: tuple[int, int] = DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	distortion_zone_time_length: float = DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	distortion_frequency: float = DEFAULT_DISTORTION_FREQUENCY,
	deviation_interval: tuple[int, int] = DEFAULT_DEVIATION_INTERVAL,
) -> Callable[[float], Point]:
	bezier_path = get_distorted_bezier_path(
		start,
		end,
		intermediate_radius_interval,
		distortion_zone_time_length,
		distortion_frequency,
		deviation_interval,
	)

	return lambda t: bezier_path(logistic_sigmoid(t))


def get_movement_time_from_fitts_law(distance: float, target_width: float) -> float:
	index_of_difficulty = math.log2((2.0 * distance) / target_width)
	movement_time = FITTS_LAW_A + FITTS_LAW_B * index_of_difficulty

	return movement_time
