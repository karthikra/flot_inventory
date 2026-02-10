from pathlib import Path

import httpx

from app.config import settings


class BookService:
    def __init__(self):
        self.base_url = settings.open_library_base_url

    async def lookup_isbn(self, isbn: str) -> dict | None:
        """Look up book metadata via Open Library API."""
        isbn = isbn.replace("-", "").strip()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/books.json",
                params={"bibkeys": f"ISBN:{isbn}", "format": "data", "jscmd": "data"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            key = f"ISBN:{isbn}"
            if key not in data:
                return None

            book = data[key]
            return {
                "title": book.get("title"),
                "author": ", ".join(a.get("name", "") for a in book.get("authors", [])),
                "publisher": ", ".join(p.get("name", "") for p in book.get("publishers", [])),
                "year_published": self._extract_year(book.get("publish_date", "")),
                "page_count": book.get("number_of_pages"),
                "cover_url": book.get("cover", {}).get("medium"),
                "subjects": [s.get("name", "") for s in book.get("subjects", [])[:5]],
            }

    async def search_books(self, title: str, author: str | None = None) -> list[dict]:
        """Search Open Library for books matching title/author."""
        params = {"title": title, "limit": 5}
        if author:
            params["author"] = author

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/search.json",
                params=params,
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            for doc in data.get("docs", [])[:5]:
                results.append({
                    "title": doc.get("title"),
                    "author": ", ".join(doc.get("author_name", [])[:3]),
                    "isbn": (doc.get("isbn", [None]) or [None])[0],
                    "year_published": doc.get("first_publish_year"),
                    "publisher": (doc.get("publisher", [""]) or [""])[0],
                    "cover_id": doc.get("cover_i"),
                })
            return results

    def scan_barcode(self, image_path: str) -> str | None:
        """Attempt to decode a barcode/ISBN from an image."""
        try:
            from pyzbar.pyzbar import decode
            from PIL import Image

            img = Image.open(image_path)
            barcodes = decode(img)
            for barcode in barcodes:
                data = barcode.data.decode("utf-8")
                # ISBN-13 starts with 978 or 979
                if data.isdigit() and len(data) in (10, 13):
                    return data
            return None
        except Exception:
            return None

    async def download_cover(self, cover_url: str, dest_dir: Path) -> str | None:
        """Download a book cover image."""
        if not cover_url:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(cover_url, timeout=10, follow_redirects=True)
                if resp.status_code != 200:
                    return None
                dest_dir.mkdir(parents=True, exist_ok=True)
                import uuid
                filename = f"cover_{uuid.uuid4().hex}.jpg"
                dest = dest_dir / filename
                dest.write_bytes(resp.content)
                return str(dest)
        except Exception:
            return None

    def _extract_year(self, date_str: str) -> int | None:
        if not date_str:
            return None
        import re
        match = re.search(r"\d{4}", date_str)
        return int(match.group()) if match else None
