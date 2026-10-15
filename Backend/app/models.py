import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    admin = "admin"
    editor = "editor"
    # Обычный посетитель: регистрируется сам, граф менять не может
    user = "user"


class ReportStatus(str, enum.Enum):
    new = "new"
    confirmed = "confirmed"
    rejected = "rejected"


class NodeType(str, enum.Enum):
    room = "room"
    entrance = "entrance"
    corridor = "corridor"
    elevator = "elevator"
    stairs = "stairs"
    ramp = "ramp"
    lift = "lift"  # подъёмник (платформа)
    toilet = "toilet"
    other = "other"


class EdgeType(str, enum.Enum):
    corridor = "corridor"
    door = "door"
    stairs = "stairs"
    elevator = "elevator"
    ramp = "ramp"
    lift = "lift"
    outdoor = "outdoor"


class ObstacleType(str, enum.Enum):
    elevator_broken = "elevator_broken"
    repair = "repair"
    blocked = "blocked"
    narrowed = "narrowed"
    other = "other"


def _enum(e: type[enum.Enum]) -> Enum:
    # VARCHAR + CHECK вместо нативного enum: проще добавлять значения миграциями
    return Enum(e, native_enum=False, length=32, validate_strings=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.editor)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    name: Mapped[str | None] = mapped_column(String(100))
    # Что важно пользователю на маршруте: noSteps, elevator, wide, ramp, toilet
    accessibility_prefs: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), primary_key=True,
                                             index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(TimestampMixin, Base):
    """Сообщение посетителя об изменении доступности. На маршруты не влияет,
    пока редактор не проверит его и не заведёт препятствие."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    text: Mapped[str] = mapped_column(String(2000))
    status: Mapped[ReportStatus] = mapped_column(_enum(ReportStatus), default=ReportStatus.new, index=True)


class Building(TimestampMixin, Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    external_source: Mapped[str | None] = mapped_column(String(16))  # 2gis | osm
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    # Растёт при любом изменении графа: по нему воркеры понимают, что кэш устарел
    graph_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    floors: Mapped[list["Floor"]] = relationship(
        back_populates="building", cascade="all, delete-orphan", passive_deletes=True, order_by="Floor.level"
    )

    __table_args__ = (UniqueConstraint("external_source", "external_id", name="uq_buildings_external"),)


class Floor(TimestampMixin, Base):
    __tablename__ = "floors"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(100))
    meters_per_px: Mapped[float] = mapped_column(Float, default=0.05)
    height_m: Mapped[float] = mapped_column(Float, default=3.5)
    # Привязка к карте: где на местности левый верхний угол схемы и как схема повёрнута
    geo_origin_lat: Mapped[float | None] = mapped_column(Float)
    geo_origin_lon: Mapped[float | None] = mapped_column(Float)
    geo_rotation_deg: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    plan_object_key: Mapped[str | None] = mapped_column(String(300))
    plan_content_type: Mapped[str | None] = mapped_column(String(50))
    plan_width_px: Mapped[int | None] = mapped_column(Integer)
    plan_height_px: Mapped[int | None] = mapped_column(Integer)

    building: Mapped[Building] = relationship(back_populates="floors")

    __table_args__ = (
        UniqueConstraint("building_id", "level", name="uq_floors_building_level"),
        CheckConstraint("meters_per_px > 0", name="ck_floors_scale_positive"),
    )


class Node(TimestampMixin, Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), index=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id", ondelete="CASCADE"), index=True)
    type: Mapped[NodeType] = mapped_column(_enum(NodeType))
    name: Mapped[str | None] = mapped_column(String(200))
    ref: Mapped[str | None] = mapped_column(String(32), index=True)  # номер аудитории
    description: Mapped[str | None] = mapped_column(Text)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    # Для входов: можно ли попасть в здание с улицы без ступеней
    is_accessible_entrance: Mapped[bool] = mapped_column(Boolean, default=False)


class Edge(TimestampMixin, Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), index=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    type: Mapped[EdgeType] = mapped_column(_enum(EdgeType))
    # null = посчитать по координатам и масштабу этажа
    length_m: Mapped[float | None] = mapped_column(Float)
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=True)
    # null = ширина неизвестна (маршрут строится, но с предупреждением)
    width_cm: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    slope_pct: Mapped[float] = mapped_column(Float, default=0)
    threshold_cm: Mapped[float] = mapped_column(Float, default=0)
    description: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        CheckConstraint("from_node_id <> to_node_id", name="ck_edges_no_loop"),
        CheckConstraint("steps >= 0", name="ck_edges_steps"),
        CheckConstraint("slope_pct >= 0", name="ck_edges_slope"),
        CheckConstraint("threshold_cm >= 0", name="ck_edges_threshold"),
    )


class Obstacle(TimestampMixin, Base):
    __tablename__ = "obstacles"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    edge_id: Mapped[int | None] = mapped_column(ForeignKey("edges.id", ondelete="CASCADE"), index=True)
    type: Mapped[ObstacleType] = mapped_column(_enum(ObstacleType))
    description: Mapped[str | None] = mapped_column(String(500))
    # Если задано, препятствие не перекрывает проход, а сужает его до этой ширины
    reduced_width_cm: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint(
            "(node_id IS NOT NULL AND edge_id IS NULL) OR (node_id IS NULL AND edge_id IS NOT NULL)",
            name="ck_obstacles_target",
        ),
    )
