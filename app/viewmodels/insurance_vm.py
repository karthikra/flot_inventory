from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.repositories.item_repo import ItemRepository
from app.repositories.room_repo import RoomRepository


@dataclass
class InsuranceViewModel:
    total_value: float = 0.0
    total_replacement: float = 0.0
    total_items: int = 0
    by_room: list[dict] = field(default_factory=list)
    by_category: list[dict] = field(default_factory=list)
    high_value_items: list[dict] = field(default_factory=list)
    missing_data_items: list[dict] = field(default_factory=list)
    rooms: list = field(default_factory=list)

    @classmethod
    async def load(cls, session: AsyncSession) -> "InsuranceViewModel":
        item_repo = ItemRepository(session)
        room_repo = RoomRepository(session)

        items = await item_repo.get_all(limit=10000)
        rooms = await room_repo.get_all()
        room_map = {r.id: r.name for r in rooms}

        # Calculate totals — prefer replacement_cost, fall back to estimated_value
        total_value = 0.0
        total_replacement = 0.0
        room_values: dict[str, dict] = {}
        cat_values: dict[str, dict] = {}
        high_value = []
        missing_data = []

        for item in items:
            value = item.replacement_cost or item.estimated_value or 0.0
            total_value += value
            if item.replacement_cost:
                total_replacement += item.replacement_cost

            room_name = room_map.get(item.room_id, "Unknown")

            # By room
            if room_name not in room_values:
                room_values[room_name] = {"name": room_name, "count": 0, "value": 0.0}
            room_values[room_name]["count"] += 1
            room_values[room_name]["value"] += value

            # By category
            cat = item.category or "other"
            if cat not in cat_values:
                cat_values[cat] = {"name": cat, "count": 0, "value": 0.0}
            cat_values[cat]["count"] += 1
            cat_values[cat]["value"] += value

            # High value items (>$500)
            if value > 500:
                high_value.append(_item_summary(item, room_name, value))

            # Missing data check
            missing = _check_missing(item)
            if missing:
                missing_data.append({
                    "id": item.id,
                    "name": item.name,
                    "room": room_name,
                    "missing": missing,
                })

        by_room = sorted(room_values.values(), key=lambda x: x["value"], reverse=True)
        by_category = sorted(cat_values.values(), key=lambda x: x["value"], reverse=True)
        high_value.sort(key=lambda x: x["value"], reverse=True)

        return cls(
            total_value=total_value,
            total_replacement=total_replacement,
            total_items=len(items),
            by_room=by_room,
            by_category=by_category,
            high_value_items=high_value,
            missing_data_items=missing_data,
            rooms=rooms,
        )


def _item_summary(item: Item, room_name: str, value: float) -> dict:
    complete = True
    if not item.replacement_cost:
        complete = False
    if not item.image_path:
        complete = False
    if item.category == "electronics" and not item.serial_number:
        complete = False
    return {
        "id": item.id,
        "name": item.name,
        "room": room_name,
        "value": value,
        "has_photo": bool(item.image_path),
        "has_serial": bool(item.serial_number),
        "has_replacement_cost": bool(item.replacement_cost),
        "documentation_complete": complete,
    }


def _check_missing(item: Item) -> list[str]:
    missing = []
    if not item.replacement_cost and not item.estimated_value:
        missing.append("no value")
    if not item.image_path:
        missing.append("no photo")
    if item.category == "electronics" and not item.serial_number:
        missing.append("no serial number")
    if not item.replacement_cost:
        missing.append("no replacement cost")
    return missing
