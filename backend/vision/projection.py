"""天球坐标投影：只保留 gnomonic 投影，供标准投影视图使用。"""
from typing import Tuple

import numpy as np


def _radec_to_xyz(ra_deg: np.ndarray, dec_deg: np.ndarray) -> np.ndarray:
    """(ra, dec) 转单位球面向量。ra/dec 单位：度。"""
    ra = np.radians(ra_deg)
    dec = np.radians(dec_deg)
    return np.stack([
        np.cos(dec) * np.cos(ra),
        np.cos(dec) * np.sin(ra),
        np.sin(dec),
    ], axis=-1)


def gnomonic_project(
    ra_deg: np.ndarray,
    dec_deg: np.ndarray,
    ra0_deg: float,
    dec0_deg: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    以 (ra0, dec0) 为中心的 gnomonic（切平面）投影。
    返回 (xi, eta, valid_mask)，xi / eta 是切平面坐标（无量纲）。
    半球背面的点 valid=False。
    """
    ra_deg = np.asarray(ra_deg, dtype=float)
    dec_deg = np.asarray(dec_deg, dtype=float)
    scalar = (ra_deg.ndim == 0)
    if scalar:
        ra_deg = ra_deg.reshape(1)
        dec_deg = dec_deg.reshape(1)

    v = _radec_to_xyz(ra_deg, dec_deg)
    v0 = _radec_to_xyz(
        np.array([ra0_deg]), np.array([dec0_deg])
    )[0]

    ra0 = np.radians(ra0_deg)
    dec0 = np.radians(dec0_deg)
    east = np.array([-np.sin(ra0), np.cos(ra0), 0.0])
    north = np.array([
        -np.sin(dec0) * np.cos(ra0),
        -np.sin(dec0) * np.sin(ra0),
        np.cos(dec0),
    ])

    denom = v @ v0
    valid = denom > 1e-6
    denom_safe = np.where(valid, denom, 1.0)
    xi = (v @ east) / denom_safe
    eta = (v @ north) / denom_safe

    if scalar:
        return xi, eta, valid
    return xi, eta, valid