import sqlite3
from pathlib import Path
from typing import Optional
from notemaster.models import Highlight, HighlightColor

# ZANNOTATIONSTYLE values confirmed from Apple Books on macOS
_STYLE_TO_COLOR: dict[int, HighlightColor] = {
    3: HighlightColor.YELLOW,
    1: HighlightColor.GREEN,
    2: HighlightColor.BLUE,
}

_ANNOTATION_GLOB = (
    "Library/Containers/com.apple.iBooksX/Data/Documents/AEAnnotation/AEAnnotation_*.sqlite"
)


def find_annotation_db() -> Optional[Path]:
    matches = list(Path.home().glob(_ANNOTATION_GLOB))
    return matches[0] if matches else None


def get_highlights(
    asset_id: str,
    book_id: str,
    book_title: str,
    db_path: Optional[Path] = None,
) -> list[Highlight]:
    if db_path is None:
        db_path = find_annotation_db()
    if db_path is None:
        return []

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT ZANNOTATIONUUID, ZANNOTATIONSELECTEDTEXT, ZANNOTATIONSTYLE
        FROM ZAEANNOTATION
        WHERE ZANNOTATIONASSETID = ?
          AND ZANNOTATIONDELETED = 0
          AND ZANNOTATIONSELECTEDTEXT IS NOT NULL
        """,
        (asset_id,),
    ).fetchall()
    conn.close()

    highlights = []
    for uuid, text, style in rows:
        color = _STYLE_TO_COLOR.get(style)
        if color is None:
            continue
        highlights.append(
            Highlight(id=uuid, text=text, color=color, book_id=book_id, book_title=book_title)
        )
    return highlights
