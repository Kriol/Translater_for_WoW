import os


API_URL = os.getenv("WOW_TRANSLATOR_API_URL", "http://127.0.0.1:1234/v1/chat/completions")
MODEL_NAME = os.getenv("WOW_TRANSLATOR_MODEL", "qwen/qwen3.5-9b")
CAPTURE_INTERVAL_SECONDS = 1.2
QUEUE_POLL_INTERVAL_MS = 100
STATUS_RESET_DELAY_MS = 4000
MIN_TEXT_LENGTH = 5
REQUEST_TIMEOUT = (5, 45)
TRANSLATION_COOLDOWN_SECONDS = 2.0   # lowered from 3.0: catch faster-scrolling chat
SIMILARITY_THRESHOLD = 0.82          # lowered from 0.9: detect partial chat updates
WINDOW_GEOMETRY = "800x520+400+500"
OVERLAY_GEOMETRY = "500x150+600+750"

SYSTEM_PROMPT = (
    "Ты переводчик чата World of Warcraft. "
    "OCR-текст может содержать одну или несколько склеенных строк чата без правильных переносов. "
    "Восстанавливай границы сообщений по шаблонам начала строки.\n\n"
    "Примеры входа → выхода:\n"
    "[Gebs] says: Hello → [Gebs] говорит: Привет\n"
    "[Gebs] has come online. → [Gebs] вошёл в игру.\n"
    "Mupke has gone offline. → Mupke вышел из игры.\n"
    "You receive item: [Void Crystal]. → Вы получили предмет: [Void Crystal].\n"
    "Quest accepted: Wanted: Rift Lords → Задание принято: Разыскивается: Властелины разлома.\n"
    "You have learned a new spell: Fireball. → Вы изучили новое заклинание: Огненный шар.\n\n"
    "Правила:\n"
    "1. КАЖДОЕ сообщение — на ОТДЕЛЬНОЙ строке (\\n между ними, не точка).\n"
    "2. Сохраняй формат каждой строки как отдельное чат-сообщение.\n"
    "3. Переводи ВСЁ на русский язык, не трогай имена персонажей в [скобках].\n"
    "4. Если сообщение уже на русском, только исправь OCR-ошибки.\n"
    "5. Если весь входной текст — мусор (случайные символы, нечитаемо) — верни только: SKIP\n"
    "6. Никаких пояснений. Только готовые строки чата."
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
