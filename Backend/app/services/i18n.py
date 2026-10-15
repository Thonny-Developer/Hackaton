"""Тексты инструкций и причин отказа на RU / KK / EN."""

from typing import Literal

Lang = Literal["ru", "kk", "en"]
LANGS = ("ru", "kk", "en")

NODE_TYPE_NAMES = {
    "ru": {"room": "помещение", "entrance": "вход", "corridor": "коридор", "elevator": "лифт",
           "stairs": "лестница", "ramp": "пандус", "lift": "подъёмник", "toilet": "туалет", "other": "точка"},
    "kk": {"room": "бөлме", "entrance": "кіреберіс", "corridor": "дәліз", "elevator": "лифт",
           "stairs": "баспалдақ", "ramp": "пандус", "lift": "көтергіш", "toilet": "дәретхана", "other": "нүкте"},
    "en": {"room": "room", "entrance": "entrance", "corridor": "corridor", "elevator": "elevator",
           "stairs": "stairs", "ramp": "ramp", "lift": "platform lift", "toilet": "restroom", "other": "point"},
}

OBSTACLE_NAMES = {
    "ru": {"elevator_broken": "лифт не работает", "repair": "ремонт", "blocked": "проход перекрыт",
           "narrowed": "проход сужен", "other": "препятствие"},
    "kk": {"elevator_broken": "лифт істемейді", "repair": "жөндеу", "blocked": "өткел жабық",
           "narrowed": "өткел тарылған", "other": "кедергі"},
    "en": {"elevator_broken": "elevator out of service", "repair": "repair works", "blocked": "passage blocked",
           "narrowed": "passage narrowed", "other": "obstacle"},
}

T: dict[str, dict[str, str]] = {
    "ru": {
        "start": "Начните у «{name}» ({level} этаж)",
        "walk": "Пройдите {dist} м",
        "walk_to": "Пройдите {dist} м до «{name}»",
        "ramp": "Пройдите по пандусу {dist} м",
        "turn_left": "Поверните налево",
        "turn_right": "Поверните направо",
        "elevator_up": "Поднимитесь на лифте на {to} этаж",
        "elevator_down": "Спуститесь на лифте на {to} этаж",
        "lift_up": "Поднимитесь на подъёмнике на {to} этаж",
        "lift_down": "Спуститесь на подъёмнике на {to} этаж",
        "lift_same": "Воспользуйтесь подъёмником",
        "stairs_up": "Поднимитесь по лестнице на {to} этаж",
        "stairs_down": "Спуститесь по лестнице на {to} этаж",
        "ramp_up": "Поднимитесь по пандусу на {to} этаж",
        "ramp_down": "Спуститесь по пандусу на {to} этаж",
        "steps": "Преодолейте ступени ({n} шт.)",
        "arrive": "Вы на месте: «{name}»",
        "same_node": "Вы уже на месте: «{name}»",
        # причины
        "not_connected": "В схеме здания нет пути между этими точками. Сообщите администратору, вероятно, схема неполная.",
        "blocked_by_obstacles": "Подходящий путь существует, но сейчас он перекрыт.",
        "no_accessible_path": "Для выбранного профиля доступного пути нет.",
        "no_accessible_path_and_obstacles": "Для выбранного профиля доступного пути нет, а часть проходов к тому же перекрыта.",
        "start_blocked": "Начальная точка сейчас недоступна.",
        "goal_blocked": "Точка назначения сейчас недоступна.",
        "different_buildings": "Точки находятся в разных зданиях. Маршрут строится в пределах одного здания.",
        # детали
        "p_stairs": "лестница ({where})",
        "p_steps": "ступени: {value} шт., допустимо {limit} ({where})",
        "p_too_narrow": "ширина {value} см, нужно не меньше {limit} см ({where})",
        "p_too_steep": "уклон {value}%, допустимо до {limit}% ({where})",
        "p_threshold": "порог {value} см, допустимо до {limit} см ({where})",
        "p_elevator_not_allowed": "нужен лифт или подъёмник, но профиль их исключает ({where})",
        "p_obstacle": "{kind}{desc} ({where})",
        "w_width_unknown": "Ширина прохода не указана, проверьте на месте ({where})",
        "w_narrowed": "Проход сужен до {value} см ({where})",
        "where_floor": "{level} этаж",
        "where_floors": "между {a} и {b} этажами",
        "where_node": "у «{name}»",
    },
    "kk": {
        "start": "«{name}» жанынан бастаңыз ({level}-қабат)",
        "walk": "{dist} м жүріңіз",
        "walk_to": "«{name}» дейін {dist} м жүріңіз",
        "ramp": "Пандуспен {dist} м жүріңіз",
        "turn_left": "Солға бұрылыңыз",
        "turn_right": "Оңға бұрылыңыз",
        "elevator_up": "Лифтпен {to}-қабатқа көтеріліңіз",
        "elevator_down": "Лифтпен {to}-қабатқа түсіңіз",
        "lift_up": "Көтергішпен {to}-қабатқа көтеріліңіз",
        "lift_down": "Көтергішпен {to}-қабатқа түсіңіз",
        "lift_same": "Көтергішті пайдаланыңыз",
        "stairs_up": "Баспалдақпен {to}-қабатқа көтеріліңіз",
        "stairs_down": "Баспалдақпен {to}-қабатқа түсіңіз",
        "ramp_up": "Пандуспен {to}-қабатқа көтеріліңіз",
        "ramp_down": "Пандуспен {to}-қабатқа түсіңіз",
        "steps": "Сатылардан өтіңіз ({n} дана)",
        "arrive": "Сіз келдіңіз: «{name}»",
        "same_node": "Сіз орындасыз: «{name}»",
        "not_connected": "Ғимарат сызбасында бұл нүктелер арасында жол жоқ. Әкімшіге хабарлаңыз.",
        "blocked_by_obstacles": "Қолайлы жол бар, бірақ қазір ол жабық.",
        "no_accessible_path": "Таңдалған профиль үшін қолжетімді жол жоқ.",
        "no_accessible_path_and_obstacles": "Таңдалған профиль үшін қолжетімді жол жоқ, кейбір өткелдер де жабық.",
        "start_blocked": "Бастапқы нүкте қазір қолжетімсіз.",
        "goal_blocked": "Баратын нүкте қазір қолжетімсіз.",
        "different_buildings": "Нүктелер әртүрлі ғимараттарда. Маршрут бір ғимарат ішінде құрылады.",
        "p_stairs": "баспалдақ ({where})",
        "p_steps": "сатылар: {value}, рұқсат {limit} ({where})",
        "p_too_narrow": "ені {value} см, кемінде {limit} см қажет ({where})",
        "p_too_steep": "еңіс {value}%, рұқсат {limit}% дейін ({where})",
        "p_threshold": "табалдырық {value} см, рұқсат {limit} см дейін ({where})",
        "p_elevator_not_allowed": "лифт қажет, бірақ профиль оны қолданбайды ({where})",
        "p_obstacle": "{kind}{desc} ({where})",
        "w_width_unknown": "Өткелдің ені көрсетілмеген, орнында тексеріңіз ({where})",
        "w_narrowed": "Өткел {value} см дейін тарылған ({where})",
        "where_floor": "{level}-қабат",
        "where_floors": "{a} және {b} қабаттар арасы",
        "where_node": "«{name}» жанында",
    },
    "en": {
        "start": "Start at “{name}” (floor {level})",
        "walk": "Walk {dist} m",
        "walk_to": "Walk {dist} m to “{name}”",
        "ramp": "Take the ramp for {dist} m",
        "turn_left": "Turn left",
        "turn_right": "Turn right",
        "elevator_up": "Take the elevator up to floor {to}",
        "elevator_down": "Take the elevator down to floor {to}",
        "lift_up": "Take the platform lift up to floor {to}",
        "lift_down": "Take the platform lift down to floor {to}",
        "lift_same": "Use the platform lift",
        "stairs_up": "Take the stairs up to floor {to}",
        "stairs_down": "Take the stairs down to floor {to}",
        "ramp_up": "Take the ramp up to floor {to}",
        "ramp_down": "Take the ramp down to floor {to}",
        "steps": "Go over the steps ({n})",
        "arrive": "You have arrived: “{name}”",
        "same_node": "You are already here: “{name}”",
        "not_connected": "The building map has no path between these points. Please tell an administrator, the map may be incomplete.",
        "blocked_by_obstacles": "A suitable path exists, but it is blocked right now.",
        "no_accessible_path": "There is no accessible path for the selected profile.",
        "no_accessible_path_and_obstacles": "There is no accessible path for the selected profile, and some passages are blocked too.",
        "start_blocked": "The starting point is not accessible right now.",
        "goal_blocked": "The destination is not accessible right now.",
        "different_buildings": "The points are in different buildings. Routes are built within one building.",
        "p_stairs": "stairs ({where})",
        "p_steps": "{value} steps, allowed {limit} ({where})",
        "p_too_narrow": "width {value} cm, at least {limit} cm needed ({where})",
        "p_too_steep": "slope {value}%, allowed up to {limit}% ({where})",
        "p_threshold": "threshold {value} cm, allowed up to {limit} cm ({where})",
        "p_elevator_not_allowed": "an elevator is required but the profile excludes it ({where})",
        "p_obstacle": "{kind}{desc} ({where})",
        "w_width_unknown": "Passage width is unknown, check on site ({where})",
        "w_narrowed": "Passage narrowed to {value} cm ({where})",
        "where_floor": "floor {level}",
        "where_floors": "between floors {a} and {b}",
        "where_node": "near “{name}”",
    },
}


def normalize_lang(lang: str | None) -> Lang:
    lang = (lang or "ru").lower()
    if lang in ("kz", "kk", "kaz"):
        return "kk"
    return lang if lang in LANGS else "ru"  # type: ignore[return-value]


def t(lang: Lang, key: str, **kw) -> str:
    return T[lang][key].format(**kw)


def fmt_num(v: float | None) -> str:
    if v is None:
        return "?"
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}".rstrip("0").rstrip(".")
