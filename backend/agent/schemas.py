from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class GeoPoint(BaseModel):
    lat: float
    lon: float
    name: Optional[str] = None


class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    location: Optional[GeoPoint] = None
    client_timestamp: Optional[str] = None


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    error: Optional[str] = None


class AgentChatResponse(BaseModel):
    session_id: str
    answer: str
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)


class ObservationSite(BaseModel):
    name: str
    lat: float
    lon: float
    distance_km: float
    bortle_class: int          # 1=最暗，9=市中心
    score: float               # 0~1，综合推荐分
    reason: str


class CelestialEvent(BaseModel):
    name: str
    date: str
    event_type: str            # "meteor_shower" | "planet_opposition" | "full_moon" | ...
    recommendation: float      # 0~1 推荐指数
    reason: str
    visibility: Optional[str] = None


class TransportPlan(BaseModel):
    mode: str                  # "drive" | "transit" | "walk"
    duration_minutes: int
    distance_km: float
    suggestion: str