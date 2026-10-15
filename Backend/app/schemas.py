from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.models import EdgeType, NodeType, ObstacleType, Role
from app.services.profiles import Profile, ProfileOverrides

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Coord = Annotated[float, Field(ge=-100_000, le=100_000)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Lon = Annotated[float, Field(ge=-180, le=180)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------- Auth / Users ----------

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: int
    email: str
    role: Role
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: Role = Role.editor


class UserUpdate(BaseModel):
    password: str | None = Field(None, min_length=10, max_length=128)
    role: Role | None = None
    is_active: bool | None = None


# ---------- Buildings / Floors ----------

class BuildingBase(BaseModel):
    name: Name
    address: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=5000)
    lat: Lat | None = None
    lon: Lon | None = None


class BuildingCreate(BuildingBase):
    external_source: Literal["2gis", "osm"] | None = None
    external_id: str | None = Field(None, max_length=128)


class BuildingUpdate(BaseModel):
    name: Name | None = None
    address: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=5000)
    lat: Lat | None = None
    lon: Lon | None = None


class BuildingOut(ORM, BuildingBase):
    id: int
    external_source: str | None
    external_id: str | None
    graph_version: int
    created_at: datetime
    updated_at: datetime


class FloorBase(BaseModel):
    level: int = Field(ge=-10, le=200)
    name: str | None = Field(None, max_length=100)
    meters_per_px: float = Field(0.05, gt=0, le=100, description="Сколько метров в одном пикселе схемы")
    height_m: float = Field(3.5, gt=0, le=50, description="Высота этажа, нужна для длины лестниц и лифтов")


class FloorCreate(FloorBase):
    pass


class FloorUpdate(BaseModel):
    level: int | None = Field(None, ge=-10, le=200)
    name: str | None = Field(None, max_length=100)
    meters_per_px: float | None = Field(None, gt=0, le=100)
    height_m: float | None = Field(None, gt=0, le=50)


class FloorOut(ORM, FloorBase):
    id: int
    building_id: int
    plan_url: str | None = None
    plan_width_px: int | None
    plan_height_px: int | None


# ---------- Nodes / Edges ----------

class NodeBase(BaseModel):
    type: NodeType
    name: str | None = Field(None, max_length=200)
    ref: str | None = Field(None, max_length=32, description="Номер аудитории, например 204")
    description: str | None = Field(None, max_length=2000)
    x: Coord
    y: Coord
    lat: Lat | None = None
    lon: Lon | None = None
    is_accessible_entrance: bool = False


class NodeCreate(NodeBase):
    floor_id: int


class NodeUpdate(BaseModel):
    floor_id: int | None = None
    type: NodeType | None = None
    name: str | None = Field(None, max_length=200)
    ref: str | None = Field(None, max_length=32)
    description: str | None = Field(None, max_length=2000)
    x: Coord | None = None
    y: Coord | None = None
    lat: Lat | None = None
    lon: Lon | None = None
    is_accessible_entrance: bool | None = None


class NodeOut(ORM, NodeBase):
    id: int
    building_id: int
    floor_id: int


class EdgeBase(BaseModel):
    type: EdgeType
    length_m: float | None = Field(None, ge=0, le=10_000, description="null = посчитать по координатам")
    bidirectional: bool = True
    width_cm: float | None = Field(None, gt=0, le=2000, description="null = ширина неизвестна")
    steps: int = Field(0, ge=0, le=500)
    slope_pct: float = Field(0, ge=0, le=100)
    threshold_cm: float = Field(0, ge=0, le=100)
    description: str | None = Field(None, max_length=300)


class EdgeCreate(EdgeBase):
    from_node_id: int
    to_node_id: int

    @model_validator(mode="after")
    def no_loop(self):
        if self.from_node_id == self.to_node_id:
            raise ValueError("Ребро не может соединять узел сам с собой")
        return self


class EdgeUpdate(BaseModel):
    type: EdgeType | None = None
    length_m: float | None = Field(None, ge=0, le=10_000)
    bidirectional: bool | None = None
    width_cm: float | None = Field(None, gt=0, le=2000)
    steps: int | None = Field(None, ge=0, le=500)
    slope_pct: float | None = Field(None, ge=0, le=100)
    threshold_cm: float | None = Field(None, ge=0, le=100)
    description: str | None = Field(None, max_length=300)


class EdgeOut(ORM, EdgeBase):
    id: int
    building_id: int
    from_node_id: int
    to_node_id: int
    effective_length_m: float | None = Field(None, description="Длина, которая используется при поиске маршрута")


# ---------- Obstacles ----------

class ObstacleBase(BaseModel):
    type: ObstacleType
    description: str | None = Field(None, max_length=500)
    reduced_width_cm: float | None = Field(
        None, gt=0, le=2000, description="Если задано, проход не перекрыт, а сужен до этой ширины"
    )
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ObstacleCreate(ObstacleBase):
    node_id: int | None = None
    edge_id: int | None = None

    @model_validator(mode="after")
    def one_target(self):
        if (self.node_id is None) == (self.edge_id is None):
            raise ValueError("Укажите ровно одно из полей: node_id или edge_id")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at должен быть позже starts_at")
        return self


class ObstacleUpdate(BaseModel):
    type: ObstacleType | None = None
    description: str | None = Field(None, max_length=500)
    reduced_width_cm: float | None = Field(None, gt=0, le=2000)
    is_active: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ObstacleOut(ORM, ObstacleBase):
    id: int
    building_id: int
    node_id: int | None
    edge_id: int | None
    is_active: bool
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


# ---------- Floor details / graph ----------

class FloorDetail(FloorOut):
    nodes: list[NodeOut]
    edges: list[EdgeOut] = Field(description="Рёбра, у которых хотя бы один конец на этом этаже")
    obstacles: list[ObstacleOut] = Field(description="Активные препятствия на узлах и рёбрах этажа")


class GraphExport(BaseModel):
    building: BuildingOut
    floors: list[FloorOut]
    nodes: list[NodeOut]
    edges: list[EdgeOut]


# ---------- Import ----------

class ImportFloor(FloorBase):
    key: str = Field(max_length=64, description="Локальный ключ этажа внутри файла")


class ImportNode(NodeBase):
    key: str = Field(max_length=64)
    floor: str = Field(max_length=64, description="key этажа")


class ImportEdge(EdgeBase):
    from_: str = Field(alias="from", max_length=64)
    to: str = Field(max_length=64)


class GraphImport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    floors: list[ImportFloor] = Field(max_length=100)
    nodes: list[ImportNode] = Field(max_length=10_000)
    edges: list[ImportEdge] = Field(max_length=30_000)


class ImportResult(BaseModel):
    floors: int
    nodes: int
    edges: int
    node_ids: dict[str, int]


class BuildingImport(BuildingCreate):
    graph: GraphImport


# ---------- Search ----------

class SearchHit(BaseModel):
    node_id: int
    building_id: int
    building_name: str
    floor_id: int
    level: int
    type: NodeType
    name: str | None
    ref: str | None
    x: float
    y: float


# ---------- Profiles / Route ----------

class ProfileOut(BaseModel):
    id: str
    title: str
    params: Profile


ProfileName = Literal["default", "wheelchair", "walker", "stroller", "no_stairs"]


class RouteRequest(BaseModel):
    from_node: int
    to_node: int
    profile: ProfileName = "default"
    overrides: ProfileOverrides | None = Field(None, description="Переопределить отдельные параметры профиля")


class RouteNode(BaseModel):
    id: int
    floor_id: int
    level: int
    type: str
    name: str | None
    ref: str | None
    x: float
    y: float


class RouteEdge(BaseModel):
    id: int
    from_node_id: int
    to_node_id: int
    type: str
    length_m: float


class RouteStep(BaseModel):
    action: str = Field(description="start, walk, turn_left, turn_right, elevator_up, stairs_down, ramp, steps, arrive и т.д.")
    text: str
    floor_id: int
    level: int
    to_level: int | None = None
    distance_m: float
    duration_s: float
    node_ids: list[int]
    edge_ids: list[int]


class RouteIssue(BaseModel):
    kind: Literal["constraint", "obstacle", "warning"]
    code: str
    message: str
    edge_id: int | None = None
    node_id: int | None = None
    obstacle_id: int | None = None
    value: float | None = None
    limit: float | None = None


class RouteReason(BaseModel):
    code: str = Field(description="not_connected, blocked_by_obstacles, no_accessible_path, "
                                  "no_accessible_path_and_obstacles, start_blocked, goal_blocked, different_buildings")
    message: str
    details: list[RouteIssue]


class RouteResponse(BaseModel):
    found: bool
    building_id: int
    profile: str
    params: Profile
    total_distance_m: float = 0
    estimated_time_s: float = 0
    floors: list[int] = Field(default_factory=list, description="Уровни этажей по порядку прохождения")
    nodes: list[RouteNode] = Field(default_factory=list)
    edges: list[RouteEdge] = Field(default_factory=list)
    steps: list[RouteStep] = Field(default_factory=list)
    warnings: list[RouteIssue] = Field(default_factory=list)
    reason: RouteReason | None = None
