"""Run once to create test fixture databases."""
import sqlite3
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def create_books_fixture():
    db_path = FIXTURES_DIR / "test_books.sqlite"
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE ZAEANNOTATION (
            ZANNOTATIONUUID     VARCHAR PRIMARY KEY,
            ZANNOTATIONASSETID  VARCHAR,
            ZANNOTATIONSELECTEDTEXT VARCHAR,
            ZANNOTATIONSTYLE    INTEGER,
            ZANNOTATIONDELETED  INTEGER DEFAULT 0,
            ZANNOTATIONCREATIONDATE TIMESTAMP
        );
    """)
    conn.executemany(
        "INSERT INTO ZAEANNOTATION VALUES (?,?,?,?,?,?)",
        [
            # yellow (style=3): English vocab
            ("uuid-1", "asset-ddia", "reliability means the system should continue to work correctly", 3, 0, 1000.0),
            # green (style=1): technical concept
            ("uuid-2", "asset-ddia", "A fault is defined as one component deviating from its spec", 1, 0, 1001.0),
            # blue (style=2): both
            ("uuid-3", "asset-ddia", "Scalability is the term used to describe a system's ability to cope with increased load", 2, 0, 1002.0),
            # deleted — must be excluded
            ("uuid-4", "asset-ddia", "this highlight was deleted", 3, 1, 1003.0),
            # different book — must be excluded when filtering by asset
            ("uuid-5", "asset-other", "some other book highlight", 1, 0, 1004.0),
        ],
    )
    conn.commit()
    conn.close()
    print(f"Created {db_path}")


if __name__ == "__main__":
    create_books_fixture()
