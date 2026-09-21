from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime


class GeoLocation(BaseModel):
    latitude: float = 39.9042
    longitude: float = 116.4074
    altitude: float = 0.0
    timezone: str = "Asia/Shanghai"


class ObservingTime(BaseModel):
    date: Optional[str] = None                # "YYYY-MM-DD"
    start_local_time: Optional[str] = None    # "HH:MM"
    duration_minutes: int = 60


class Equipment(BaseModel):
    type: Literal["naked_eye", "binoculars", "telescope", "camera"] = "naked_eye"
    aperture_mm: Optional[float] = None
    limiting_magnitude: float = 5.5


class TourPreferences(BaseModel):
    user_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    style: Literal["story", "science", "observation", "photography"] = "story"
    max_steps: int = 10
    include_deep_sky: bool = True
    include_planets: bool = False
    include_moon_notes: bool = False


class CreateTourSessionRequest(BaseModel):
    locale: str = "zh-CN"
    location: GeoLocation = Field(default_factory=GeoLocation)
    observing_time: ObservingTime = Field(default_factory=ObservingTime)
    equipment: Equipment = Field(default_factory=Equipment)
    preferences: TourPreferences = Field(default_factory=TourPreferences)


class InstructionRequest(BaseModel):
    text: str
    client_event_id: Optional[str] = None


class CameraTarget(BaseModel):
    center_ra_deg: float
    center_dec_deg: float
    fov_deg: float = 30.0
    roll_deg: float = 0.0
    highlight_ids: List[str] = Field(default_factory=list)
    constellation_lines: List[str] = Field(default_factory=list)


class TourTarget(BaseModel):
    type: Literal["star", "constellation", "messier", "ngc", "planet", "moon", "asterism"]
    id: str
    hyg_id: Optional[str] = None          # ← 新增：与 data_loader / vision 对齐
    name_zh: str
    name_en: str
    constellation: Optional[str] = None
    ra_deg: Optional[float] = None
    dec_deg: Optional[float] = None
    magnitude: Optional[float] = None
    altitude_deg: Optional[float] = None
    azimuth_deg: Optional[float] = None
    description: Optional[str] = None


class Narration(BaseModel):
    short: str
    long: str
    fun_fact: Optional[str] = None
    observation_tip: Optional[str] = None


class TourStep(BaseModel):
    step_index: int
    title: str
    subtitle: Optional[str] = None
    targets: List[TourTarget] = Field(default_factory=list)
    camera: CameraTarget
    narration: Narration
    estimated_minutes: int = 3
    next_hint: Optional[str] = None
    actions: List[str] = Field(default_factory=lambda: ["next", "prev", "pause", "stop"])


class TourPlan(BaseModel):
    plan_id: str
    title: str
    description: str
    total_minutes: int
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    steps: List[TourStep] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class TourSessionResponse(BaseModel):
    session_id: str
    status: str
    plan: Optional[TourPlan] = None
    current_step_index: int = 0
    message: str = ""