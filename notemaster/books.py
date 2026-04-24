import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Optional
from notemaster.models import Highlight, HighlightColor

_STYLE_TO_COLOR: dict[int, HighlightColor] = {
    3: HighlightColor.YELLOW,
    1: HighlightColor.GREEN,
    2: HighlightColor.BLUE,
}

_ANNOTATION_GLOB = (
    "Library/Containers/com.apple.iBooksX/Data/Documents/AEAnnotation/AEAnnotation_*.sqlite"
)
_LIBRARY_GLOB = (
    "Library/Containers/com.apple.iBooksX/Data/Documents/BKLibrary/BKLibrary-*.sqlite"
)


def find_library_db() -> Optional[Path]:
    matches = list(Path.home().glob(_LIBRARY_GLOB))
    return matches[0] if matches else None


def find_annotation_db() -> Optional[Path]:
    matches = list(Path.home().glob(_ANNOTATION_GLOB))
    return matches[0] if matches else None


def list_apple_books(db_path: Optional[Path] = None) -> list[dict]:
    if db_path is None:
        db_path = find_library_db()
    if db_path is None:
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT ZASSETID, ZTITLE, ZAUTHOR FROM ZBKLIBRARYASSET "
        "WHERE ZASSETID IS NOT NULL AND ZTITLE IS NOT NULL ORDER BY ZTITLE"
    ).fetchall()
    conn.close()
    return [{"asset_id": r[0], "title": r[1], "author": r[2] or ""} for r in rows]


def _section_label_from_cfi(cfi: str) -> str:
    """Extract the deepest meaningful section id from an EPUB CFI string."""
    after_bang = cfi.split("!", 1)[1] if cfi and "!" in cfi else ""
    ids = re.findall(r"\[(ch_[^\]]+|sec_[^\]]+)\]", after_bang)
    if not ids:
        return "other"
    raw = ids[-1]
    # humanize: strip common prefixes, replace underscores
    label = re.sub(r"^(sec_|ch_)", "", raw)
    # strip book-specific prefixes like "introduction_"
    label = re.sub(r"^[a-z]+_", "", label) if "_" in label else label
    return label.replace("_", " ").strip() or raw


def get_highlight_sections(
    asset_id: str,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Return sections (with highlight counts) available for a given book asset."""
    if db_path is None:
        db_path = find_annotation_db()
    if db_path is None:
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT ZANNOTATIONLOCATION FROM ZAEANNOTATION "
        "WHERE ZANNOTATIONASSETID = ? AND ZANNOTATIONDELETED = 0 "
        "AND ZANNOTATIONSELECTEDTEXT IS NOT NULL",
        (asset_id,),
    ).fetchall()
    conn.close()

    counts: Counter = Counter()
    section_ids: dict[str, str] = {}  # label -> raw section_id
    for (loc,) in rows:
        after = loc.split("!", 1)[1] if loc and "!" in loc else ""
        ids = re.findall(r"\[(ch_[^\]]+|sec_[^\]]+)\]", after)
        section_id = ids[-1] if ids else "other"
        label = _section_label_from_cfi(loc)
        counts[label] += 1
        section_ids[label] = section_id

    return [
        {"section_id": section_ids[label], "label": label, "count": count}
        for label, count in sorted(counts.items(), key=lambda x: -x[1])
    ]


def get_highlights(
    asset_id: str,
    book_id: str,
    book_title: str,
    db_path: Optional[Path] = None,
    sections: Optional[list[str]] = None,
) -> list[Highlight]:
    if db_path is None:
        db_path = find_annotation_db()
    if db_path is None:
        return []

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT ZANNOTATIONUUID, ZANNOTATIONSELECTEDTEXT, ZANNOTATIONSTYLE, ZANNOTATIONLOCATION "
        "FROM ZAEANNOTATION "
        "WHERE ZANNOTATIONASSETID = ? AND ZANNOTATIONDELETED = 0 "
        "AND ZANNOTATIONSELECTEDTEXT IS NOT NULL",
        (asset_id,),
    ).fetchall()
    conn.close()

    highlights = []
    for uuid, text, style, loc in rows:
        color = _STYLE_TO_COLOR.get(style)
        if color is None:
            continue
        if sections is not None:
            label = _section_label_from_cfi(loc or "")
            if label not in sections:
                continue
        highlights.append(
            Highlight(id=uuid, text=text, color=color, book_id=book_id, book_title=book_title)
        )
    return highlights
