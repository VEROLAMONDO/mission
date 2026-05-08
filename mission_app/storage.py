"""SQLite persistence for the Mission desktop app."""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from .models import ProgressInput, TaskStatus, TaskType, utc_now_iso, weighted_progress

APP_DIR = Path.home() / ".mission_todolist"
DB_PATH = APP_DIR / "mission.db"


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'minimum',
    category TEXT NOT NULL DEFAULT 'default',
    tags TEXT NOT NULL DEFAULT '',
    estimated_minutes INTEGER NOT NULL DEFAULT 20,
    actual_minutes INTEGER NOT NULL DEFAULT 0,
    difficulty INTEGER NOT NULL DEFAULT 1,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'todo',
    progress REAL NOT NULL DEFAULT 0,
    deadline TEXT,
    acceptance_criteria TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS task_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    completion_rate REAL NOT NULL,
    self_rating INTEGER,
    objective_score REAL,
    actual_minutes INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS token_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    formula TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    tags TEXT NOT NULL DEFAULT '',
    daily_new_limit INTEGER NOT NULL DEFAULT 20,
    daily_review_limit INTEGER NOT NULL DEFAULT 100
);
CREATE TABLE IF NOT EXISTS memory_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'basic',
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}',
    tags TEXT NOT NULL DEFAULT '',
    difficulty INTEGER NOT NULL DEFAULT 1,
    memory_value REAL NOT NULL DEFAULT 100,
    review_count INTEGER NOT NULL DEFAULT 0,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    next_review_at TEXT,
    last_review_at TEXT,
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    linked_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class MissionStore:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()
        self.ensure_seed_data()

    def close(self) -> None:
        self.connection.close()

    def ensure_seed_data(self) -> None:
        deck_count = self.connection.execute("SELECT COUNT(*) FROM decks").fetchone()[0]
        if deck_count == 0:
            self.connection.execute("INSERT INTO decks(name, tags) VALUES(?, ?)", ("默认牌组", ""))
        task_count = self.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if task_count == 0:
            project_id = self.create_task(
                title="示例：构建任务成长系统",
                description="本地部署 Windows/Android 任务成长系统 MVP。",
                task_type=TaskType.PROJECT,
                estimated_minutes=120,
                difficulty=3,
                acceptance_criteria="完成需求、实现原型、验证数据保存。",
            )
            self.create_task("梳理今日任务 20 分钟", parent_id=project_id, estimated_minutes=20, difficulty=1)
            self.create_task("录入一张记忆卡片 20 分钟", parent_id=project_id, estimated_minutes=20, difficulty=1)
            self.recalculate_ancestors(project_id)
        self.connection.commit()

    def rows(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(query, params).fetchall())

    def row(self, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        return self.connection.execute(query, params).fetchone()

    def create_task(
        self,
        title: str,
        description: str = "",
        task_type: str = TaskType.MINIMUM,
        parent_id: int | None = None,
        category: str = "default",
        tags: str = "",
        estimated_minutes: int = 20,
        difficulty: int = 1,
        priority: str = "medium",
        deadline: str | None = None,
        acceptance_criteria: str = "",
    ) -> int:
        now = utc_now_iso()
        cursor = self.connection.execute(
            """
            INSERT INTO tasks(parent_id, title, description, type, category, tags, estimated_minutes,
                              difficulty, priority, status, deadline, acceptance_criteria, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parent_id,
                title.strip(),
                description.strip(),
                str(task_type),
                category.strip() or "default",
                tags.strip(),
                max(1, estimated_minutes),
                max(1, min(5, difficulty)),
                priority,
                TaskStatus.TODO,
                deadline or None,
                acceptance_criteria.strip(),
                now,
                now,
            ),
        )
        self.connection.commit()
        if parent_id:
            self.recalculate_ancestors(parent_id)
        return int(cursor.lastrowid)

    def update_task_progress(
        self,
        task_id: int,
        progress: float,
        status: str | None = None,
        actual_minutes: int | None = None,
    ) -> None:
        now = utc_now_iso()
        updates = ["progress = ?", "updated_at = ?"]
        params: list[Any] = [max(0, min(100, progress)), now]
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == TaskStatus.COMPLETED:
                updates.append("completed_at = ?")
                params.append(now)
        if actual_minutes is not None:
            updates.append("actual_minutes = ?")
            params.append(max(0, actual_minutes))
        params.append(task_id)
        self.connection.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        self.connection.commit()
        parent = self.row("SELECT parent_id FROM tasks WHERE id = ?", (task_id,))
        if parent and parent["parent_id"]:
            self.recalculate_ancestors(int(parent["parent_id"]))

    def recalculate_ancestors(self, task_id: int) -> None:
        current_id: int | None = task_id
        while current_id:
            children = self.rows("SELECT progress, estimated_minutes FROM tasks WHERE parent_id = ?", (current_id,))
            if children:
                progress = weighted_progress(
                    ProgressInput(float(child["progress"]), int(child["estimated_minutes"])) for child in children
                )
                status = TaskStatus.COMPLETED if progress >= 100 else TaskStatus.IN_PROGRESS if progress > 0 else TaskStatus.TODO
                self.connection.execute(
                    "UPDATE tasks SET progress = ?, status = ?, updated_at = ? WHERE id = ?",
                    (progress, status, utc_now_iso(), current_id),
                )
            parent = self.row("SELECT parent_id FROM tasks WHERE id = ?", (current_id,))
            current_id = int(parent["parent_id"]) if parent and parent["parent_id"] else None
        self.connection.commit()

    def add_review(self, task_id: int, completion_rate: float, self_rating: int, actual_minutes: int, note: str) -> None:
        self.connection.execute(
            """
            INSERT INTO task_reviews(task_id, completion_rate, self_rating, actual_minutes, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, completion_rate, self_rating, actual_minutes, note, utc_now_iso()),
        )
        self.connection.commit()

    def add_token_ledger(self, task_id: int | None, ledger_type: str, amount: int, reason: str, formula: str = "") -> None:
        self.connection.execute(
            "INSERT INTO token_ledger(task_id, type, amount, reason, formula, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, ledger_type, amount, reason, formula, utc_now_iso()),
        )
        self.connection.commit()

    def token_balance(self) -> int:
        return int(self.connection.execute("SELECT COALESCE(SUM(amount), 0) FROM token_ledger").fetchone()[0])

    def create_card(self, deck_id: int, front: str, back: str, card_type: str = "basic", tags: str = "") -> int:
        cursor = self.connection.execute(
            "INSERT INTO memory_cards(deck_id, type, front, back, tags) VALUES (?, ?, ?, ?, ?)",
            (deck_id, card_type, front.strip(), back.strip(), tags.strip()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def export_cards_csv(self, path: Path) -> None:
        cards = self.rows(
            """
            SELECT decks.name AS deck, front, back, type, memory_cards.tags, extra_json, difficulty
            FROM memory_cards JOIN decks ON memory_cards.deck_id = decks.id
            ORDER BY decks.name, memory_cards.id
            """
        )
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["deck", "front", "back", "type", "tags", "extra_json", "difficulty"])
            writer.writeheader()
            for card in cards:
                writer.writerow(dict(card))

    def import_cards_csv(self, path: Path) -> int:
        count = 0
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                deck_name = row.get("deck") or "默认牌组"
                deck = self.row("SELECT id FROM decks WHERE name = ?", (deck_name,))
                if deck is None:
                    cursor = self.connection.execute("INSERT INTO decks(name) VALUES (?)", (deck_name,))
                    deck_id = int(cursor.lastrowid)
                else:
                    deck_id = int(deck["id"])
                if row.get("front") and row.get("back"):
                    self.create_card(deck_id, row["front"], row["back"], row.get("type") or "basic", row.get("tags") or "")
                    count += 1
        self.connection.commit()
        return count


    def export_cards_apkg(self, path: Path) -> None:
        """Export basic cards to a simple Anki-compatible APKG package."""
        cards = self.rows(
            """
            SELECT memory_cards.*, decks.name AS deck_name
            FROM memory_cards JOIN decks ON memory_cards.deck_id = decks.id
            ORDER BY decks.name, memory_cards.id
            """
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            collection_path = Path(temp_dir) / "collection.anki2"
            conn = sqlite3.connect(collection_path)
            conn.executescript(
                """
                CREATE TABLE col (
                    id integer primary key, crt integer not null, mod integer not null,
                    scm integer not null, ver integer not null, dty integer not null,
                    usn integer not null, ls integer not null, conf text not null,
                    models text not null, decks text not null, dconf text not null, tags text not null
                );
                CREATE TABLE notes (
                    id integer primary key, guid text not null, mid integer not null,
                    mod integer not null, usn integer not null, tags text not null,
                    flds text not null, sfld text not null, csum integer not null,
                    flags integer not null, data text not null
                );
                CREATE TABLE cards (
                    id integer primary key, nid integer not null, did integer not null,
                    ord integer not null, mod integer not null, usn integer not null,
                    type integer not null, queue integer not null, due integer not null,
                    ivl integer not null, factor integer not null, reps integer not null,
                    lapses integer not null, left integer not null, odue integer not null,
                    odid integer not null, flags integer not null, data text not null
                );
                CREATE TABLE revlog (
                    id integer primary key, cid integer not null, usn integer not null,
                    ease integer not null, ivl integer not null, lastIvl integer not null,
                    factor integer not null, time integer not null, type integer not null
                );
                CREATE TABLE graves (usn integer not null, oid integer not null, type integer not null);
                """
            )
            now = int(time.time())
            model_id = 1607392319000
            deck_names = sorted({row["deck_name"] for row in cards} or {"默认牌组"})
            deck_ids = {name: 1607392319000 + index for index, name in enumerate(deck_names, start=1)}
            decks_json = {
                str(deck_id): {
                    "id": deck_id,
                    "name": name,
                    "desc": "Mission export",
                    "mod": now,
                    "usn": 0,
                    "collapsed": False,
                    "browserCollapsed": False,
                    "conf": 1,
                    "dyn": 0,
                    "extendNew": 10,
                    "extendRev": 50,
                    "newToday": [0, 0],
                    "revToday": [0, 0],
                    "lrnToday": [0, 0],
                    "timeToday": [0, 0],
                }
                for name, deck_id in deck_ids.items()
            }
            models_json = {
                str(model_id): {
                    "id": model_id,
                    "name": "Mission Basic",
                    "type": 0,
                    "mod": now,
                    "usn": 0,
                    "sortf": 0,
                    "did": next(iter(deck_ids.values())),
                    "flds": [
                        {"name": "Front", "ord": 0, "sticky": False, "rtl": False, "font": "Arial", "size": 20},
                        {"name": "Back", "ord": 1, "sticky": False, "rtl": False, "font": "Arial", "size": 20},
                    ],
                    "tmpls": [
                        {
                            "name": "Card 1",
                            "ord": 0,
                            "qfmt": "{{Front}}",
                            "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
                            "did": None,
                            "bqfmt": "",
                            "bafmt": "",
                        }
                    ],
                    "css": ".card { font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white; }",
                    "latexPre": "",
                    "latexPost": "",
                    "req": [[0, "any", [0]]],
                }
            }
            conn.execute(
                "INSERT INTO col VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    now,
                    now,
                    now,
                    11,
                    0,
                    0,
                    0,
                    "{}",
                    json.dumps(models_json),
                    json.dumps(decks_json),
                    "{}",
                    "{}",
                ),
            )
            for index, row in enumerate(cards, start=1):
                note_id = 1700000000000 + index
                card_id = 1800000000000 + index
                deck_id = deck_ids[row["deck_name"]]
                tags = f" {row['tags'].replace(',', ' ')} " if row["tags"] else ""
                flds = f"{row['front']}\x1f{row['back']}"
                conn.execute(
                    "INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (note_id, f"mission-{row['id']}", model_id, now, 0, tags, flds, row["front"], 0, 0, row["extra_json"]),
                )
                conn.execute(
                    "INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (card_id, note_id, deck_id, 0, now, 0, 0, 0, index, 0, 2500, row["review_count"], row["wrong_count"], 0, 0, 0, 0, ""),
                )
            conn.commit()
            conn.close()
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(collection_path, "collection.anki2")
                archive.writestr("media", "{}")

    def import_cards_apkg(self, path: Path) -> int:
        """Import basic front/back cards from an Anki APKG package."""
        count = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(path) as archive:
                collection_name = "collection.anki2" if "collection.anki2" in archive.namelist() else "collection.anki21"
                archive.extract(collection_name, temp_dir)
            conn = sqlite3.connect(Path(temp_dir) / collection_name)
            conn.row_factory = sqlite3.Row
            col = conn.execute("SELECT decks FROM col LIMIT 1").fetchone()
            decks = json.loads(col["decks"]) if col else {}
            note_decks: dict[int, str] = {}
            for row in conn.execute("SELECT nid, did FROM cards"):
                deck = decks.get(str(row["did"]), {})
                note_decks[int(row["nid"])] = deck.get("name", "APKG导入")
            for row in conn.execute("SELECT id, tags, flds FROM notes"):
                fields = row["flds"].split("\x1f")
                if len(fields) < 2:
                    continue
                deck_name = note_decks.get(int(row["id"]), "APKG导入")
                deck = self.row("SELECT id FROM decks WHERE name = ?", (deck_name,))
                if deck is None:
                    cursor = self.connection.execute("INSERT INTO decks(name) VALUES (?)", (deck_name,))
                    deck_id = int(cursor.lastrowid)
                else:
                    deck_id = int(deck["id"])
                self.create_card(deck_id, fields[0], fields[1], "basic", row["tags"].strip())
                count += 1
            conn.close()
        self.connection.commit()
        return count

    def export_backup_json(self, path: Path) -> None:
        payload = {}
        for table in ["tasks", "task_reviews", "token_ledger", "decks", "memory_cards", "notes", "settings"]:
            payload[table] = [dict(row) for row in self.rows(f"SELECT * FROM {table}")]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
