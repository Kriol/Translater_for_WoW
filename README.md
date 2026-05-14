# WoW Chat Translator

A real-time screen-capture translator designed specifically for World of Warcraft. It captures the chat area, performs OCR, and translates messages using LLMs (Local or Gemini) or Google Translate.

![Preview](https://via.placeholder.com/800x450.png?text=WoW+Chat+Translator+Overlay+Preview) *Replace with a real screenshot later*

## Features

- **Real-time OCR**: Uses Windows WinRT OCR for high performance and accuracy.
- **Multi-engine Translation**: 
  - **Local LLM**: Supports OpenAI-compatible APIs (LM Studio, Ollama).
  - **Gemini API**: Native support for Google Gemini 1.5/2.0/3.0 models.
  - **Google Translate**: Reliable fallback for zero-config use.
- **Click-Through Overlay**: A transparent overlay that captures text without blocking your game clicks or scrolling.
- **Manual Translation**: A built-in tool to translate your Russian text to English and copy it to the clipboard instantly for in-game replies.
- **Auto-Fixing**: Corrects common OCR errors (like Cyrillic/Latin character confusion in player names).

## Requirements

- **OS**: Windows 10/11 (WinRT OCR is Windows-only).
- **Language Packs**: Ensure the language you are translating FROM (e.g., English/Russian) is installed in Windows Language Settings.
- **Python**: 3.10 or higher.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/Translater_for_WoW.git
   cd Translater_for_WoW
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file (optional, for Gemini):
   ```env
   GEMINI_API_KEY=your_key_here
   ```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```
2. **SET REGION**: Click the button and drag the red frame over your WoW chat window.
3. **LOCK**: Click the Lock button to make the frame "ghost-like" (click-through). This allows you to interact with the game chat underneath while translating.
4. **Manual Input**: Type Russian text in the bottom field and press **Enter**. The translation will be copied to your clipboard—just press `Ctrl+V` in the game.

## Configuration

Settings are located in `config.py`:
- `CAPTURE_INTERVAL_SECONDS`: How often to scan the screen (default: 1.2s).
- `MODEL_NAME`: The name of your local LLM model.
- `API_URL`: Your local LLM endpoint (default: LM Studio).

## How to Build EXE

If you want to create a standalone executable for yourself or friends:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Run the build using the provided `.spec` file:
   ```bash
   pyinstaller --noconfirm WoW_Translator.spec
   ```
3. Your EXE will be in the `dist/` folder.

## License

MIT License. Feel free to use and modify.
