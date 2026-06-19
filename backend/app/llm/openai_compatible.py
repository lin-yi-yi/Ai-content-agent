"""OpenAI 兼容客户端"""
import json
import re
import time
from typing import Optional

from openai import OpenAI

from app.llm.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    def __init__(self, api_key: str, base_url: str, model: str, provider: str = "unknown"):
        self.provider = provider
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        start = time.time()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency = int((time.time() - start) * 1000)
            content = resp.choices[0].message.content or ""
            self._log_run("chat", system_prompt + user_prompt, content, True, latency)
            return content
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            self._log_run("chat", system_prompt + user_prompt, "", False, latency, str(e))
            raise

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
        prompt_suffix = "\n\n请严格输出一个合法 JSON 对象，不要 Markdown，不要解释。"
        full_user_prompt = user_prompt + prompt_suffix
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response_format = "json_object" if attempt == 0 else "text"
                text = self.chat_with_format(system_prompt, full_user_prompt, temperature, response_format=response_format)
                return self._parse_json_object(text)
            except Exception as e:
                last_error = e
                if attempt == 0 and self._looks_like_response_format_error(e):
                    continue
                if attempt == 2:
                    break

                repair_prompt = (
                    "下面这段内容没有被解析成合法 JSON。请只返回修复后的 JSON 对象，"
                    "不要添加解释，不要使用 Markdown。\n\n"
                    f"原始内容：\n{locals().get('text', '')[:6000]}\n\n"
                    f"解析错误：{str(e)}"
                )
                try:
                    text = self.chat_with_format(
                        "你是 JSON 修复器，负责把文本修复为合法 JSON 对象。",
                        repair_prompt,
                        temperature=0,
                        response_format="text",
                    )
                    return self._parse_json_object(text)
                except Exception as repair_error:
                    last_error = repair_error

        raise last_error or ValueError("模型没有返回合法 JSON")

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', text)
            if not match:
                raise
            value = json.loads(match.group())
        if not isinstance(value, dict):
            raise ValueError("模型 JSON 输出必须是对象")
        return value

    @staticmethod
    def _looks_like_response_format_error(error: Exception) -> bool:
        message = str(error).lower()
        return "response_format" in message or "json_object" in message

    def chat_with_format(self, system_prompt: str, user_prompt: str,
                         temperature: float = 0.7, max_tokens: int = 4096,
                         response_format: str = "text") -> str:
        start = time.time()
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = self.client.chat.completions.create(**kwargs)
            latency = int((time.time() - start) * 1000)
            content = resp.choices[0].message.content or ""
            self._log_run("chat", system_prompt + user_prompt, content, True, latency)
            return content
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            self._log_run("chat", system_prompt + user_prompt, "", False, latency, str(e))
            raise

    def _log_run(self, task_type: str, input_text: str, output_text: str,
                 success: bool, latency_ms: int, error: str = ""):
        """写入 model_runs 表"""
        from app.db.session import SessionLocal
        from app.models.model_run import ModelRun
        try:
            db = SessionLocal()
            db.add(ModelRun(
                task_type=task_type,
                provider=self.provider,
                model_name=self.model,
                input_preview=input_text[:500],
                output_preview=output_text[:500],
                success=success,
                error_message=error or None,
                latency_ms=latency_ms,
            ))
            db.commit()
            db.close()
        except Exception:
            pass
