import sqlite3
import time
import uuid
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '/home/f42charlie/app')
from wordlist import WORDS
import random

_session_counter = 0

def generate_session_id():
    global _session_counter
    word = random.choice(WORDS)
    digits = str(random.randint(1000, 9999))
    _session_counter += 1
    for attempt in range(100):
        test_id = word + digits + str(_session_counter + attempt)[-4:]
        if len(test_id) >= 8 and test_id[:-4].isalpha() and test_id[-4:].isdigit():
            return test_id
    return word + digits

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
        """Create all required tables"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT,
                workdir TEXT,
                passphrase_hash TEXT UNIQUE,
                created INTEGER
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                workspace_id TEXT,
                authenticated INTEGER DEFAULT 0,
                created INTEGER,
                expires INTEGER
            )
        ''')
        
        self.cursor.execute('''
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
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                task_id TEXT PRIMARY KEY,
                session_id TEXT,
                output TEXT,
                created INTEGER,
                expires INTEGER
            )
        ''')
        
        self.conn.commit()
    
    def _unique_session_id(self):
        """Generate a unique session_id"""
        max_attempts = 100
        for _ in range(max_attempts):
            sid = generate_session_id()
            if sid not in self._session_ids:
                self._session_ids.add(sid)
                return sid
        return "sess" + uuid.uuid4().hex[:12]
    
    def create_workspace(self, name, workdir, passphrase_hash):
        """Create a new workspace and return workspace_id"""
        workspace_id = uuid.uuid4().hex
        now = int(time.time())
        
        self.cursor.execute('''
            INSERT INTO workspaces (id, name, workdir, passphrase_hash, created)
            VALUES (?, ?, ?, ?, ?)
        ''', (workspace_id, name, workdir, passphrase_hash, now))
        
        self.conn.commit()
        return workspace_id
    
    def get_workspace_by_passphrase(self, passphrase_hash):
        """Get workspace by passphrase hash"""
        self.cursor.execute('''
            SELECT * FROM workspaces WHERE passphrase_hash = ?
        ''', (passphrase_hash,))
        
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def get_workspace(self, workspace_id):
        """Get workspace by id"""
        self.cursor.execute('''
            SELECT * FROM workspaces WHERE id = ?
        ''', (workspace_id,))
        
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def create_session(self, workspace_id, authenticated=False, ttl_days=30):
        """Create a new session and return session_id"""
        session_id = self._unique_session_id()
        now = int(time.time())
        expires = now + (ttl_days * 24 * 3600)
        authenticated_int = 1 if authenticated else 0
        
        self.cursor.execute('''
            INSERT INTO sessions (session_id, workspace_id, authenticated, created, expires)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, workspace_id, authenticated_int, now, expires))
        
        self.conn.commit()
        return session_id
    
    def get_session(self, session_id):
        """Get session by id, return None if expired"""
        self.cursor.execute('''
            SELECT * FROM sessions WHERE session_id = ?
        ''', (session_id,))
        
        row = self.cursor.fetchone()
        if not row:
            return None
        
        session = dict(row)
        now = int(time.time())
        
        # Check if expired
        if session['expires'] <= now:
            return None
        
        return session
    
    def get_active_session(self, workspace_id):
        """Get last authenticated non-expired session for workspace"""
        now = int(time.time())
        
        self.cursor.execute('''
            SELECT * FROM sessions 
            WHERE workspace_id = ? AND authenticated = 1 AND expires > ?
            ORDER BY created DESC
            LIMIT 1
        ''', (workspace_id, now))
        
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def set_authenticated(self, session_id, workspace_id):
        """Mark session as authenticated"""
        self.cursor.execute('''
            UPDATE sessions SET authenticated = 1
            WHERE session_id = ? AND workspace_id = ?
        ''', (session_id, workspace_id))
        
        self.conn.commit()
    
    def rotate_session(self, old_session_id, new_session_id, task_id=None):
        """Mark old session as expired, transfer task/result ownership to new session."""
        now = int(time.time())
        self.cursor.execute(
            'UPDATE sessions SET expires = ? WHERE session_id = ?',
            (now, old_session_id))
        self.cursor.execute(
            'UPDATE tasks SET session_id = ? WHERE session_id = ?',
            (new_session_id, old_session_id))
        self.cursor.execute(
            'UPDATE results SET session_id = ? WHERE session_id = ?',
            (new_session_id, old_session_id))
        self.conn.commit()
    
    def create_task(self, session_id, plugin, command, argument, workdir):
        """Create a new task and return task_id"""
        task_id = uuid.uuid4().hex
        now = int(time.time())
        
        self.cursor.execute('''
            INSERT INTO tasks (task_id, session_id, plugin, command, argument, workdir, status, created)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        ''', (task_id, session_id, plugin, command, argument, workdir, now))
        
        self.conn.commit()
        return task_id
    
    def get_pending_tasks(self):
        """Get all pending tasks"""
        self.cursor.execute('''
            SELECT * FROM tasks WHERE status = 'pending'
        ''')
        
        rows = self.cursor.fetchall()
        return [dict(row) for row in rows]
    
    def set_task_running(self, task_id):
        """Mark task as running"""
        self.cursor.execute('''
            UPDATE tasks SET status = 'running'
            WHERE task_id = ?
        ''', (task_id,))
        
        self.conn.commit()
    
    def set_task_done(self, task_id):
        """Mark task as done"""
        self.cursor.execute('''
            UPDATE tasks SET status = 'done'
            WHERE task_id = ?
        ''', (task_id,))
        
        self.conn.commit()
    
    def set_result(self, task_id, session_id, output, ttl_days=1):
        """Store task result"""
        now = int(time.time())
        expires = now + (ttl_days * 24 * 3600)
        
        self.cursor.execute('''
            INSERT INTO results (task_id, session_id, output, created, expires)
            VALUES (?, ?, ?, ?, ?)
        ''', (task_id, session_id, output, now, expires))
        
        self.conn.commit()
    
    def get_result_by_session(self, session_id):
        """Get result output for session (last result)"""
        now = int(time.time())
        
        self.cursor.execute('''
            SELECT output FROM results 
            WHERE session_id = ? AND expires > ?
            ORDER BY created DESC, rowid DESC
            LIMIT 1
        ''', (session_id, now))
        
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    def is_running(self, session_id):
        """Check if there are any running tasks for session"""
        self.cursor.execute('''
            SELECT COUNT(*) FROM tasks 
            WHERE session_id = ? AND status = 'running'
        ''', (session_id,))
        
        count = self.cursor.fetchone()[0]
        return count > 0
    
    def cleanup_expired(self):
        """Delete expired sessions and results, return count of deleted rows"""
        now = int(time.time())
        
        # Delete expired sessions
        self.cursor.execute('DELETE FROM sessions WHERE expires < ?', (now,))
        deleted_sessions = self.cursor.rowcount
        
        # Delete expired results
        self.cursor.execute('DELETE FROM results WHERE expires < ?', (now,))
        deleted_results = self.cursor.rowcount
        
        self.conn.commit()
        
        return deleted_sessions + deleted_results


if __name__ == '__main__':
    db = DB(':memory:')
    
    # Test create_workspace
    ws_id = db.create_workspace('test', '/home/f42charlie/workspaces/test', 'hash123')
    assert ws_id
    
    # Test get_workspace_by_passphrase
    ws = db.get_workspace_by_passphrase('hash123')
    assert ws is not None
    
    # Test create_session
    sid = db.create_session(ws_id, authenticated=True)
    assert sid
    assert sid[:-4].isalpha()  # word part
    assert sid[-4:].isdigit()  # digit part
    
    # Test get_session
    session = db.get_session(sid)
    assert session is not None
    
    # Test get_active_session
    active_session = db.get_active_session(ws_id)
    assert active_session is not None
    
    # Test create_task
    task_id = db.create_task(sid, 'exec', 'echo', 'hello', '/tmp')
    assert task_id
    
    # Test get_pending_tasks
    pending = db.get_pending_tasks()
    assert pending
    
    # Test set_task_running
    db.set_task_running(task_id)
    
    # Test is_running
    assert db.is_running(sid)
    
    # Test set_task_done
    db.set_task_done(task_id)
    
    # Test set_result
    db.set_result(task_id, sid, 'hello\n')
    
    # Test get_result_by_session
    result = db.get_result_by_session(sid)
    assert result == 'hello\n'
    
    # Test rotate_session
    new_sid = db.create_session(ws_id, authenticated=True)
    db.rotate_session(sid, new_sid)
    assert db.get_session(sid) is None
    
    print('DB OK')
