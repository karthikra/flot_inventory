import json

import anthropic

from app.config import settings


class ValueEstimator:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def estimate_value(self, name: str, description: str, category: str, condition: str | None = None) -> dict:
        """Estimate replacement value for an item using LLM."""
        condition_text = f" in {condition} condition" if condition else ""
        prompt = f"""Estimate the replacement value in USD for this household item{condition_text}.

Item: {name}
Description: {description}
Category: {category}

Return ONLY a JSON object:
{{"low": <number>, "mid": <number>, "high": <number>, "currency": "USD", "reasoning": "<brief explanation>"}}

Be realistic — use typical retail/secondhand prices."""

        response = await self.client.messages.create(
            model=settings.vision_model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(text)
            return data
        except (json.JSONDecodeError, ValueError):
            return {"low": None, "mid": None, "high": None, "currency": "USD", "reasoning": "Could not estimate"}
