from __future__ import annotations

import asyncio

from builder.config import Settings


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required")
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(settings.gemini_model)

    async def generate_json(self, prompt: str) -> str:
        return await asyncio.to_thread(self._generate, prompt, "application/json")

    async def generate_text(self, prompt: str) -> str:
        return await asyncio.to_thread(self._generate, prompt, "text/plain")

    def _generate(self, prompt: str, response_mime_type: str) -> str:
        response = self._model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "top_p": 0.9,
                "response_mime_type": response_mime_type,
            },
        )
        text = getattr(response, "text", "")
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return text.strip()

