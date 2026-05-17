import os


API_URL = os.getenv("WOW_TRANSLATOR_API_URL", "http://127.0.0.1:1234/v1/chat/completions")
MODEL_NAME = os.getenv("WOW_TRANSLATOR_MODEL", "qwen/qwen3.5-9b")
CAPTURE_INTERVAL_SECONDS = 0.5
QUEUE_POLL_INTERVAL_MS = 100
STATUS_RESET_DELAY_MS = 4000
MIN_TEXT_LENGTH = 5
REQUEST_TIMEOUT = (5, 45)
TRANSLATION_COOLDOWN_SECONDS = 1.0   # lowered from 2.0: make translation more responsive
SIMILARITY_THRESHOLD = 0.82          # lowered from 0.9: detect partial chat updates
WINDOW_GEOMETRY = "800x520+400+500"
OVERLAY_GEOMETRY = "500x150+600+750"

SYSTEM_PROMPT = (
    "Ты профессиональный переводчик игрового чата World of Warcraft. "
    "Твоя задача — точно перевести каждую строку чата на русский язык, строго сохраняя её оригинальную структуру.\n\n"
    "Примеры входа → выхода:\n"
    "[Party Leader] [Nickezy]: dont u have better xd → [Лидер группы] [Nickezy]: разве у тебя нет получше хд\n"
    "[Party] [Corvin]: ty → [Группа] [Corvin]: спс\n"
    "[Nickezy]: gg → [Nickezy]: гг\n"
    "[Gebs]: gl → [Gebs]: удачи\n"
    "can u inv? → можешь инвайтнуть?\n"
    "123 → нужен суммон\n"
    "[Party] [Corvin]: loads of stam → [Группа] [Corvin]: куча выносливости\n\n"
    "Справочник сленга для контекста:\n"
    "- 123 = просьба о суммоне\n"
    "- gg = хорошая игра\n"
    "- gl/hf = удачи и фана\n"
    "- ty/thx = спасибо\n"
    "- mb = мой косяк\n"
    "- inc = идут (враги)\n"
    "- oom = нет маны\n"
    "- zug zug = туннелить цель / игнорить тактику\n"
    "- lock in = собрались / фокус\n"
    "- ate = сделал идеально / красава\n"
    "- cya = увидимся / пока\n"
    "- can = могу / можем / можешь\n"
    "- u = ты / тебе\n"
    "- inv = инвайт / пригласи в группу\n\n"
    "You receive item: [Void Crystal]. → Вы получили предмет: [Void Crystal].\n\n"
    "КРИТИЧЕСКИЕ ПРАВИЛА:\n"
    "1. СТРОГО сохраняй структуру и ТЕГ КАНАЛА (если есть). Ничего не удаляй!\n"
    "2. Переводи названия каналов: [Party] → [Группа], [Party Leader] → [Лидер группы], [Raid] → [Рейд], [Guild] → [Гильдия].\n"
    "3. Имена персонажей в [скобках] НЕ ПЕРЕВОДИ (оставляй как есть).\n"
    "4. НЕ ПРОПУСКАЙ и НЕ ОБЪЕДИНЯЙ строки! Если на входе 10 строк (даже коротких, вроде 'ty' или 'gg'), на выходе должно быть ровно 10 переведенных строк.\n"
    "5. Если весь входной текст — мусор (случайные символы) — верни только слово: SKIP\n"
    "6. Никаких лишних слов, комментариев или пояснений. Только готовые строки чата."
)

CYRILLIC_TO_LATIN = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "Т": "T",
        "Х": "X",
        "У": "Y",
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "к": "k",
        "м": "m",
        "т": "t",
        "в": "b",
        "н": "h",
        "ј": "j",
        "і": "i",
        "І": "I",
    }
)
