import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "question_bank.db")
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "output", "images")

SUBJECTS = ["國文", "英文", "數學", "理化", "生物", "地球科學", "歷史", "地理", "公民"]
QUESTION_TYPES = ["選擇題", "填充題", "問答題", "閱讀測驗", "寫作題", "其他"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id          TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            created_at  DATETIME DEFAULT (datetime('now','localtime')),
            exported_at DATETIME DEFAULT NULL,
            subject     TEXT NOT NULL,
            type        TEXT NOT NULL,
            stem        TEXT NOT NULL,
            options     TEXT DEFAULT '[]',
            answer      TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS question_images (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id TEXT NOT NULL,
            image_path  TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Initialized: {DB_PATH}")
