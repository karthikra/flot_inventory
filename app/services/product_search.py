import base64
import json
import logging
from pathlib import Path

import httpx

from app.config import settings
from app.schemas.product_search import ProductSearchResult

logger = logging.getLogger(__name__)


class ProductSearchService:
    """Search for product pricing and specs via SerpAPI or LLM fallback."""

    async def search_product(
        self, query: str, category: str = "", brand: str = ""
    ) -> list[ProductSearchResult]:
        """Search for a product by name. Uses SerpAPI if configured, else LLM fallback."""
        search_query = query
        if brand:
            search_query = f"{brand} {query}"

        if settings.serpapi_api_key:
            return await self._search_serpapi(search_query, category)
        return await self._search_llm_fallback(search_query, category)

    async def visual_search(self, image_path: str) -> list[ProductSearchResult]:
        """Reverse image search via SerpAPI Google Lens."""
        if not settings.serpapi_api_key:
            return []
        return await self._visual_search_serpapi(image_path)

    async def _search_serpapi(
        self, query: str, category: str = ""
    ) -> list[ProductSearchResult]:
        """Search Google Shopping via SerpAPI."""
        params = {
            "engine": "google_shopping",
            "q": query,
            "api_key": settings.serpapi_api_key,
            "num": 5,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://serpapi.com/search", params=params
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("shopping_results", [])[:5]:
                # Parse price string like "$299.99" to float
                price = None
                price_str = item.get("extracted_price")
                if price_str is not None:
                    try:
                        price = float(price_str)
                    except (ValueError, TypeError):
                        pass

                # Extract specs if available
                specs = {}
                for spec in item.get("extensions", []):
                    if isinstance(spec, str) and ":" in spec:
                        k, _, v = spec.partition(":")
                        specs[k.strip()] = v.strip()

                results.append(ProductSearchResult(
                    title=item.get("title", ""),
                    price=price,
                    source=item.get("source", ""),
                    url=item.get("link"),
                    thumbnail_url=item.get("thumbnail"),
                    brand=item.get("brand"),
                    specs=specs if specs else None,
                ))

            logger.info("SerpAPI returned %d results for: %s", len(results), query)
            return results

        except Exception:
            logger.exception("SerpAPI search failed for: %s", query)
            return await self._search_llm_fallback(query, category)

    async def _visual_search_serpapi(self, image_path: str) -> list[ProductSearchResult]:
        """Visual search via SerpAPI Google Lens endpoint."""
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
        ext = Path(image_path).suffix.lstrip(".") or "jpeg"
        mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"

        params = {
            "engine": "google_lens",
            "api_key": settings.serpapi_api_key,
            "url": f"data:{mime};base64,{image_b64}",
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://serpapi.com/search", params=params
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for match in data.get("visual_matches", [])[:5]:
                price = None
                price_info = match.get("price", {})
                if isinstance(price_info, dict):
                    price_str = price_info.get("extracted_value")
                    if price_str is not None:
                        try:
                            price = float(price_str)
                        except (ValueError, TypeError):
                            pass

                results.append(ProductSearchResult(
                    title=match.get("title", ""),
                    price=price,
                    source=match.get("source", ""),
                    url=match.get("link"),
                    thumbnail_url=match.get("thumbnail"),
                ))

            logger.info("SerpAPI Lens returned %d visual matches", len(results))
            return results

        except Exception:
            logger.exception("SerpAPI visual search failed")
            return []

    async def _search_llm_fallback(
        self, query: str, category: str = ""
    ) -> list[ProductSearchResult]:
        """Use Qwen3-VL via configured backend to estimate product info from training data."""
        prompt = f"""You are a product research assistant. For the following item, estimate typical retail information.

Item: {query}
Category: {category}

Return ONLY a JSON array of 1-3 likely product matches with these fields:
- "title": full product name
- "price": typical retail price in USD (number)
- "source": likely retailer (e.g. "Amazon", "Target")
- "brand": manufacturer
- "model_number": model if known
- "specs": object with relevant specs

Example: [{{"title": "Sony WH-1000XM5", "price": 299.99, "source": "Amazon", "brand": "Sony", "model_number": "WH-1000XM5", "specs": {{"weight": "250g", "battery": "30 hours"}}}}]"""

        try:
            if settings.vision_backend == "openai":
                return await self._llm_fallback_openai(prompt)
            return await self._llm_fallback_ollama(prompt)
        except Exception:
            logger.exception("LLM product search fallback failed")
            return []

    async def _llm_fallback_ollama(self, prompt: str) -> list[ProductSearchResult]:
        payload = {
            "model": settings.ollama_vision_model,
            "prompt": f"/nothink\n{prompt}",
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=settings.qwen_timeout) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "")

        return self._parse_llm_results(text)

    async def _llm_fallback_openai(self, prompt: str) -> list[ProductSearchResult]:
        payload = {
            "model": settings.openai_vision_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.1,
        }

        headers = {"Content-Type": "application/json"}
        if settings.openai_vision_api_key:
            headers["Authorization"] = f"Bearer {settings.openai_vision_api_key}"

        async with httpx.AsyncClient(timeout=settings.qwen_timeout) as client:
            resp = await client.post(
                f"{settings.openai_vision_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]

        return self._parse_llm_results(text)

    def _parse_llm_results(self, text: str) -> list[ProductSearchResult]:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        text = text.replace(": True", ": true").replace(": False", ": false").replace(": None", ": null")

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end > start:
                try:
                    data = json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    return []
            else:
                return []

        if not isinstance(data, list):
            data = [data]

        results = []
        for item in data[:5]:
            if not isinstance(item, dict):
                continue
            results.append(ProductSearchResult(
                title=item.get("title", "Unknown"),
                price=item.get("price"),
                source=item.get("source"),
                brand=item.get("brand"),
                model_number=item.get("model_number"),
                specs=item.get("specs"),
            ))

        return results
