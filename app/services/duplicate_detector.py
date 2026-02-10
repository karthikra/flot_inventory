from rapidfuzz import fuzz

from app.models.item import Item
from app.config import settings


class DuplicateDetector:
    def find_duplicates(self, new_name: str, new_description: str, existing_items: list[Item]) -> list[dict]:
        """Find potential duplicate items based on text similarity."""
        candidates = []
        threshold = settings.duplicate_text_threshold * 100  # rapidfuzz uses 0-100

        for item in existing_items:
            name_score = fuzz.ratio(new_name.lower(), item.name.lower())
            desc_score = fuzz.ratio(
                (new_description or "").lower(),
                (item.description or "").lower(),
            )
            # weighted: name matters more
            combined = (name_score * 0.7) + (desc_score * 0.3)

            if combined >= threshold:
                candidates.append({
                    "item": item,
                    "name_similarity": name_score / 100,
                    "description_similarity": desc_score / 100,
                    "combined_score": combined / 100,
                })

        candidates.sort(key=lambda x: x["combined_score"], reverse=True)
        return candidates[:5]
