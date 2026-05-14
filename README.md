# WoW Chat Translator

[English](#wow-chat-translator) | [Русский](#переводчик-чата-wow)

A real-time screen-capture translator designed specifically for World of Warcraft. It captures the chat area, performs OCR, and translates messages using LLMs (Local or Gemini) or Google Translate.

## Features

- **Real-time OCR**: Uses Windows WinRT OCR for high performance and accuracy.
- **Multi-engine Translation**: 
  - **Local LLM**: Supports OpenAI-compatible APIs (LM Studio, Ollama).
  - **Gemini API**: Native support for Google Gemini models.
  - **Google Translate**: Reliable fallback.
- **Click-Through Overlay**: A transparent overlay that captures text without blocking your game clicks or scrolling.
- **Manual Translation**: Translate Russian text to English and copy it to the clipboard instantly for in-game replies.
- **Auto-Fixing**: Corrects common OCR errors.

## Requirements

- **OS**: Windows 10/11.
- **Language Packs**: Install the source language (English/Russian) in Windows.
- **Python**: 3.10+.

## Installation

1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. (Optional) Enter your `GEMINI_API_KEY` directly in the application's **KEY** field or add it to a `.env` file.

## Usage

1. Run `python main.py`.
2. **SET REGION**: Drag the red frame over your chat.
3. **LOCK**: Make the frame click-through.
4. **Manual Input**: Type Russian, press Enter, then `Ctrl+V` in WoW.

> [!TIP]
> **For best OCR quality**: Set your in-game WoW chat window background to **black** and **non-transparent** (100% opaque).

## How to Build EXE

`pyinstaller --noconfirm WoW_Translator.spec`

---

# Переводчик чата WoW

Экранный переводчик чата в реальном времени, созданный специально для World of Warcraft. Захватывает область чата, распознает текст через OCR и переводит его с помощью нейросетей (Локальных или Gemini) или Google Translate.

## Возможности

- **OCR в реальном времени**: Использует быстрый Windows WinRT OCR.
- **Гибкий перевод**:
  - **Локальные LLM**: Поддержка LM Studio, Ollama и других.
  - **Gemini API**: Прямая поддержка моделей Google Gemini.
  - **Google Translate**: Надежный запасной вариант.
- **"Призрачный" оверлей**: Прозрачная рамка, которая не мешает кликам и скроллу внутри игры.
- **Обратный перевод**: Ввод текста на русском -> автоматический перевод на английский -> копирование в буфер обмена для быстрых ответов.
- **Auto-Fixing**: Исправляет ошибки OCR (например, путаницу кириллических и латинских букв в никах).

## Требования

- **ОС**: Windows 10/11.
- **Языковые пакеты**: Убедитесь, что в системе установлены пакеты для языков, которые нужно распознавать (English/Russian).
- **Python**: 3.10 или выше.

## Инструкция

1. Скачайте проект или склонируйте репозиторий.
2. Установите зависимости: `pip install -r requirements.txt`
3. (Опционально) Введите ваш `GEMINI_API_KEY` прямо в поле **KEY** в приложении или добавьте его в файл `.env`.

## Как пользоваться

1. Запустите `python main.py`.
2. **SET REGION**: Нажмите кнопку и растяните красную рамку над чатом игры.
3. **LOCK**: Нажмите Lock, чтобы рамка стала "прозрачной" для мышки. Теперь вы сможете кликать и скроллить чат WoW прямо сквозь неё.
4. **Ручной ввод**: Пишите в нижнем поле на русском и жмите **Enter**. Перевод сразу окажется в буфере обмена — просто нажмите `Ctrl+V` в игре.

> [!TIP]
> **Для лучшего качества распознавания**: Установите фон чата в самой игре на **черный** и полностью **уберите прозрачность** (сделайте его непрозрачным).

## Как собрать EXE

Если вы хотите создать готовый файл для запуска:
1. `pip install pyinstaller`
2. `pyinstaller --noconfirm WoW_Translator.spec`

Результат будет в папке `dist/`.

## Лицензия

MIT License.
