from pydantic import BaseModel


class ProductSearchResult(BaseModel):
    title: str
    price: float | None = None
    source: str | None = None  # "Amazon", "Best Buy", etc.
    url: str | None = None
    thumbnail_url: str | None = None
    dimensions: dict | None = None  # {width_cm, height_cm, depth_cm}
    brand: str | None = None
    model_number: str | None = None
    specs: dict | None = None  # arbitrary key-value specs
