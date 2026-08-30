"""
Generic geometric utilities for finding a grid of circular bubbles and
clustering them into rows / column-blocks. Used once by the template
calibrator (full-page scan) and reused by tests. The per-submission OMR
runtime does NOT call this -- it uses the template's stored ROIs directly
(spec section 19: "do not scan the entire image for circles" at grading time).
"""
from __future__ import annotations

import cv2
import numpy as np


def detect_circles(
    gray: np.ndarray,
    min_radius: int,
    max_radius: int,
    min_dist: int,
    param1: int = 80,
    param2: int = 18,
) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=min_dist,
        param1=param1, param2=param2, minRadius=min_radius, maxRadius=max_radius,
    )
    if circles is None:
        return np.empty((0, 3), dtype=np.float32)
    return circles[0]


def cluster_1d(values: list[float], tol: float) -> list[list[int]]:
    """Cluster indices of `values` whose consecutive sorted values are within `tol`."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    clusters: list[list[int]] = []
    for idx in order:
        if clusters and abs(values[idx] - values[clusters[-1][-1]]) <= tol:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])
    return clusters


def cluster_rows(circles: np.ndarray, y_tol: float) -> list[np.ndarray]:
    """Group circles into rows by y-coordinate. Returns rows sorted top-to-bottom,
    each row's circles sorted left-to-right."""
    if len(circles) == 0:
        return []
    ys = circles[:, 1].tolist()
    idx_clusters = cluster_1d(ys, y_tol)
    rows = []
    for idxs in idx_clusters:
        row = circles[idxs]
        row = row[np.argsort(row[:, 0])]
        rows.append(row)
    rows.sort(key=lambda r: r[:, 1].mean())
    return rows


def split_row_into_blocks(row: np.ndarray, gap_factor: float = 2.5) -> list[np.ndarray]:
    """Split a left-to-right sorted row of circles into column-blocks wherever
    the horizontal gap is much larger than the typical (median) gap."""
    if len(row) < 2:
        return [row]
    xs = row[:, 0]
    diffs = np.diff(xs)
    median_gap = float(np.median(diffs)) if len(diffs) else 0.0
    if median_gap <= 0:
        return [row]
    split_points = np.where(diffs > gap_factor * median_gap)[0]
    blocks = []
    start = 0
    for sp in split_points:
        blocks.append(row[start:sp + 1])
        start = sp + 1
    blocks.append(row[start:])
    return blocks
