import contextlib
import sqlite3
import threading
import os
from typing import List, Dict, Optional
from lib.log_setup import logger


def get_next_setup(setups_sorted_by_priority: List[Dict], current_id: Optional[int]) -> Optional[Dict]:
    """Given setups already ordered by ascending priority, return the one after
    current_id, wrapping around. Returns the first setup if current_id is None or
    not found (e.g. it was deleted since the last cycle). Returns None if the list
    is empty."""
    if not setups_sorted_by_priority:
        return None
    if current_id is None:
        return setups_sorted_by_priority[0]
    for i, s in enumerate(setups_sorted_by_priority):
        if s["id"] == current_id:
            return setups_sorted_by_priority[(i + 1) % len(setups_sorted_by_priority)]
    return setups_sorted_by_priority[0]


class PortSetupManager:
    """Manage saved MIDI port setups (named bundles of input/secondary/playback
    ports + whether to auto-connect them), so the whole bundle can be applied at
    once from the web UI or cycled through with a physical button.

    Schema:
        port_setups(id INTEGER PK, priority INTEGER UNIQUE, name TEXT,
                    input_port TEXT, secondary_input_port TEXT, play_port TEXT,
                    auto_connect INTEGER)
    """

    def __init__(self, db_path: str = "port_setups.db"):
        if not os.path.isabs(db_path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            data_dir = os.path.join(project_root, 'data')
            try:
                os.makedirs(data_dir, exist_ok=True)
            except OSError:
                data_dir = os.path.abspath(project_root)
            db_path = os.path.join(data_dir, db_path)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS port_setups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    priority INTEGER NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    input_port TEXT NOT NULL,
                    secondary_input_port TEXT NOT NULL DEFAULT 'default',
                    play_port TEXT NOT NULL,
                    auto_connect INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "priority": row[1],
            "name": row[2],
            "input_port": row[3],
            "secondary_input_port": row[4],
            "play_port": row[5],
            "auto_connect": bool(row[6]),
        }

    def list_setups(self) -> List[Dict]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, priority, name, input_port, secondary_input_port, play_port, auto_connect "
                "FROM port_setups ORDER BY priority ASC"
            )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_setup(self, setup_id: int) -> Optional[Dict]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, priority, name, input_port, secondary_input_port, play_port, auto_connect "
                "FROM port_setups WHERE id=?",
                (setup_id,)
            )
            row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def _validate(self, name, priority, input_port, play_port):
        if not name or not str(name).strip():
            raise ValueError("Setup name cannot be empty")
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            raise ValueError("Priority must be an integer")
        if not input_port or not str(input_port).strip():
            raise ValueError("Input port cannot be empty")
        if not play_port or not str(play_port).strip():
            raise ValueError("Playback port cannot be empty")
        return priority

    def create_setup(self, name: str, priority, input_port: str,
                      secondary_input_port: str = "default", play_port: str = None,
                      auto_connect: bool = False) -> Dict:
        priority = self._validate(name, priority, input_port, play_port)
        name = str(name).strip()
        secondary_input_port = secondary_input_port or "default"

        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM port_setups WHERE priority=?", (priority,))
            if cur.fetchone() is not None:
                raise ValueError(f"Priority {priority} is already used by another setup")
            cur.execute(
                "INSERT INTO port_setups(priority, name, input_port, secondary_input_port, play_port, auto_connect) "
                "VALUES(?,?,?,?,?,?)",
                (priority, name, input_port, secondary_input_port, play_port, int(bool(auto_connect)))
            )
            conn.commit()
            setup_id = cur.lastrowid

        return self.get_setup(setup_id)

    def update_setup(self, setup_id: int, name: str, priority, input_port: str,
                      secondary_input_port: str = "default", play_port: str = None,
                      auto_connect: bool = False) -> Dict:
        priority = self._validate(name, priority, input_port, play_port)
        name = str(name).strip()
        secondary_input_port = secondary_input_port or "default"

        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM port_setups WHERE id=?", (setup_id,))
            if cur.fetchone() is None:
                raise ValueError(f"Setup {setup_id} not found")
            cur.execute("SELECT id FROM port_setups WHERE priority=? AND id!=?", (priority, setup_id))
            if cur.fetchone() is not None:
                raise ValueError(f"Priority {priority} is already used by another setup")
            cur.execute(
                "UPDATE port_setups SET priority=?, name=?, input_port=?, secondary_input_port=?, "
                "play_port=?, auto_connect=? WHERE id=?",
                (priority, name, input_port, secondary_input_port, play_port, int(bool(auto_connect)), setup_id)
            )
            conn.commit()

        return self.get_setup(setup_id)

    def delete_setup(self, setup_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM port_setups WHERE id=?", (setup_id,))
            changed = cur.rowcount > 0
            conn.commit()
        return changed
