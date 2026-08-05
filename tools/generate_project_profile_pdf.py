#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import textwrap


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT = 54
TOP = 72
BOTTOM = 64
FONT_SIZE = 11
LEADING = 16
MAX_CHARS = 88


def escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def parse_markdown(md_text: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line:
            items.append(("blank", ""))
        elif line.startswith("# "):
            items.append(("h1", line[2:].strip()))
        elif line.startswith("## "):
            items.append(("h2", line[3:].strip()))
        elif line.startswith("### "):
            items.append(("h3", line[4:].strip()))
        elif line.startswith("- "):
            items.append(("bullet", line[2:].strip()))
        elif line[:2].isdigit() and line[1:3] == ". ":
            items.append(("number", line))
        else:
            items.append(("para", line))
    return items


def wrap_items(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    wrapped: list[tuple[str, str]] = []
    for kind, text in items:
        if kind == "blank":
            wrapped.append((kind, text))
            continue

        prefix = ""
        width = MAX_CHARS
        if kind == "bullet":
            prefix = "- "
            width = MAX_CHARS - len(prefix)
        elif kind == "number":
            split = text.split(". ", 1)
            prefix = split[0] + ". "
            text = split[1] if len(split) > 1 else text
            width = MAX_CHARS - len(prefix)

        lines = textwrap.wrap(text, width=width) or [""]
        for index, line in enumerate(lines):
            if kind in {"bullet", "number"}:
                wrapped.append((kind, (prefix if index == 0 else " " * len(prefix)) + line))
            else:
                wrapped.append((kind, line))
        if kind in {"h1", "h2", "h3"}:
            wrapped.append(("blank", ""))
    return wrapped


def paginate(lines: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    pages: list[list[tuple[str, str]]] = [[]]
    y = PAGE_HEIGHT - TOP
    for line in lines:
        required = LEADING
        if y - required < BOTTOM:
            pages.append([])
            y = PAGE_HEIGHT - TOP
        pages[-1].append(line)
        y -= required
    return pages


def line_font(kind: str) -> tuple[str, int]:
    if kind == "h1":
        return ("F2", 20)
    if kind == "h2":
        return ("F2", 15)
    if kind == "h3":
        return ("F2", 12)
    return ("F1", FONT_SIZE)


def build_stream(page_lines: list[tuple[str, str]], page_number: int, total_pages: int) -> str:
    y = PAGE_HEIGHT - TOP
    parts: list[str] = []

    parts.append("BT /F2 10 Tf 54 812 Td (Video Voice Translator - Track 1 Project Profile) Tj ET")
    parts.append(f"BT /F1 9 Tf 500 22 Td (Page {page_number} / {total_pages}) Tj ET")

    for kind, text in page_lines:
        if kind == "blank":
            y -= LEADING
            continue

        font, size = line_font(kind)
        safe_text = escape_pdf_text(text)
        parts.append(f"BT /{font} {size} Tf {LEFT} {y} Td ({safe_text}) Tj ET")
        y -= LEADING

    return "\n".join(parts)


def build_pdf(streams: list[str]) -> bytes:
    objects: list[bytes] = []

    def add_object(body: str | bytes) -> int:
        if isinstance(body, str):
            body = body.encode("latin-1", "replace")
        objects.append(body)
        return len(objects)

    font1 = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font2 = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_ids = []
    content_ids = []

    for stream in streams:
        data = stream.encode("latin-1", "replace")
        content_id = add_object(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
        content_ids.append(content_id)
        page_ids.append(0)

    kids_placeholder_index = len(objects) + 1
    pages_id = add_object("<< /Type /Pages /Kids [] /Count 0 >>")

    for i, content_id in enumerate(content_ids):
        page_obj = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        page_ids[i] = add_object(page_obj)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [ {kids} ] /Count {len(page_ids)} >>".encode("latin-1")

    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("latin-1"))
        out.extend(body)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(out)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "docs" / "PROJECT_PROFILE_TRACK1_EN.md"
    target = repo_root / "deliverables" / "track1-project-profile.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)

    items = parse_markdown(source.read_text(encoding="utf-8"))
    wrapped = wrap_items(items)
    pages = paginate(wrapped)
    streams = [build_stream(page, i + 1, len(pages)) for i, page in enumerate(pages)]
    target.write_bytes(build_pdf(streams))
    print(target)


if __name__ == "__main__":
    main()
