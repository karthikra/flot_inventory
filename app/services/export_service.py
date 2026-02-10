import csv
import io
import json
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from app.models.book import Book
from app.models.item import Item


class ExportService:
    def export_csv(self, items: list[Item], rooms: dict[int, str]) -> str:
        """Generate CSV string of inventory."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Name", "Description", "Category", "Room", "Condition",
            "Status", "Estimated Value", "Type", "Book Title", "Book Author",
            "ISBN", "Created At",
        ])
        for item in items:
            room_name = rooms.get(item.room_id, "Unknown")
            title = item.title if isinstance(item, Book) else ""
            author = item.author if isinstance(item, Book) else ""
            isbn = item.isbn if isinstance(item, Book) else ""
            writer.writerow([
                item.id, item.name, item.description or "", item.category,
                room_name, item.condition or "", item.status or "",
                item.estimated_value or "", item.type, title, author, isbn,
                item.created_at.isoformat() if item.created_at else "",
            ])
        return output.getvalue()

    def export_json(self, items: list[Item], rooms: dict[int, str]) -> str:
        """Generate JSON string of inventory."""
        data = []
        for item in items:
            entry = {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "room": rooms.get(item.room_id, "Unknown"),
                "condition": item.condition,
                "status": item.status,
                "estimated_value": item.estimated_value,
                "type": item.type,
                "image_path": item.image_path,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            if isinstance(item, Book):
                entry.update({
                    "book_title": item.title,
                    "book_author": item.author,
                    "isbn": item.isbn,
                    "publisher": item.publisher,
                    "genre": item.genre,
                    "page_count": item.page_count,
                    "year_published": item.year_published,
                })
            data.append(entry)
        return json.dumps(data, indent=2)

    def export_pdf(
        self,
        items: list[Item],
        rooms: dict[int, str],
        title: str = "Home Inventory Report",
        insurance_mode: bool = False,
    ) -> bytes:
        """Generate PDF report of inventory."""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # title
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)

        if insurance_mode:
            total_value = sum(item.estimated_value or 0 for item in items)
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, f"Total Estimated Value: ${total_value:,.2f}", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(5)

        # group by room
        by_room: dict[str, list[Item]] = {}
        for item in items:
            room_name = rooms.get(item.room_id, "Unknown")
            by_room.setdefault(room_name, []).append(item)

        for room_name, room_items in sorted(by_room.items()):
            pdf.set_font("Helvetica", "B", 14)
            room_value = sum(i.estimated_value or 0 for i in room_items)
            pdf.cell(0, 10, f"{room_name} ({len(room_items)} items — ${room_value:,.2f})", new_x="LMARGIN", new_y="NEXT")
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)

            for item in room_items:
                self._add_item_to_pdf(pdf, item, insurance_mode)

            pdf.ln(5)

        return bytes(pdf.output())

    def _add_item_to_pdf(self, pdf: FPDF, item: Item, insurance_mode: bool) -> None:
        # item image if available
        if item.thumbnail_path and Path(item.thumbnail_path).exists():
            try:
                pdf.image(item.thumbnail_path, w=30, h=30)
                pdf.set_xy(pdf.get_x() + 35, pdf.get_y() - 30)
            except Exception:
                pass

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, item.name, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "", 9)
        if item.description:
            pdf.multi_cell(0, 5, item.description[:200])

        details = []
        if item.category:
            details.append(f"Category: {item.category}")
        if item.condition:
            details.append(f"Condition: {item.condition}")
        if insurance_mode and item.estimated_value:
            details.append(f"Value: ${item.estimated_value:,.2f}")
        if isinstance(item, Book):
            if item.title:
                details.append(f"Title: {item.title}")
            if item.author:
                details.append(f"Author: {item.author}")

        if details:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 5, " | ".join(details), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(4)
