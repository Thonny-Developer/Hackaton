"""Профили доступности: готовые пресеты + переопределение параметров в запросе."""

from pydantic import BaseModel, Field


class Profile(BaseModel):
    allow_stairs: bool = Field(True, description="Можно ли идти по лестничным маршам")
    max_steps: int | None = Field(None, ge=0, le=100, description="Макс. число ступеней на одном переходе (0 = никаких)")
    min_width_cm: float | None = Field(None, ge=0, le=500, description="Минимальная ширина прохода")
    max_slope_pct: float | None = Field(None, ge=0, le=100, description="Максимальный уклон пандуса, %")
    max_threshold_cm: float | None = Field(None, ge=0, le=50, description="Максимальная высота порога")
    allow_elevator: bool = Field(True, description="Можно ли пользоваться лифтом и подъёмником")
    speed_mps: float = Field(1.2, gt=0.1, le=3, description="Скорость для оценки времени, м/с")


class ProfileOverrides(BaseModel):
    allow_stairs: bool | None = None
    max_steps: int | None = Field(None, ge=0, le=100)
    min_width_cm: float | None = Field(None, ge=0, le=500)
    max_slope_pct: float | None = Field(None, ge=0, le=100)
    max_threshold_cm: float | None = Field(None, ge=0, le=50)
    allow_elevator: bool | None = None
    speed_mps: float | None = Field(None, gt=0.1, le=3)


# Значения по нормам доступной среды (СП 59.13330 / СН РК 3.06-01):
# ширина пути на коляске ≥ 90 см, порог ≤ 1.4 см, уклон пандуса ≤ 8 % (1:12)
PRESETS: dict[str, dict] = {
    "default": {
        "title": {"ru": "Без ограничений", "kk": "Шектеусіз", "en": "No restrictions"},
        "profile": Profile(),
    },
    "wheelchair": {
        "title": {"ru": "Кресло-коляска", "kk": "Мүгедектер арбасы", "en": "Wheelchair"},
        "profile": Profile(
            allow_stairs=False, max_steps=0, min_width_cm=90, max_slope_pct=8, max_threshold_cm=1.4, speed_mps=0.9
        ),
    },
    "walker": {
        "title": {"ru": "Ходунки", "kk": "Жүргіштер", "en": "Walker"},
        "profile": Profile(
            allow_stairs=False, max_steps=0, min_width_cm=70, max_slope_pct=10, max_threshold_cm=2, speed_mps=0.6
        ),
    },
    "stroller": {
        "title": {"ru": "Детская коляска", "kk": "Балалар арбасы", "en": "Stroller"},
        "profile": Profile(
            allow_stairs=False, max_steps=0, min_width_cm=70, max_slope_pct=12, max_threshold_cm=3, speed_mps=1.0
        ),
    },
    "no_stairs": {
        "title": {"ru": "Без лестниц (костыли, трость)", "kk": "Баспалдақсыз", "en": "No stairs"},
        "profile": Profile(allow_stairs=False, max_steps=2, speed_mps=0.8),
    },
}


def resolve_profile(name: str, overrides: ProfileOverrides | None) -> Profile:
    base = PRESETS[name]["profile"]
    if not overrides:
        return base
    # Явный null у числового лимита снимает ограничение; у флагов null игнорируется
    patch = {
        k: v
        for k, v in overrides.model_dump(exclude_unset=True).items()
        if v is not None or k not in ("allow_stairs", "allow_elevator", "speed_mps")
    }
    return base.model_copy(update=patch)
