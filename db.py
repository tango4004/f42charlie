import sqlite3
import time
import uuid
import sys
import random

sys.path.insert(0, "/home/f42charlie/app")
from wordlist import WORDS
from auth import generate_session_id, generate_signed_session_id


class DB:
    def __init__(self, path):
        """Initialize database connection and create tables if needed"""
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._session_ids = set()

    def _create_tables(self):
        """Create all required tables + signed-session migrations."""
        try:
            self.cursor.execute(
                "ALTER TABLE workspaces ADD COLUMN plugins TEXT DEFAULT '[]'"
            )
            self.conn.commit()
        except Exception:
            pass

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT,
                workdir TEXT,
                passphrase_hash TEXT UNIQUE,
                plugins TEXT DEFAULT '[]',
                created INTEGER
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                workspace_id TEXT,
                authenticated INTEGER DEFAULT 0,
                created INTEGER,
                expires INTEGER
            )
            """
        )

        # Signed session columns (idempotent migrations)
        for col_def in (
            "mode TEXT DEFAULT 'legacy'",
            "client_pub TEXT",
            "last_ts INTEGER DEFAULT 0",
            "status TEXT DEFAULT 'active'",
        ):
            col = col_def.split()[0]
            try:
                self.cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col_def}")
                self.conn.commit()
            except Exception:
                pass

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                session_id TEXT,
                plugin TEXT,
                command TEXT,
                argument TEXT,
                workdir TEXT,
                status TEXT DEFAULT 'pending',
                created INTEGER
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                task_id TEXT PRIMARY KEY,
                session_id TEXT,
                output TEXT,
                created INTEGER,
                expires INTEGER
            )
            """
        )

        self.conn.commit()

    def _unique_session_id(self, signed=False):
        """Generate a unique session_id."""
        max_attempts = 100
        for _ in range(max_attempts):
            sid = generate_signed_session_id() if signed else generate_session_id()
            # also check DB uniqueness
            self.cursor.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (sid,)
            )
            if self.cursor.fetchone():
                continue
            if sid not in self._session_ids:
                self._session_ids.add(sid)
                return sid
        return ("s" if signed else "sess") + uuid.uuid4().hex

    def create_workspace(self, name, workdir, passphrase_hash, plugins=None):
        """Create a new workspace and return workspace_id"""
        workspace_id = uuid.uuid4().hex
        now = int(time.time())

        import json as _j

        plugins_json = _j.dumps(plugins if plugins is not None else [])
        self.cursor.execute(
            """
            INSERT INTO workspaces (id, name, workdir, passphrase_hash, plugins, created)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workspace_id, name, workdir, passphrase_hash, plugins_json, now),
        )
        self.conn.commit()
        return workspace_id

    def get_workspace_plugins(self, workspace_id):
        import json as _j

        self.cursor.execute(
            "SELECT plugins FROM workspaces WHERE id = ?", (workspace_id,)
        )
        row = self.cursor.fetchone()
        if not row or not row[0]:
            return []
        try:
            return _j.loads(row[0])
        except Exception:
            return []

    def set_workspace_plugins(self, workspace_id, plugins):
        import json as _j

        self.cursor.execute(
            "UPDATE workspaces SET plugins = ? WHERE id = ?",
            (_j.dumps(plugins), workspace_id),
        )
        self.conn.commit()

    def get_workspace_by_passphrase(self, passphrase_hash):
        """Get workspace by passphrase hash"""
        self.cursor.execute(
            "SELECT * FROM workspaces WHERE passphrase_hash = ?",
            (passphrase_hash,),
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def get_workspace(self, workspace_id):
        """Get workspace by id"""
        self.cursor.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def create_session(
        self,
        workspace_id,
        authenticated=False,
        ttl_days=30,
        mode="legacy",
        client_pub=None,
        signed_id=False,
    ):
        """Create a new session and return session_id.

        mode:
          - legacy: soft word+digits sid (bootstrap / unauth)
          - signed: stable hex sid bound to client_pub
        expires=0 means no expiry (only used for signed when ttl_days<=0).
        """
        use_signed_id = signed_id or mode == "signed"
        session_id = self._unique_session_id(signed=use_signed_id)
        now = int(time.time())
        if ttl_days is None or ttl_days <= 0:
            expires = 0
        else:
            expires = now + (int(ttl_days) * 24 * 3600)
        authenticated_int = 1 if authenticated else 0

        self.cursor.execute(
            """
            INSERT INTO sessions
              (session_id, workspace_id, authenticated, created, expires,
               mode, client_pub, last_ts, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'active')
            """,
            (
                session_id,
                workspace_id,
                authenticated_int,
                now,
                expires,
                mode or "legacy",
                client_pub,
            ),
        )
        self.conn.commit()
        return session_id

    def get_session(self, session_id):
        """Get session by id, return None if expired/revoked."""
        self.cursor.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = self.cursor.fetchone()
        if not row:
            return None

        session = dict(row)
        now = int(time.time())

        if session.get("status") and session["status"] not in (None, "active"):
            return None

        exp = session.get("expires") or 0
        # exp==0 → no expiry (signed sessions)
        if exp != 0 and exp <= now:
            return None

        return session

    def get_active_session(self, workspace_id, mode=None):
        """Get last authenticated non-expired active session for workspace."""
        now = int(time.time())
        if mode:
            self.cursor.execute(
                """
                SELECT * FROM sessions
                WHERE workspace_id = ? AND authenticated = 1
                  AND (status IS NULL OR status = 'active')
                  AND (expires = 0 OR expires > ?)
                  AND mode = ?
                ORDER BY created DESC
                LIMIT 1
                """,
                (workspace_id, now, mode),
            )
        else:
            self.cursor.execute(
                """
                SELECT * FROM sessions
                WHERE workspace_id = ? AND authenticated = 1
                  AND (status IS NULL OR status = 'active')
                  AND (expires = 0 OR expires > ?)
                ORDER BY created DESC
                LIMIT 1
                """,
                (workspace_id, now),
            )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def revoke_workspace_sessions(self, workspace_id, except_sid=None):
        """Revoke all active sessions for a workspace (optional keep except_sid)."""
        now = int(time.time())
        if except_sid:
            self.cursor.execute(
                """
                UPDATE sessions
                SET status = 'revoked', expires = ?
                WHERE workspace_id = ? AND session_id != ?
                  AND (status IS NULL OR status = 'active')
                """,
                (now, workspace_id, except_sid),
            )
        else:
            self.cursor.execute(
                """
                UPDATE sessions
                SET status = 'revoked', expires = ?
                WHERE workspace_id = ?
                  AND (status IS NULL OR status = 'active')
                """,
                (now, workspace_id),
            )
        self.conn.commit()

    def revoke_session(self, session_id):
        now = int(time.time())
        self.cursor.execute(
            """
            UPDATE sessions SET status = 'revoked', expires = ?
            WHERE session_id = ?
            """,
            (now, session_id),
        )
        self.conn.commit()

    def set_authenticated(self, session_id, workspace_id):
        """Mark session as authenticated"""
        self.cursor.execute(
            """
            UPDATE sessions SET authenticated = 1
            WHERE session_id = ? AND workspace_id = ?
            """,
            (session_id, workspace_id),
        )
        self.conn.commit()

    def touch_last_ts(self, session_id, ts: int):
        self.cursor.execute(
            "UPDATE sessions SET last_ts = ? WHERE session_id = ?",
            (int(ts), session_id),
        )
        self.conn.commit()

    def rotate_session(self, old_session_id, new_session_id, task_id=None):
        """Legacy: mark old session expired, transfer task/result ownership."""
        now = int(time.time())
        self.cursor.execute(
            "UPDATE sessions SET expires = ?, status = 'rotated' WHERE session_id = ?",
            (now, old_session_id),
        )
        self.cursor.execute(
            "UPDATE tasks SET session_id = ? WHERE session_id = ?",
            (new_session_id, old_session_id),
        )
        self.cursor.execute(
            "UPDATE results SET session_id = ? WHERE session_id = ?",
            (new_session_id, old_session_id),
        )
        self.conn.commit()

    def create_task(self, session_id, plugin, command, argument, workdir):
        """Create a new task and return task_id"""
        task_id = uuid.uuid4().hex
        now = int(time.time())

        self.cursor.execute(
            """
            INSERT INTO tasks
              (task_id, session_id, plugin, command, argument, workdir, status, created)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (task_id, session_id, plugin, command, argument, workdir, now),
        )
        self.conn.commit()
        return task_id

    def get_pending_tasks(self):
        """Get all pending tasks"""
        self.cursor.execute("SELECT * FROM tasks WHERE status = 'pending'")
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]

    def set_task_running(self, task_id):
        self.cursor.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (task_id,),
        )
        self.conn.commit()

    def set_task_done(self, task_id):
        self.cursor.execute(
            "UPDATE tasks SET status = 'done' WHERE task_id = ?",
            (task_id,),
        )
        self.conn.commit()

    def set_result(self, task_id, session_id, output, ttl_days=1):
        now = int(time.time())
        expires = now + (ttl_days * 24 * 3600)
        self.cursor.execute(
            """
            INSERT INTO results (task_id, session_id, output, created, expires)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, session_id, output, now, expires),
        )
        self.conn.commit()

    def echo_result(self, session_id, text):
        """Attach an immediate echo result to session (signed path, no rotate)."""
        task_id = self.create_task(session_id, "_echo", "_echo", text, "/tmp")
        self.set_task_running(task_id)
        self.set_result(task_id, session_id, text)
        self.set_task_done(task_id)
        return task_id

    def get_result_by_session(self, session_id):
        now = int(time.time())
        self.cursor.execute(
            """
            SELECT output FROM results
            WHERE session_id = ? AND expires > ?
            ORDER BY created DESC, rowid DESC
            LIMIT 1
            """,
            (session_id, now),
        )
        row = self.cursor.fetchone()
        return row[0] if row else None

    def is_running(self, session_id):
        self.cursor.execute(
            """
            SELECT COUNT(*) FROM tasks
            WHERE session_id = ? AND status = 'running'
            """,
            (session_id,),
        )
        count = self.cursor.fetchone()[0]
        return count > 0

    def cleanup_expired(self):
        now = int(time.time())
        # never delete expires=0 (no-expiry signed) unless revoked (expires set)
        self.cursor.execute(
            "DELETE FROM sessions WHERE expires != 0 AND expires < ?", (now,)
        )
        deleted_sessions = self.cursor.rowcount
        self.cursor.execute("DELETE FROM results WHERE expires < ?", (now,))
        deleted_results = self.cursor.rowcount
        self.conn.commit()
        return deleted_sessions + deleted_results


if __name__ == "__main__":
    from auth import generate_ed25519_keypair

    db = DB(":memory:")

    ws_id = db.create_workspace("test", "/tmp/t", "hash123")
    assert ws_id
    ws = db.get_workspace_by_passphrase("hash123")
    assert ws is not None

    sid = db.create_session(ws_id, authenticated=False)
    assert sid

    priv, pub = generate_ed25519_keypair()
    sid2 = db.create_session(
        ws_id, authenticated=True, mode="signed", client_pub=pub, ttl_days=0
    )
    s = db.get_session(sid2)
    assert s and s["mode"] == "signed" and s["client_pub"] == pub
    assert s["expires"] == 0

    db.revoke_workspace_sessions(ws_id, except_sid=sid2)
    assert db.get_session(sid) is None or db.get_session(sid) is None
    assert db.get_session(sid2) is not None

    db.echo_result(sid2, "hello")
    assert db.get_result_by_session(sid2) == "hello"

    print("DB OK")
