"""LLM 基类"""
from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        ...

    @abstractmethod
    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
        ...
