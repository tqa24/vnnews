import sqlite3
import os
from datetime import datetime
from .const import DB_PATH


def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Thêm cột source nếu chưa có
    cursor.execute('''CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        time TEXT,
        content TEXT,
        summary TEXT,
        link TEXT,
        is_new INTEGER DEFAULT 1,
        source TEXT
    )''')
    try:
        cursor.execute('ALTER TABLE news ADD COLUMN source TEXT')
    except Exception:
        pass
    cursor.execute('''CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY,
        gemini_api_key TEXT,
        last_update TEXT
    )''')
    conn.commit()
    conn.close()


def add_or_update_news(news):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Kiểm tra đã có tin cùng title và source chưa
    cursor.execute('''SELECT id FROM news WHERE title=? AND source=?''', (news['title'], news['source']))
    row = cursor.fetchone()
    if row:
        cursor.execute(
            '''UPDATE news SET time=?, content=?, summary=?, link=?, is_new=? WHERE id=?''',
            (
                news['time'],
                news['content'],
                news['summary'],
                news['link'],
                int(news.get('is_new', 1)),
                row[0]
            )
        )
    else:
        cursor.execute(
            '''INSERT INTO news (title, time, content, summary, link, is_new, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                news['title'],
                news['time'],
                news['content'],
                news['summary'],
                news['link'],
                int(news.get('is_new', 1)),
                news['source']
            )
        )
    conn.commit()
    conn.close()


def get_latest_news(limit=30, source=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if source:
        cursor.execute(
            '''SELECT title, time, summary, link, is_new
               FROM news
               WHERE source=?
               ORDER BY datetime(time) DESC
               LIMIT ?''',
            (source, limit)
        )
    else:
        cursor.execute(
            '''SELECT title, time, summary, link, is_new
               FROM news
               ORDER BY datetime(time) DESC
               LIMIT ?''',
            (limit,)
        )
    rows = cursor.fetchall()
    conn.close()
    return [
        {'title': r[0], 'time': r[1], 'summary': r[2], 'link': r[3], 'is_new': bool(r[4])}
        for r in rows
    ]


def mark_all_old(source=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if source:
        cursor.execute('UPDATE news SET is_new=0 WHERE source=?', (source,))
    else:
        cursor.execute('UPDATE news SET is_new=0')
    conn.commit()
    conn.close()


def delete_old_news(max_titles=200, source=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if source:
        cursor.execute('''DELETE FROM news WHERE id NOT IN (
            SELECT id FROM news WHERE source=? ORDER BY datetime(time) DESC LIMIT ?
        ) AND source=?''', (source, max_titles, source))
    else:
        cursor.execute('''DELETE FROM news WHERE id NOT IN (
            SELECT id FROM news ORDER BY datetime(time) DESC LIMIT ?
        )''', (max_titles,))
    conn.commit()
    conn.close()


def set_gemini_api_key(api_key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT OR REPLACE INTO config (id, gemini_api_key, last_update) VALUES (1, ?, ?)''',
        (api_key, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_gemini_api_key():
    init_db()  # Đảm bảo DB và bảng đã tồn tại
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT gemini_api_key FROM config WHERE id=1')
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None
