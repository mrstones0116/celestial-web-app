import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import TourPlan

JD_UNIX_EPOCH = 2440587.5
JD_J2000 = 2451545.0
SECONDS_PER_DAY = 86400.0


def _to_utc(dt: datetime) -> datetime:
    """naive datetime 一律按 UTC 处理，避免依赖服务器本地时区。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _gmst(dt: datetime) -> float:
    """简化格林尼治恒星时（小时）。"""
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
):
    """
    简化版赤道坐标转地平坐标。
    返回 (altitude_deg, azimuth_deg)。
    """
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
    """
    为 plan 里每个 TourTarget 填充 altitude_deg / azimuth_deg。
    直接原地修改 plan，不返回值。
    """
    location = config.get("location") or {}
    observing_time = config.get("observing_time") or {}

    lat = location.get("latitude", 39.9042)
    lon = location.get("longitude", 116.4074)
    tz_name = location.get("timezone", "Asia/Shanghai")

    dt = _parse_observing_dt(observing_time, tz_name)

    for step in plan.steps:
        for target in step.targets:
            if target.ra_deg is None or target.dec_deg is None:
                continue
            alt, az = ra_dec_to_altaz(
                target.ra_deg, target.dec_deg, lat, lon, dt,
            )
            target.altitude_deg = round(alt, 2)
            target.azimuth_deg = round(az, 2)