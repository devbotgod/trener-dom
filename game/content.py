"""Контент игры «You vs You» — упражнения, монстры, уровни в биомах.

1 повтор (или 1 секунда удержания) = 1 урон. HP врага = сколько нужно сделать
(с учётом твоего урона за повтор). Все упражнения — дома, без инвентаря.
Структура: биомы × 5 уровней. 5-й уровень биома — босс; победа над ним
открывает следующий биом.
"""

from __future__ import annotations

# --- Цели тренировок (онбординг) ----------------------------------------------
# kind: goal — цель-объектив (раскрывается в группы мышц) | muscle — группа мышц
GOAL_GROUPS = [
    # объективы
    {"id": "slim", "name": "Похудеть", "icon": "💧", "kind": "goal", "expand": ["cardio", "quads", "glutes", "abs"]},
    {"id": "waist", "name": "Убрать бока", "icon": "🔥", "kind": "goal", "expand": ["obliques", "abs", "cardio"]},
    {"id": "belly", "name": "Убрать живот", "icon": "🎯", "kind": "goal", "expand": ["abs", "obliques", "cardio"]},
    {"id": "sport", "name": "Заниматься спортом", "icon": "🏃", "kind": "goal", "expand": ["chest", "back", "abs", "quads", "glutes", "cardio"]},
    {"id": "tone", "name": "Подтянуть тело", "icon": "✨", "kind": "goal", "expand": ["chest", "abs", "quads", "glutes", "cardio"]},
    {"id": "booty", "name": "Упругие ягодицы", "icon": "🍑", "kind": "goal", "expand": ["glutes", "hamstrings"]},
    {"id": "maintain", "name": "Держать тонус", "icon": "🌿", "kind": "goal", "expand": ["chest", "back", "abs", "quads", "glutes", "cardio"]},
    {"id": "strength", "name": "Стать сильнее", "icon": "🏋️", "kind": "goal", "expand": ["chest", "triceps", "back", "quads"]},
    {"id": "endurance", "name": "Выносливость", "icon": "🫁", "kind": "goal", "expand": ["cardio", "quads", "abs"]},
    {"id": "posture", "name": "Осанка и спина", "icon": "🧍", "kind": "goal", "expand": ["back", "abs", "shoulders"]},
    # группы мышц
    {"id": "chest", "name": "Грудь", "icon": "🫀", "kind": "muscle"},
    {"id": "back", "name": "Спина", "icon": "🔙", "kind": "muscle"},
    {"id": "shoulders", "name": "Плечи", "icon": "🎽", "kind": "muscle"},
    {"id": "triceps", "name": "Руки", "icon": "💪", "kind": "muscle"},
    {"id": "abs", "name": "Пресс", "icon": "🧨", "kind": "muscle"},
    {"id": "obliques", "name": "Косые", "icon": "🌀", "kind": "muscle"},
    {"id": "quads", "name": "Бёдра (перед)", "icon": "🦵", "kind": "muscle"},
    {"id": "hamstrings", "name": "Бёдра (зад)", "icon": "🦿", "kind": "muscle"},
    {"id": "glutes", "name": "Ягодицы", "icon": "🍑", "kind": "muscle"},
    {"id": "calves", "name": "Икры", "icon": "🦶", "kind": "muscle"},
    {"id": "cardio", "name": "Кардио", "icon": "🔥", "kind": "muscle"},
]
_GOAL_BY_ID = {g["id"]: g for g in GOAL_GROUPS}


def expand_goals(goals: list[str]) -> set[str]:
    """Раскрыть выбранные цели (объективы) в набор групп мышц."""
    out: set[str] = set()
    for g in goals or []:
        gg = _GOAL_BY_ID.get(g)
        if not gg:
            continue
        if gg.get("expand"):
            out.update(gg["expand"])
        else:
            out.add(g)
    return out


def _ex(name, icon, groups, mode, det, how, tip=""):
    return {"name": name, "icon": icon, "groups": groups, "mode": mode,
            "type": "hold" if mode == "hold" else "reps",
            "detector": det, "how": how, "tip": tip}


def _V(joints, amp, posture="floor", strict=True):
    # posture: floor (лёжа/упор) | stand (стоя) | any — не даёт «читерить» другим упражнением
    # strict=False — считать без проверки глубины/темпа (для мелко-амплитудных: носки)
    return {"kind": "vertical", "joints": joints, "amp": amp, "posture": posture, "strict": strict}


_HOLD = {"kind": "hold"}
_CAM_FRONT = "Телефон на полу перед собой, в кадре голова и плечи."
_CAM_SIDE = "Камера сбоку, чтобы видеть тело целиком."
_CAM_FULL = "Встань в полный рост в кадр (лучше задняя камера)."

# --- Упражнения. mode: reps (камера повторы) | hold (сек) | manual (ручной +) ---
EXERCISES: dict[str, dict] = {
    "pushup": _ex("Отжимания", "🔥", ["chest", "triceps", "shoulders"], "reps", _V(["nose", "shoulders"], 0.08), "Упор лёжа, руки чуть шире плеч. Опускай грудь к полу и выжимайся. С колен — можно.", _CAM_FRONT),
    "widepushup": _ex("Широкие отжимания", "💥", ["chest"], "reps", _V(["nose", "shoulders"], 0.08), "Широкая постановка рук — акцент на грудь.", _CAM_FRONT),
    "inclinepushup": _ex("Отжимания с возвышения", "📐", ["chest"], "reps", _V(["nose", "shoulders"], 0.07), "Руки на диван/стул, отжимайся под наклоном — легче, низ груди.", _CAM_SIDE),
    "declinepushup": _ex("Отжимания ноги вверх", "🔻", ["chest", "shoulders"], "reps", _V(["nose", "shoulders"], 0.08), "Ноги на возвышении — акцент верх груди и плечи.", _CAM_FRONT),
    "diamondpushup": _ex("Алмазные отжимания", "💎", ["triceps", "chest"], "reps", _V(["nose", "shoulders"], 0.07), "Ладони «ромбом» под грудью. Акцент на трицепс.", _CAM_FRONT),
    "pikepushup": _ex("Пайк-отжимания", "🔺", ["shoulders", "triceps"], "reps", _V(["shoulders"], 0.07, "any"), "Встань в позу «домик»: таз вверх, руки и ноги на полу, тело углом. Сгибая руки, опускай макушку к полу между ладоней и выжимайся.", _CAM_SIDE),
    "tricepdip": _ex("Обратные отжимания", "💪", ["triceps"], "reps", _V(["shoulders"], 0.06), "Сядь спиной к дивану/стулу, руки на край, таз на весу. Сгибая локти назад, опускай таз вниз и выжимайся вверх.", _CAM_SIDE),
    "superman": _ex("Супермен", "🦸", ["back"], "hold", _HOLD, "Ляг на живот, руки вытяни вперёд. Оторви от пола руки, грудь и ноги и держи, напрягая спину и ягодицы.", "Камера сбоку (на доверии)."),
    "birddog": _ex("Птица-собака", "🐦", ["back", "abs"], "hold", _HOLD, "Встань на четвереньки. Вытяни вперёд одну руку и назад противоположную ногу, держи ровно, не заваливаясь. Меняй стороны.", _CAM_SIDE),
    "plank": _ex("Планка", "🛡️", ["abs"], "hold", _HOLD, "Упор на предплечья и носки, тело — прямая линия. Секунда = удар.", _CAM_SIDE),
    "sideplank": _ex("Боковая планка", "🧘", ["obliques"], "hold", _HOLD, "На боку, упор на предплечье, таз вверх, тело ровное. Меняй сторону.", _CAM_SIDE),
    "situp": _ex("Скручивания", "🧨", ["abs"], "reps", _V(["shoulders"], 0.07), "Ляг на спину, колени согнуты, стопы на полу. Поднимай корпус до положения сидя и плавно опускайся.", _CAM_SIDE),
    "crunch": _ex("Скручивания короткие", "🎯", ["abs"], "reps", _V(["shoulders"], 0.05), "Ляг на спину, колени согнуты, руки у висков. Отрывай от пола только лопатки, тянись к коленям — короткое движение, поясница прижата.", _CAM_SIDE),
    "legraise": _ex("Подъём ног", "🦿", ["abs"], "reps", _V(["ankles"], 0.08), "Лёжа, руки под таз. Поднимай прямые ноги вверх и медленно опускай.", _CAM_SIDE),
    "reversecrunch": _ex("Обратные скручивания", "🔄", ["abs"], "reps", _V(["hips"], 0.06), "Ляг на спину, руки вдоль тела. Подтягивай согнутые колени к груди, отрывая таз от пола, затем медленно опускай.", _CAM_SIDE),
    "vup": _ex("Складка V-up", "✌️", ["abs"], "reps", _V(["shoulders"], 0.08), "Ляг на спину, руки за головой. Одновременно поднимай прямые ноги и корпус, тянись руками к стопам — тело складывается в букву V.", _CAM_SIDE),
    "flutterkicks": _ex("Ножницы", "✂️", ["abs"], "reps", _V(["ankles"], 0.05), "Ляг на спину, руки под ягодицы, прямые ноги подними на 20-30 см. Быстро поочерёдно поднимай и опускай ноги, будто плывёшь.", _CAM_SIDE),
    "bicyclecrunch": _ex("Велосипед", "🚴", ["obliques", "abs"], "reps", _V(["shoulders"], 0.05), "Ляг на спину, руки у висков, ноги подними и согни. Поочерёдно тяни локоть к противоположному колену, вторую ногу выпрямляя — будто крутишь педали велосипеда.", _CAM_SIDE),
    "heeltouches": _ex("Касания пяток", "👐", ["obliques"], "manual", {"kind": "manual"}, "Ляг на спину, колени согнуты, плечи чуть приподняты. Тянись рукой к пятке своей стороны, слегка наклоняя корпус вбок. Чередуй стороны.", "Движение мелкое — камера его не ловит. Жми по кругу-счётчику после каждого касания."),
    "russiantwist": _ex("Русский твист", "🌀", ["obliques"], "reps", _V(["shoulders"], 0.05), "Сядь, немного отклони корпус назад, стопы оторви от пола. Соединив руки, поворачивай корпус влево-вправо, касаясь пола сбоку.", "Камера спереди."),
    "squat": _ex("Приседания", "🦵", ["quads", "glutes"], "reps", _V(["hips"], 0.09, "stand"), "Ноги на ширине плеч, приседай до параллели бёдер и вставай.", _CAM_FULL),
    "jumpsquat": _ex("Приседания с прыжком", "⚡", ["quads", "cardio"], "reps", _V(["hips"], 0.1, "stand"), "Присед и мощный прыжок вверх, мягко приземляйся в присед.", _CAM_FULL),
    "squatpulse": _ex("Присед-пульс", "🔃", ["quads"], "reps", _V(["hips"], 0.05, "stand"), "В нижней точке приседа короткие пружинящие движения.", _CAM_FULL),
    "wallsit": _ex("Стенка", "🪑", ["quads"], "hold", _HOLD, "Спиной к стене, присядь до 90° и держи.", _CAM_SIDE),
    "lunge": _ex("Выпады", "🚶", ["quads", "glutes"], "reps", _V(["hips"], 0.08, "stand"), "Встань прямо. Шагни вперёд и опускайся, пока оба колена не согнутся под 90°, оттолкнись назад. Чередуй ноги.", _CAM_FULL),
    "curtsylunge": _ex("Реверанс-выпады", "💃", ["glutes"], "reps", _V(["hips"], 0.07, "stand"), "Встань прямо. Шагни одной ногой по диагонали назад крест-накрест и присядь (как реверанс), затем вернись. Чередуй ноги.", _CAM_FULL),
    "sumosquat": _ex("Сумо-присед", "🧎", ["glutes", "quads"], "reps", _V(["hips"], 0.08, "stand"), "Поставь ноги широко, носки разверни наружу. Приседай, разводя колени в стороны, до параллели бёдер с полом, и вставай.", _CAM_FULL),
    "glutebridge": _ex("Ягодичный мост", "🍑", ["glutes", "hamstrings"], "reps", _V(["hips"], 0.06), "Ляг на спину, колени согнуты, стопы у таза. Поднимай таз вверх до прямой линии от колен до плеч, сжимая ягодицы, и опускай.", _CAM_SIDE),
    "hipthrust": _ex("Ягодичный толчок", "🌉", ["glutes"], "reps", _V(["hips"], 0.07), "Обопрись лопатками на край дивана, стопы на полу. Толкай таз вверх до прямой линии, сжимая ягодицы вверху, и опускай.", _CAM_SIDE),
    "singlelegbridge": _ex("Мост на одной ноге", "🦩", ["glutes", "hamstrings"], "reps", _V(["hips"], 0.06), "Ягодичный мост с одной поднятой ногой. Смени ногу.", _CAM_SIDE),
    "goodmorning": _ex("Наклоны «доброе утро»", "🙇", ["hamstrings"], "reps", _V(["shoulders"], 0.07, "stand"), "Встань прямо, руки у висков, лёгкий прогиб в спине. Наклоняйся вперёд, отводя таз назад (колени чуть согнуты), до параллели корпуса с полом, и выпрямляйся.", _CAM_SIDE),
    "donkeykick": _ex("Махи назад", "🐴", ["glutes"], "reps", _V(["ankles"], 0.06), "Встань на четвереньки. Поднимай согнутую в колене ногу вверх пяткой к потолку, напрягая ягодицу. Смени ногу в след. подход.", _CAM_SIDE),
    "calfraise": _ex("Подъёмы на носки", "🦶", ["calves"], "reps", _V(["nose", "shoulders", "hips"], 0.015, "stand", strict=False), "Встань прямо, поднимайся на носки как можно выше и плавно опускайся. Ровный темп.", _CAM_FULL),
    "highknees": _ex("Высокие колени", "🏃", ["cardio", "quads"], "reps", _V(["knees"], 0.06, "stand"), "Бег на месте: поднимай колени как можно выше.", _CAM_FULL),
    "mountainclimber": _ex("Скалолаз", "🧗", ["cardio", "abs"], "reps", _V(["knees"], 0.05), "Прими упор лёжа. Быстро поочерёдно подтягивай колени к груди, будто бежишь на месте в упоре.", _CAM_SIDE),
    "burpee": _ex("Бёрпи", "💫", ["cardio", "chest"], "reps", _V(["nose", "shoulders"], 0.1, "any"), "Из стойки: присядь, руки на пол, прыжком отведи ноги в упор лёжа (можно отжаться), прыжком верни ноги к рукам и выпрыгни вверх.", _CAM_FULL),
    "kneepushup": _ex("Отжимания с колен", "🤲", ["chest", "triceps"], "reps", _V(["nose", "shoulders"], 0.07), "Упор лёжа с колен (колени на полу). Опускай грудь к полу и выжимайся. Лёгкий вариант отжиманий.", _CAM_FRONT),
    "reverselunge": _ex("Обратные выпады", "⬅️", ["quads", "glutes"], "reps", _V(["hips"], 0.08, "stand"), "Встань прямо. Делай шаг назад и опускайся, пока оба колена не согнутся под 90°, вернись. Чередуй ноги.", _CAM_FULL),
    "sidelunge": _ex("Боковые выпады", "↔️", ["quads", "glutes"], "reps", _V(["hips"], 0.07, "stand"), "Встань прямо, шагни широко в сторону и присядь на эту ногу, вторую держи прямой. Вернись, чередуй стороны.", _CAM_FULL),
    "lungejump": _ex("Выпады в прыжке", "🦘", ["quads", "cardio"], "reps", _V(["hips"], 0.09, "stand"), "Из выпада выпрыгни вверх и в прыжке смени ноги местами, приземлись в выпад на другую ногу.", _CAM_FULL),
    "toetouch": _ex("Наклоны к носкам", "🙆", ["hamstrings"], "reps", _V(["shoulders"], 0.1, "stand"), "Встань прямо, ноги на ширине плеч. Наклоняйся вниз, тянись руками к носкам (колени можно чуть согнуть), и выпрямляйся.", _CAM_FULL),
}


def exercises_for_goals(goals: list[str]) -> tuple[list[str], list[str]]:
    """(primary, base) — камерные (reps) упражнения под цели и общий пул."""
    gs = expand_goals(goals)
    base = [k for k, e in EXERCISES.items() if e["mode"] == "reps"]
    primary = [k for k in base if set(EXERCISES[k]["groups"]) & gs]
    return (primary or base), base


def _enemy(eid, name, hp, exercise, attack, xp, kind="normal", avatar="ogre"):
    return {
        "id": eid, "name": name, "hp": int(hp), "exercise": exercise,
        "attack": round(attack, 2), "xp": int(xp), "kind": kind, "avatar": avatar,
    }


# --- Биомы и генерация 50 уровней (10 биомов × 5) -----------------------------
BIOMES = [
    {"key": "forest", "name": "Зелёные земли", "rank": "E", "color": "#4caf50",
     "mobs": ["slime", "ogre", "goblin"], "boss": "ogre_boss", "boss_name": "Вожак огров",
     "levels": ["Шёпот леса", "Мшистый овраг", "Древний дуб", "Волчья застава", "Трон Вожака"]},
    {"key": "desert", "name": "Выжженная пустошь", "rank": "E", "color": "#d9a441",
     "mobs": ["goblin", "spider", "orc"], "boss": "goblin_boss", "boss_name": "Король песков",
     "levels": ["Песчаный тракт", "Кости каравана", "Оазис миражей", "Гнездо скорпионов", "Дворец Короля"]},
    {"key": "swamp", "name": "Гнилые топи", "rank": "D", "color": "#6b8e3d",
     "mobs": ["spider", "troll", "slime"], "boss": "spider", "boss_name": "Матка пауков",
     "levels": ["Туманная гать", "Утопший храм", "Логово пиявок", "Паутинный лог", "Гнездо Матки"]},
    {"key": "jungle", "name": "Дикие джунгли", "rank": "D", "color": "#2e9e5b",
     "mobs": ["harpy", "orc", "spider"], "boss": "harpy_boss", "boss_name": "Хищник джунглей",
     "levels": ["Лиановый полог", "Затерянные руины", "Река пираний", "Алтарь идола", "Клетка Хищника"]},
    {"key": "volcano", "name": "Огненные недра", "rank": "C", "color": "#e2622a",
     "mobs": ["hound", "orc", "demon", "golem"], "boss": "demon_boss", "boss_name": "Балрог",
     "levels": ["Тлеющий разлом", "Лавовые мосты", "Кузня демонов", "Пепельный трон", "Сердце Балрога"]},
    {"key": "tundra", "name": "Ледяная пустошь", "rank": "C", "color": "#5bb6e0",
     "mobs": ["troll", "golem", "harpy"], "boss": "troll_boss", "boss_name": "Ледяной вождь",
     "levels": ["Снежный перевал", "Ледяные клыки", "Замёрзшее озеро", "Чертог вьюги", "Логово Вождя"]},
    {"key": "ruins", "name": "Забытые руины", "rank": "B", "color": "#b98a54",
     "mobs": ["golem", "undead", "orc"], "boss": "golem", "boss_name": "Древний голем",
     "levels": ["Разбитые ворота", "Зал колонн", "Гробница стража", "Библиотека праха", "Престол Голема"]},
    {"key": "crystal", "name": "Кристальные пещеры", "rank": "B", "color": "#7b6bff",
     "mobs": ["golem", "spider", "undead"], "boss": "golem", "boss_name": "Кристальный голем",
     "levels": ["Мерцающий грот", "Зеркальный тоннель", "Жила силы", "Кристальный сад", "Око Хозяина"]},
    {"key": "graveyard", "name": "Проклятое кладбище", "rank": "A", "color": "#8a4fd0",
     "mobs": ["undead", "hound", "spider"], "boss": "lich", "boss_name": "Лич-некромант",
     "levels": ["Ворота мёртвых", "Аллея надгробий", "Древний склеп", "Костяная яма", "Курган Лича"]},
    {"key": "hell", "name": "Бездна", "rank": "S", "color": "#ff2d55",
     "mobs": ["demon", "undead", "hound"], "boss": "dragon", "boss_name": "Владыка Бездны",
     "levels": ["Врата тьмы", "Мост над бездной", "Адское пламя", "Тень отчаяния", "Престол Владыки"]},
    {"key": "sky", "name": "Небесная гряда", "rank": "S", "color": "#31c6d4",
     "mobs": ["harpy", "demon", "golem"], "boss": "dragon", "boss_name": "Небесный дракон",
     "levels": ["Кромка облаков", "Парящие руины", "Гнездо бури", "Мост ветров", "Логово Дракона"]},
    {"key": "ocean", "name": "Морская бездна", "rank": "S", "color": "#2f8fd4",
     "mobs": ["spider", "slime", "hound"], "boss": "demon_boss", "boss_name": "Владыка глубин",
     "levels": ["Коралловый риф", "Затонувший корабль", "Пещеры мурен", "Тёмная впадина", "Трон Глубин"]},
    {"key": "storm", "name": "Грозовые пики", "rank": "SS", "color": "#7a6cff",
     "mobs": ["golem", "demon", "undead"], "boss": "dragon", "boss_name": "Повелитель гроз",
     "levels": ["Тропа молний", "Громовой уступ", "Око бури", "Ледяной шпиль", "Вершина Гроз"]},
    {"key": "citadel", "name": "Золотой чертог", "rank": "SS", "color": "#e8b43a",
     "mobs": ["undead", "demon", "golem"], "boss": "demon_boss", "boss_name": "Забытый Бог",
     "levels": ["Врата света", "Зал колонн", "Небесный сад", "Чертог славы", "Трон Бога"]},
    {"key": "canyon", "name": "Багровый каньон", "rank": "SS", "color": "#c0392b",
     "mobs": ["orc", "goblin", "demon"], "boss": "demon_boss", "boss_name": "Каньонный титан",
     "levels": ["Пыльная тропа", "Красные скалы", "Ущелье ветров", "Логово стервятников", "Сердце каньона"]},
    {"key": "mushroom", "name": "Грибной лес", "rank": "SS", "color": "#8e44ad",
     "mobs": ["slime", "spider", "goblin"], "boss": "spider", "boss_name": "Мицелий-матка",
     "levels": ["Споровые поля", "Светящаяся чаща", "Гнилые корни", "Паучьи сети", "Сердце грибницы"]},
    {"key": "aurora", "name": "Северное сияние", "rank": "SSS", "color": "#26c6da",
     "mobs": ["harpy", "undead", "golem"], "boss": "dragon", "boss_name": "Ледяной феникс",
     "levels": ["Снежная гладь", "Ледяные пики", "Замёрзший водопад", "Чертог сияния", "Гнездо Феникса"]},
    {"key": "wasteland", "name": "Радиоактивная пустошь", "rank": "SSS", "color": "#7cb342",
     "mobs": ["undead", "hound", "orc"], "boss": "golem", "boss_name": "Мутант-гигант",
     "levels": ["Ржавые руины", "Кислотные топи", "Заражённый бункер", "Логово мутантов", "Эпицентр"]},
    {"key": "temple", "name": "Забытый храм", "rank": "SSS", "color": "#d4a017",
     "mobs": ["undead", "golem", "demon"], "boss": "lich", "boss_name": "Жрец древних",
     "levels": ["Заросшие ступени", "Зал ловушек", "Святилище", "Гробница царя", "Алтарь древних"]},
    {"key": "void", "name": "Пустота", "rank": "SSS", "color": "#5c6bc0",
     "mobs": ["demon", "undead", "hound"], "boss": "dragon", "boss_name": "Пожиратель миров",
     "levels": ["Разлом реальности", "Осколки миров", "Мост в никуда", "Око бездны", "Трон Пустоты"]},
]
_EX_EARLY = ["pushup", "squat", "situp"]
_EX_ALL = ["pushup", "squat", "situp", "highknees", "plank", "sideplank"]
_MOB_NAMES = {
    "slime": "Слизень", "ogre": "Огр", "goblin": "Гоблин", "spider": "Паук",
    "orc": "Орк", "troll": "Тролль", "demon": "Демон", "hound": "Гончая",
    "golem": "Голем", "undead": "Скелет", "dragon": "Дракон", "harpy": "Гарпия",
}
_EARLY_BIOMES = ("forest", "desert", "swamp", "jungle")


def _gen_gates() -> list[dict]:
    gates = []
    gi = 0  # глобальный индекс уровня 0..49
    for b in BIOMES:
        pool = _EX_EARLY if b["key"] in _EARLY_BIOMES else _EX_ALL
        for lvl in range(5):
            boss_level = lvl == 4
            base = 5 + gi * 0.10
            atk = 0.3 + gi * 0.015
            xpb = 12 + gi * 2.5
            n = 5 if boss_level else 4
            enemies = []
            for k in range(n):
                last = k == n - 1
                ex = pool[(gi + k) % len(pool)]
                if boss_level and last:
                    enemies.append(_enemy(
                        f"g{gi}b", b["boss_name"], round(base * 2.1),
                        "pushup", atk * 1.4, xpb * 5, kind="boss", avatar=b["boss"],
                    ))
                else:
                    av = b["mobs"][k % len(b["mobs"])]
                    elite = last or (k % 3 == 2)
                    nm = _MOB_NAMES.get(av, "Монстр") + (" (элита)" if elite else "")
                    enemies.append(_enemy(
                        f"g{gi}e{k}", nm, round(base * (1.0 + 0.14 * k)),
                        ex, atk * (1.25 if elite else 1.0),
                        xpb + (10 if elite else 0),
                        kind="elite" if elite else "normal", avatar=av,
                    ))
            rank = b["rank"]
            name = b["levels"][lvl]
            gates.append({
                "id": f"gate_{gi + 1}", "rank": rank, "name": name,
                "biome": b["key"], "biome_name": b["name"], "color": b["color"],
                "subtitle": f'ВРАТА {rank} · {name.upper()}',
                "reward_xp": int(30 + gi * 10), "is_biome_boss": boss_level,
                "enemies": enemies,
            })
            gi += 1
    return gates


GATES: list[dict] = _gen_gates()
GATES_BY_ID = {g["id"]: g for g in GATES}


def gate_index(gate_id: str) -> int:
    for i, g in enumerate(GATES):
        if g["id"] == gate_id:
            return i
    return 0


# --- Прогрессия игрока (мягкая кривая) ----------------------------------------
BASE_MAX_HP = 168
HP_PER_LEVEL = 12
BASE_DAMAGE = 1
DAMAGE_PER_5_LEVELS = 1
HP_REGEN_PER_MIN = 2.0

TRAIN_XP_PER_REP = 1
TRAIN_DAILY_XP_CAP = 100


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    return int(40 * (level - 1) ** 1.35)


def level_from_xp(xp: int) -> int:
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def max_hp_for_level(level: int) -> int:
    return BASE_MAX_HP + (level - 1) * HP_PER_LEVEL


def damage_for_level(level: int) -> int:
    return BASE_DAMAGE  # 1 повтор = 1 урон всегда (HP врага = число повторов)


RANK_ORDER = ["E", "D", "C", "B", "A", "S"]

# --- Ежедневные задания (свои под режим) -------------------------------------
_Q_REPS = [
    {"id": "reps30", "icon": "🔥", "text": "Сделать 30 повторов", "metric": "reps", "target": 30, "reward": 20},
    {"id": "reps60", "icon": "🔥", "text": "Сделать 60 повторов", "metric": "reps", "target": 60, "reward": 40},
    {"id": "reps100", "icon": "🔥", "text": "Сделать 100 повторов", "metric": "reps", "target": 100, "reward": 70},
]
ADVENTURE_QUESTS = _Q_REPS + [
    {"id": "kills5", "icon": "💀", "text": "Победить 5 врагов", "metric": "kills", "target": 5, "reward": 25},
    {"id": "kills10", "icon": "💀", "text": "Победить 10 врагов", "metric": "kills", "target": 10, "reward": 45},
    {"id": "gate1", "icon": "🏰", "text": "Зачистить 1 уровень", "metric": "gates", "target": 1, "reward": 30},
    {"id": "gate2", "icon": "🏰", "text": "Зачистить 2 уровня", "metric": "gates", "target": 2, "reward": 55},
]
SIMPLE_QUESTS = _Q_REPS + [
    {"id": "work3", "icon": "✅", "text": "Выполнить 3 упражнения дня", "metric": "workout", "target": 3, "reward": 30},
    {"id": "workall", "icon": "🎉", "text": "Пройти всю тренировку дня", "metric": "workout", "target": 5, "reward": 55},
]


def daily_quests(ordinal: int, mode: str = "adventure") -> list[dict]:
    """3 задания на день под режим (детерминированно по дате)."""
    pool = SIMPLE_QUESTS if mode == "simple" else ADVENTURE_QUESTS
    n = len(pool)
    return [pool[(ordinal + i * 2) % n] for i in range(3)]


# --- Кастомизация ------------------------------------------------------------
TITLES = [
    {"id": "rookie", "name": "Новобранец", "need": None, "val": 0, "desc": "Доступно сразу"},
    {"id": "fighter", "name": "Боец", "need": "level", "val": 5, "desc": "5 уровень"},
    {"id": "worker", "name": "Трудяга", "need": "reps", "val": 300, "desc": "300 повторов всего"},
    {"id": "gatestorm", "name": "Гроза Врат", "need": "gates", "val": 5, "desc": "5 врат зачищено"},
    {"id": "unbroken", "name": "Несокрушимый", "need": "streak", "val": 7, "desc": "Стрик 7 дней"},
    {"id": "veteran", "name": "Ветеран", "need": "level", "val": 10, "desc": "10 уровень"},
    {"id": "iron", "name": "Железный", "need": "reps", "val": 1500, "desc": "1500 повторов всего"},
    {"id": "slayer", "name": "Палач", "need": "kills", "val": 100, "desc": "100 убийств"},
    {"id": "legend", "name": "Легенда", "need": "level", "val": 20, "desc": "20 уровень"},
]
TITLES_BY_ID = {t["id"]: t for t in TITLES}
AVATAR_CHOICES = ["🧑", "🥷", "🦸", "🧔", "👩", "💪", "🐉", "🔥", "⚔️", "👑"]

# --- Программы сложности ------------------------------------------------------
PROGRAMS = {
    "novice": {"name": "Новичок", "mult": 0.7, "icon": "🌱", "desc": "Меньше повторов на врага. Мягкий старт."},
    "medium": {"name": "Средний", "mult": 1.0, "icon": "💪", "desc": "Стандартная нагрузка."},
    "pro":    {"name": "Продвинутый", "mult": 1.45, "icon": "🔥", "desc": "Больше повторов. Серьёзный вызов."},
}
DEFAULT_PROGRAM_MULT = 1.0
MAX_FREEZES = 2

# Заморозки (дни отдыха) начисляются каждые N дней серии
FREEZE_EVERY_STREAK = 7

