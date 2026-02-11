import json
from datetime import date

import anthropic

from app.config import settings

# Annual depreciation rates by category
DEPRECIATION_RATES: dict[str, float] = {
    "electronics": 0.25,
    "appliances": 0.15,
    "furniture": 0.10,
    "kitchenware": 0.10,
    "tools": 0.10,
    "clothing": 0.20,
    "sports": 0.15,
    "toys": 0.20,
    "decor": 0.08,
    "books": 0.05,
    "musical_instruments": 0.08,
    "other": 0.12,
}


def calculate_depreciation(
    replacement_cost: float,
    purchase_date: str | None,
    category: str = "other",
) -> dict:
    """Calculate actual cash value (ACV) using straight-line depreciation.

    Returns dict with: actual_cash_value, depreciation_rate, age_years, total_depreciation
    """
    rate = DEPRECIATION_RATES.get(category, 0.12)

    if not purchase_date or not replacement_cost:
        return {
            "actual_cash_value": replacement_cost,
            "depreciation_rate": rate,
            "age_years": 0,
            "total_depreciation": 0.0,
        }

    try:
        purchase = date.fromisoformat(purchase_date)
        age_years = (date.today() - purchase).days / 365.25
    except (ValueError, TypeError):
        age_years = 0

    # ACV = replacement_cost * (1 - rate) ^ age_years
    # Floor at 10% of replacement cost (items retain some salvage value)
    acv = replacement_cost * ((1 - rate) ** age_years)
    acv = max(acv, replacement_cost * 0.10)
    total_dep = replacement_cost - acv

    return {
        "actual_cash_value": round(acv, 2),
        "depreciation_rate": rate,
        "age_years": round(age_years, 1),
        "total_depreciation": round(total_dep, 2),
    }


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
