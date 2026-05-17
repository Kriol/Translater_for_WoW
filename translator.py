import requests
import logging
import re
from typing import cast, List, Optional
from deep_translator import GoogleTranslator
from google import genai

from config import REQUEST_TIMEOUT, SYSTEM_PROMPT

LOGGER = logging.getLogger("wow_translator")


class ReasoningOnlyModelError(ValueError):
    pass


class TranslatorClient:
    def __init__(self, api_url: str, model_name: str) -> None:
        self.api_url = api_url
        self.model_name = model_name
        self.session = requests.Session()
        # Fallback translators
        self.fallback_to_ru = GoogleTranslator(source='auto', target='ru')
        self.fallback_to_en = GoogleTranslator(source='ru', target='en')
        self.api_key: str = ""
        self.client = None  # type: ignore[assignment]
        self.gemini_model_id: str = "gemini-3-flash-preview"

    def _get_available_models(self) -> List[str]:
        """Get list of available Gemini models from API."""
        try:
            models_list = self.client.models.list()  # type: ignore[attr-defined]
            return [str(m.name) for m in models_list if m.name is not None]
        except Exception:
            return []

    def _select_best_model(self) -> str:
        """Select the best available Gemini model."""
        available = self._get_available_models()
        
        # Target Gemini 3 Flash series, ignore specific modalities
        g3_models = [
            m for m in available 
            if "gemini-3" in m and "flash" in m 
            and "image" not in m and "audio" not in m and "tts" not in m and "live" not in m
        ]
        
        if g3_models:
            # Prefer stable models over previews
            g3_models.sort(key=lambda x: ("preview" not in x, x), reverse=True)
            return g3_models[0]
        
        return "gemini-2.5-flash"  # Safe fallback

    def _init_client_if_needed(self) -> None:
        """Initialize Gemini client if API key is available."""
        if self.api_key and not self.client:
            try:
                self.client = genai.Client(api_key=self.api_key)  # type: ignore[assignment]
                
                # Dynamically determine the best Gemini model available
                best_model = self._select_best_model()
                self.gemini_model_id = best_model
                LOGGER.info(f"GenAI SDK configured with model: {self.gemini_model_id}")
            except Exception as e:
                LOGGER.error(f"Failed to configure GenAI SDK: {e}")
                self.client = None

    def set_api_key(self, key: str):
        if key and key != self.api_key:
            old_key = self.api_key
            self.api_key = key
            # Initialize client when API key is provided
            if not self.client:
                self._init_client_if_needed()
            # Reinitialize client if key changed (in case of model change)
            elif self.client and old_key != self.api_key:  # type: ignore[operator]
                try:
                    best_model = self._select_best_model()
                    self.gemini_model_id = best_model
                except Exception as e:
                    LOGGER.warning(f"Failed to dynamically query Gemini models with new key. ({e})")
                    self.gemini_model_id = "gemini-2.5-flash"
        elif not key:
            self.api_key = ""
            self.client = None

    def _ensure_client_is_initialized(self) -> bool:
        """Ensure the Gemini client is initialized and available."""
        if not self.client or not self.api_key:  # type: ignore[truthy]
            self._init_client_if_needed()
        return self.client is not None

    def build_payload(self, raw_text: str, *, force_no_think: bool) -> dict:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            "temperature": 0.0,
            "max_tokens": 300,
        }
        if force_no_think:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    def parse_response(self, data: dict) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LM Studio returned no choices.")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str):
            raise ValueError("LM Studio response does not contain text content.")
        if not content.strip():
            reasoning_content = message.get("reasoning_content", "")
            if isinstance(reasoning_content, str) and reasoning_content.strip():
                raise ReasoningOnlyModelError(
                    "Model returned reasoning_content but empty content."
                )
            raise ValueError("LM Studio returned an empty response.")

        return content.strip()

    def translate(self, raw_text: str) -> tuple[str, str]:
        # 1. Rules
        system_fix = self._rule_based_translate(raw_text)
        if system_fix:
            return system_fix, "Rules"

        # 2. Local LLM
        try:
            payload = self.build_payload(raw_text, force_no_think=True)
            response = self.session.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return self.parse_response(response.json()), "Local LLM"
        except Exception as e:
            # 3. Gemini Fallback (ensure client is initialized)
            if self._ensure_client_is_initialized():
                try:
                    resp = self.client.models.generate_content(  # type: ignore[attr-defined]
                        model=self.gemini_model_id,
                        contents=f"{SYSTEM_PROMPT}\n\nTranslate this:\n{raw_text}"
                    )
                    if resp and resp.text:
                        return resp.text.strip(), "Gemini"
                except Exception as ge:
                    if "429" in str(ge):
                        LOGGER.warning("Gemini API rate limit exceeded (429). Falling back...")
                    else:
                        LOGGER.warning(f"Gemini API failed: {ge}")

            # 4. Google Fallback
            try:
                return self.fallback_to_ru.translate(raw_text), "Google"
            except Exception as fe:
                LOGGER.error(f"Google fallback failed: {fe}")
                return f"[Error] {raw_text}", "Error"

    def _rule_based_translate(self, text: str) -> str | None:
        import re
        # [Name] has come online / gone offline
        online_match = re.match(r"^\[?([A-Za-zА-Яа-я0-9]+)\]?\s+has\s+come\s+online\.?$", text, re.I)
        if online_match:
            return f"[{online_match.group(1)}] вошел в игру."
        offline_match = re.match(r"^\[?([A-Za-zА-Яа-я0-9]+)\]?\s+has\s+gone\s+offline\.?$", text, re.I)
        if offline_match:
            return f"[{offline_match.group(1)}] вышел из игры."
        if "You are now AFK" in text:
            return "Вы теперь AFK."
        if "You are no longer AFK" in text:
            return "Вы больше не AFK."
        return None

    def translate_lines(self, lines: list[str]) -> tuple[str, str]:
        """Translate a list of chat messages and return them as formatted multiline string.
        
        Each message gets translated separately for proper formatting.
        Returns translation with each message on a new line.
        Splits by time format (HH:MM:SS) to preserve message boundaries.
        """
        if not lines:
            return "", "None"
        
        # Объединяем все строки в один текст для перевода
        combined = "\n".join(lines)
        translated, engine = self.translate(combined)
        
        # Разбиваем результат по времени (HH:MM:SS) чтобы сохранить границы сообщений
        pattern = r"(\d{2}:\d{2}:\d{2}\s+[^\[]+)"
        matches = list(re.finditer(pattern, translated))
        
        if not matches:
            # Если нет времени — просто делим по новой строке
            result_lines = translated.split("\n")
            formatted_lines = [line.strip() for line in result_lines if line.strip()]
            return "\n".join(formatted_lines), engine
        
        # Собираем сообщения начиная с первого вхождения времени
        result_lines = []
        for i, match in enumerate(matches):
            start = match.start()
            # Берём от начала совпадения до начала следующего (или конца строки)
            if i + 1 < len(matches):
                end = matches[i + 1].start()
            else:
                end = len(translated)
            
            line_text = translated[start:end].strip()
            if line_text:
                result_lines.append(line_text)
        
        return "\n".join(result_lines), engine

    def translate_manual_input(self, russian_text: str) -> tuple[str, str]:
        # 1. Local LLM
        try:
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": "Translate Russian to natural English for WoW chat."},
                    {"role": "user", "content": russian_text},
                ],
                "temperature": 0.3,
                "max_tokens": 250,
            }
            response = self.session.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return self.parse_response(response.json()), "Local LLM"
        except Exception:
            # 2. Gemini Fallback (ensure client is initialized)
            if self._ensure_client_is_initialized():
                try:
                    p = f"Translate Russian to natural English for WoW chat. Return ONLY translation.\n\nText: {russian_text}"
                    resp = self.client.models.generate_content(  # type: ignore[attr-defined]
                        model=self.gemini_model_id, contents=p
                    )
                    if resp and resp.text:
                        return resp.text.strip(), "Gemini"
                except Exception as ge:
                    if "429" in str(ge):
                        LOGGER.warning("Gemini API rate limit exceeded (429) during manual translation.")
                    else:
                        LOGGER.warning(f"Gemini manual translation failed: {ge}")

            # 3. Google Fallback
            try:
                return self.fallback_to_en.translate(russian_text), "Google"
            except Exception:
                return russian_text, "Error"

    def close(self) -> None:
        self.session.close()
        if self.client:
            # genai.Client doesn't have a close method, but we can clear resources
            self.client = None  # type: ignore[assignment]