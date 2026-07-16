import threading, subprocess, time, sys, os
sys.path.insert(0, '/home/f42charlie/app')
from db import DB

class Daemon(threading.Thread):
    def __init__(self, db: DB, plugins_dir: str = '/home/f42charlie/app/plugins'):
        super().__init__(daemon=True)
        self.db = db
        self.plugins_dir = plugins_dir
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                tasks = self.db.get_pending_tasks()
                for task in tasks:
                    self.db.set_task_running(task['task_id'])
                    t = threading.Thread(
                        target=self._run_plugin,
                        args=(task,),
                        daemon=True
                    )
                    t.start()
            except Exception as e:
                print(f"[daemon] error: {e}", flush=True)
            self._stop_event.wait(1.0)

    def _run_plugin(self, task: dict):
        # _echo: instant result, no subprocess needed
        if task['plugin'] == '_echo':
            self.db.set_result(task['task_id'], task['session_id'], task['argument'])
            self.db.set_task_done(task['task_id'])
            return
        plugin_path = f"{self.plugins_dir}/{task['plugin']}.py"
        try:
            # Check if plugin file exists
            if not os.path.exists(plugin_path):
                raise FileNotFoundError(f"Plugin file not found: {plugin_path}")
            
            r = subprocess.run(
                ['python3', plugin_path,
                 task['command'],
                 task['argument'],
                 task['workdir']],
                capture_output=True, text=True, timeout=60
            )
            output = r.stdout
            if r.stderr:
                output += '\n[stderr]\n' + r.stderr
            if not output:
                output = '(no output)'
        except subprocess.TimeoutExpired:
            output = 'error: plugin timeout'
        except FileNotFoundError:
            output = f"error: plugin not found: {task['plugin']}"
        except Exception as e:
            output = f"error: {e}"

        self.db.set_result(task['task_id'], task['session_id'], output)
        self.db.set_task_done(task['task_id'])
        print(f"[daemon] task {task['task_id'][:8]} done: {output[:50]}", flush=True)


if __name__ == '__main__':
    import time
    db = DB(':memory:')

    # setup
    ws_id = db.create_workspace('test', '/tmp', 'hash123')
    sid = db.create_session(ws_id, authenticated=True)

    # создать задачу exec echo
    task_id = db.create_task(sid, 'exec', 'echo', 'daemon test ok', '/tmp')
    assert db.get_pending_tasks(), "no pending tasks"
    print(f"task created: {task_id[:8]}")

    # запустить демон
    daemon = Daemon(db)
    daemon.start()

    # ждать результата
    for i in range(10):
        time.sleep(0.5)
        result = db.get_result_by_session(sid)
        if result:
            break

    daemon.stop()

    assert result, "no result after 5s"
    assert 'daemon test ok' in result, f"unexpected result: {result}"
    print(f"result: {result.strip()}")

    # тест несуществующего плагина
    sid2 = db.create_session(ws_id, authenticated=True)
    task_id2 = db.create_task(sid2, 'nonexistent', 'cmd', 'arg', '/tmp')
    daemon2 = Daemon(db)
    daemon2.start()
    for i in range(10):
        time.sleep(0.5)
        result2 = db.get_result_by_session(sid2)
        if result2:
            break
    daemon2.stop()
    assert result2 and 'error' in result2, f"expected error: {result2}"
    print(f"nonexistent plugin: {result2.strip()}")

    print("DAEMON OK")
