import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Tuple

if TYPE_CHECKING:
    from .schemas import TourPlan

JD_UNIX_EPOCH = 2440587.5
JD_J2000 = 2451545.0
SECONDS_PER_DAY = 86400.0


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _gmst(dt: datetime) -> float:
    dt = _to_utc(dt)
    jd = dt.timestamp() / SECONDS_PER_DAY + JD_UNIX_EPOCH
    t = (jd - JD_J2000) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - JD_J2000)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    )
    return (gmst % 360) / 15.0


def ra_dec_to_altaz(
    ra_deg: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
    dt: datetime,
) -> Tuple[float, float]:
    gmst_hours = _gmst(dt)
    lst_hours = (gmst_hours + lon_deg / 15.0) % 24.0
    ha_hours = (lst_hours - ra_deg / 15.0) % 24.0
    ha_deg = ha_hours * 15.0

    lat = math.radians(lat_deg)
    dec = math.radians(dec_deg)
    ha = math.radians(ha_deg)

    sin_alt = (
        math.sin(lat) * math.sin(dec)
        + math.cos(lat) * math.cos(dec) * math.cos(ha)
    )
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))

    cos_alt = math.cos(alt)
    if abs(cos_alt) < 1e-6:
        az = 0.0
    else:
        sin_az = -math.cos(dec) * math.sin(ha) / cos_alt
        cos_az = (math.sin(dec) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
        az = math.degrees(math.atan2(sin_az, cos_az))
        az = (az + 360) % 360

    return math.degrees(alt), az

def _parse_observing_dt(observing_time: dict, tz_name: str) -> datetime:
    """从 observing_time 配置解析出一个带时区的 datetime。"""
    tz = ZoneInfo(tz_name)

    # ✅ 实时模式：直接使用当前时间
    if observing_time.get("use_real_time"):
        return datetime.now(tz)

    date_str = observing_time.get("date")
    time_str = observing_time.get("start_local_time") or "22:00"

    if date_str:
        try:
            date_part = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            date_part = datetime.now(tz).date()
    else:
        date_part = datetime.now(tz).date()

    try:
        hh, mm = time_str.split(":")
        dt = datetime(
            date_part.year, date_part.month, date_part.day,
            int(hh), int(mm), tzinfo=tz,
        )
    except Exception:
        dt = datetime.now(tz)
    return dt


def annotate_plan(plan: "TourPlan", config: dict) -> None:
    """为 plan 里每个 TourTarget 填充 altitude_deg / azimuth_deg / is_visible。"""
    location = config.get("location") or {}
    observing_time = config.get("observing_time") or {}

    lat = location.get("latitude", 22.3193)
    lon = location.get("longitude", 114.1694)
    tz_name = location.get("timezone", "Asia/Hong_Kong")
    dt = _parse_observing_dt(observing_time, tz_name)

    # ✅ 可见性阈值：城市环境下，高度角<15°的星星基本被遮挡
    min_altitude = 10.0

    for step in plan.steps:
        for target in step.targets:
            if target.ra_deg is None or target.dec_deg is None:
                target.is_visible = False
                continue
            alt, az = ra_dec_to_altaz(target.ra_deg, target.dec_deg, lat, lon, dt)
            target.altitude_deg = round(alt, 2)
            target.azimuth_deg = round(az, 2)
            target.is_visible = alt >= min_altitude

            # ✅ 生成可见性提示
            if not target.is_visible:
                if alt < 0:
                    target.visibility_note = "当前位于地平线以下，不可见"
                else:
                    target.visibility_note = f"高度角仅{alt:.0f}°，建议寻找开阔地平线"

# ==================== ✅ 新增：RA 单位安全转换 ====================

def _ra_to_deg(ra_value) -> Optional[float]:
    """
    HYG 星表的 ra 字段单位是小时 (0~24)。
    安全转换：若值 <= 24 认为是小时，乘以 15 转为度；否则直接当度用。
    """
    try:
        ra = float(ra_value)
    except (TypeError, ValueError):
        return None
    if ra <= 24.0:
        return ra * 15.0
    return ra


def _dec_to_deg(dec_value) -> Optional[float]:
    """dec 字段已经是度，直接转 float。"""
    try:
        return float(dec_value)
    except (TypeError, ValueError):
        return None


# ==================== ✅ 修正：实时可见天体计算 ====================

def compute_visible_objects(
    stars: List[Dict[str, Any]],
    config: dict,
    min_altitude: float = 15.0,
    max_magnitude: Optional[float] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    根据当前时间地点，从星表数据中筛选可见天体。
    返回按亮度+高度角综合评分排序的天体列表。

    ✅ 已适配 HYG 字段：ra(小时), dec(度), mag, con, proper
    """
    location = config.get("location") or {}
    observing_time = config.get("observing_time") or {}
    equipment = config.get("equipment") or {}

    lat = location.get("latitude", 22.3193)
    lon = location.get("longitude", 114.1694)
    tz_name = location.get("timezone", "Asia/Hong_Kong")
    dt = _parse_observing_dt(observing_time, tz_name)

    # 设备极限星等
    limiting_mag = equipment.get("limiting_magnitude", 5.5)
    if max_magnitude is not None:
        limiting_mag = min(limiting_mag, max_magnitude)

    # 光污染降级
    sky_quality = equipment.get("sky_quality", "city")
    if sky_quality == "city":
        limiting_mag = min(limiting_mag, 3.5)
    elif sky_quality == "suburb":
        limiting_mag = min(limiting_mag, 5.0)
        
    results = []
    for star in stars:
        try:
            mag = float(star.get("mag", 99))
        except (ValueError, TypeError):
            continue

        if mag > limiting_mag:
            continue

        # ✅ 修正：get_stars() 返回 "ra_hours"，不是 "ra"
        raw_ra = star.get("ra_hours") or star.get("ra")
        ra = _ra_to_deg(raw_ra)
        dec = _dec_to_deg(star.get("dec"))

        if ra is None or dec is None:
            continue

        alt, az = ra_dec_to_altaz(ra, dec, lat, lon, dt)

        if alt < min_altitude:
            continue

        brightness_score = max(0.0, (6.0 - mag) / 5.0 * 10.0)
        altitude_score = max(0.0, alt / 90.0 * 10.0)
        total_score = brightness_score * 0.7 + altitude_score * 0.3

        results.append({
            **star,
            "ra_deg": round(ra, 6),
            "dec_deg": round(dec, 6),
            "altitude_deg": round(alt, 2),
            "azimuth_deg": round(az, 2),
            "visibility_score": round(total_score, 2),
        })

    results.sort(key=lambda x: x["visibility_score"], reverse=True)
    return results[:limit]

def sort_observation_path(objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按方位角排序，减少用户来回转头的幅度。
    简单策略：以正北为起点，按方位角顺时针排序；若跨度大，则找最短路径。
    """
    if len(objects) <= 1:
        return objects

    # 按方位角排序
    sorted_by_az = sorted(objects, key=lambda x: x.get("azimuth_deg", 0))

    # 计算相邻方位角间隔，找最大间隔处作为"切割点"，使路径最短
    if len(sorted_by_az) > 2:
        max_gap = 0
        cut_index = 0
        for i in range(len(sorted_by_az) - 1):
            gap = sorted_by_az[i + 1]["azimuth_deg"] - sorted_by_az[i]["azimuth_deg"]
            if gap > max_gap:
                max_gap = gap
                cut_index = i + 1
        # 从最大间隔后开始，形成最短环形路径
        sorted_by_az = sorted_by_az[cut_index:] + sorted_by_az[:cut_index]

    return sorted_by_az