"""Cubic Bezier paths with optional mid-path distortion."""

from __future__ import annotations

import random
from functools import partial
from typing import Callable

from mouse_trajectory.constants import (
	DEFAULT_DEVIATION_INTERVAL,
	DEFAULT_DISTORTION_FREQUENCY,
	DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	Point,
)


def cubic_bezier_single_coordinate(p0: int, p1: int, p2: int, p3: int, t: float):
	first_coeff = (1 - t) ** 3
	second_coeff = 3 * t * (1 - t) ** 2
	third_coeff = 3 * (1 - t) * (t ** 2)
	fourth_coeff = t ** 3

	return (
		first_coeff * p0
		+ second_coeff * p1
		+ third_coeff * p2
		+ fourth_coeff * p3
	)


def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
	return (
		(cubic_bezier_single_coordinate(p0[0], p1[0], p2[0], p3[0], t)),
		(cubic_bezier_single_coordinate(p0[1], p1[1], p2[1], p3[1], t)),
	)


def random_anysign(a: int, b: int) -> int:
	result = random.randint(a, b)

	if random.randint(0, 1):
		return -result

	return result


def get_bezier_path(
	start: Point,
	end: Point,
	intermediate_radius_interval: tuple[int, int] = DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
) -> Callable[[float], Point]:
	p0, p3 = start, end

	p1 = (
		p0[0] + random_anysign(intermediate_radius_interval[0], intermediate_radius_interval[1]),
		p0[1] + random_anysign(intermediate_radius_interval[0], intermediate_radius_interval[1]),
	)

	p2 = (
		p3[0] + random_anysign(intermediate_radius_interval[0], intermediate_radius_interval[1]),
		p3[1] + random_anysign(intermediate_radius_interval[0], intermediate_radius_interval[1]),
	)

	return partial(cubic_bezier, p0, p1, p2, p3)


def get_distorted_bezier_path(
	start: Point,
	end: Point,
	intermediate_radius_interval: tuple[int, int] = DEFAULT_INTERMEDIATE_RADIUS_INTERVAL,
	distortion_zone_time_length: float = DEFAULT_DISTORTION_ZONE_TIME_LENGTH,
	distortion_frequency: float = DEFAULT_DISTORTION_FREQUENCY,
	deviation_interval: tuple[int, int] = DEFAULT_DEVIATION_INTERVAL,
) -> Callable[[float], Point]:
	distortion_zones: list[tuple[float, float]] = [
		(i * distortion_zone_time_length, (i + 1) * distortion_zone_time_length)
		for i in range(int(1 / distortion_zone_time_length))
		if random.uniform(0, 1) < distortion_frequency
	]

	distortion_offsets: list[Point] = [
		(
			random_anysign(deviation_interval[0], deviation_interval[1]),
			random_anysign(deviation_interval[0], deviation_interval[1]),
		)
		for _ in range(len(distortion_zones))
	]

	def get_distorted_point(
		true_point: Point,
		distortion_offset: Point,
		distortion_zone: tuple[float, float],
		t: float,
	) -> Point:
		distortion_zone_length = distortion_zone[1] - distortion_zone[0]
		distortion_zone_progress = (t - distortion_zone[0]) / distortion_zone_length

		if distortion_zone_progress < 0.5:  # move from true to distorted point
			return (
				true_point[0] + distortion_offset[0] * distortion_zone_progress * 2,
				true_point[1] + distortion_offset[1] * distortion_zone_progress * 2,
			)
		else:  # move from distorted to true point
			return (
				true_point[0] + distortion_offset[0] * (1 - (distortion_zone_progress - 0.5) * 2),
				true_point[1] + distortion_offset[1] * (1 - (distortion_zone_progress - 0.5) * 2),
			)

	bezier_path = get_bezier_path(start, end, intermediate_radius_interval)

	def distored_path_function(t: float):
		true_point = bezier_path(t)

		for i, distortion_zone in enumerate(distortion_zones):
			if distortion_zone[0] <= t <= distortion_zone[1]:
				return get_distorted_point(
					true_point,
					distortion_offsets[i],
					distortion_zone,
					t,
				)

		# we are not in a distortion zone, return the true point
		return true_point

	return distored_path_function
