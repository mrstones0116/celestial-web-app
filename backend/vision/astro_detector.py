"""
天文级星点检测 —— photutils DAOStarFinder
兼容 photutils 1.x / 2.x
"""
import numpy as np
from typing import List, Dict
from PIL import Image


def detect_stars_astro(
    image_path: str,
    fwhm: float = 4.0,
    threshold_sigma: float = 5.0,
    max_stars: int = 150,
    min_sharpness: float = 0.2,
    max_sharpness: float = 1.0,
    roundness_limit: float = 0.6,
) -> List[Dict]:
    from astropy.stats import sigma_clipped_stats
    from photutils.detection import DAOStarFinder
    import inspect

    img = Image.open(image_path).convert('L')
    data = np.array(img, dtype=np.float64)

    mean, median, std = sigma_clipped_stats(data, sigma=3.0, maxiters=5)

    # ---- 兼容新旧参数名 ----
    dao_kwargs = dict(fwhm=fwhm, threshold=threshold_sigma * std)
    _params = inspect.signature(DAOStarFinder.__init__).parameters

    if 'sharpness_range' in _params:
        dao_kwargs['sharpness_range'] = (min_sharpness, max_sharpness)
        dao_kwargs['roundness_range'] = (-roundness_limit, roundness_limit)
    else:
        dao_kwargs['sharplo'] = min_sharpness
        dao_kwargs['sharphi'] = max_sharpness
        dao_kwargs['roundlo'] = -roundness_limit
        dao_kwargs['roundhi'] = roundness_limit

    daofind = DAOStarFinder(**dao_kwargs)
    sources = daofind(data - median)

    if sources is None or len(sources) == 0:
        return []

    # ---- 兼容列名 ----
    colnames = list(sources.colnames)

    def _col(candidates):
        for c in candidates:
            if c in colnames:
                return c
        return None

    x_col    = _col(['xcentroid', 'x_centroid', 'xcenter', 'x'])
    y_col    = _col(['ycentroid', 'y_centroid', 'ycenter', 'y'])
    flux_col = _col(['flux', 'peak'])
    sharp_col = _col(['sharpness', 'sharp'])
    round_col = _col(['roundness1', 'roundness'])

    if x_col is None or y_col is None:
        raise ValueError(f"无法定位坐标列，可用列: {colnames}")
    if flux_col is None:
        flux_col = x_col

    fluxes_all = np.array(sources[flux_col], dtype=np.float64)
    order = np.argsort(fluxes_all)[::-1]
    sources = sources[order]

    fluxes = np.maximum(np.array(sources[flux_col], dtype=np.float64), 1e-6)
    mag_est = -2.5 * np.log10(fluxes)

    stars = []
    for i, row in enumerate(sources[:max_stars]):
        star = {
            "x": float(row[x_col]),
            "y": float(row[y_col]),
            "flux": float(row[flux_col]),
            "mag_est": float(mag_est[i]),
        }
        if sharp_col:
            star["sharpness"] = float(row[sharp_col])
        if round_col:
            star["roundness"] = float(row[round_col])
        stars.append(star)

    return stars