from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime


class GeoLocation(BaseModel):
    # ✅ 默认地点改为香港
    latitude: float = 22.3193
    longitude: float = 114.1694
    altitude: float = 0.0
    timezone: str = "Asia/Hong_Kong"


class ObservingTime(BaseModel):
    date: Optional[str] = None                # "YYYY-MM-DD"
    start_local_time: Optional[str] = None    # "HH:MM"
    duration_minutes: int = 60
    # ✅ 新增：是否强制使用"当前真实时间"（用于"现在我能看到什么"）
    use_real_time: bool = False


class Equipment(BaseModel):
    type: Literal["naked_eye", "binoculars", "telescope", "camera"] = "naked_eye"
    aperture_mm: Optional[float] = None
    limiting_magnitude: float = 5.5
    # ✅ 新增：光污染环境（影响城市可见性阈值）
    sky_quality: Literal["city", "suburb", "dark_site"] = "city"


class TourPreferences(BaseModel):
    user_level: Literal["beginner", "intermediate", "advanced"] = "beginner"
    style: Literal["story", "science", "observation", "photography"] = "story"
    max_steps: int = 10
    include_deep_sky: bool = True
    include_planets: bool = False
    include_moon_notes: bool = False
    # ✅ 新增：是否要求实时可见性过滤
    require_visible_now: bool = True


class CreateTourSessionRequest(BaseModel):
    locale: str = "zh-CN"
    location: GeoLocation = Field(default_factory=GeoLocation)
    observing_time: ObservingTime = Field(default_factory=ObservingTime)
    equipment: Equipment = Field(default_factory=Equipment)
    preferences: TourPreferences = Field(default_factory=TourPreferences)


class InstructionRequest(BaseModel):
    text: str
    client_event_id: Optional[str] = None
    # ✅ 新增：允许前端携带当前设备时间，解决时区/时间不同步问题
    client_timestamp: Optional[str] = None


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
    hyg_id: Optional[str] = None
    name_zh: str
    name_en: str
    constellation: Optional[str] = None
    ra_deg: Optional[float] = None
    dec_deg: Optional[float] = None
    magnitude: Optional[float] = None
    altitude_deg: Optional[float] = None
    azimuth_deg: Optional[float] = None
    description: Optional[str] = None
    # ✅ 新增：实时可见性状态，前端可据此显示"当前不可见"
    is_visible: Optional[bool] = None
    # ✅ 新增：可见性提示（如"位于西方低空，建议找开阔地"）
    visibility_note: Optional[str] = None


class Narration(BaseModel):
    short: str
    long: str
    fun_fact: Optional[str] = None
    observation_tip: Optional[str] = None
    # ✅ 新增：LLM 生成的动态引导语，如"现在抬头看，那颗最亮的就是织女星"
    live_guide: Optional[str] = None


class TourStep(BaseModel):
    step_index: int
    title: str
    subtitle: Optional[str] = None
    targets: List[TourTarget] = Field(default_factory=list)
    camera: CameraTarget
    narration: Narration
    estimated_minutes: int = 3
    next_hint: Optional[str] = None
    actions: List[str] = Field(default_factory=lambda: ["next", "prev", "pause", "stop", "exit"])


class TourPlan(BaseModel):
    plan_id: str
    title: str
    description: str
    total_minutes: int
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    steps: List[TourStep] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    # ✅ 新增：生成此计划时的实时上下文，便于前端展示
    generated_at: Optional[str] = None
    location_summary: Optional[str] = None


class TourSessionResponse(BaseModel):
    session_id: str
    status: str
    plan: Optional[TourPlan] = None
    current_step_index: int = 0
    message: str = ""
    # ✅ 新增：如果用户问"现在能看到什么"，直接返回天体列表而非完整导览
    visible_objects: Optional[List[TourTarget]] = None


# ✅ 新增：自由问答请求/响应
class ChatRequest(BaseModel):
    text: str
    client_timestamp: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    # 可选：如果回答涉及具体天体，附带定位信息
    referenced_targets: List[TourTarget] = Field(default_factory=list)
    suggested_action: Optional[str] = None  # "start_tour" | "locate_star" | None