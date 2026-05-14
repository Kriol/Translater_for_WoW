from dataclasses import dataclass


@dataclass
class ManualTranslationTask:
    request_id: int
    text: str
