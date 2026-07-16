import sys, json, time, threading
sys.path.insert(0, '/home/f42charlie/app')
from flask import Flask, request, jsonify, render_template_string
from db import DB
from auth import generate_passphrase, hash_passphrase
from daemon import Daemon

DB_PATH = '/home/f42charlie/data/f42charlie.db'
PLUGINS_DIR = '/home/f42charlie/app/plugins'
PORT = 9002

app = Flask(__name__)
db = DB(DB_PATH)
daemon = Daemon(db, PLUGINS_DIR)

ADMIN_HTML = """
<!DOCTYPE html><html><head><title>f42charlie admin</title></head><body>
<h2>f42charlie — create workspace</h2>
<form method="POST">
  Name: <input name="name" required><br><br>
  Workdir: <input name="workdir" value="/home/f42charlie/workspaces/" required><br><br>
  <button type="submit">Create</button>
</form>
{% if passphrase %}
<hr>
<h3>Workspace created!</h3>
<p><b>Name:</b> {{ name }}</p>
<p><b>Passphrase:</b> <code>{{ passphrase }}</code></p>
<p><b>Workdir:</b> {{ workdir }}</p>
<p style="color:red">Save passphrase now — it won't be shown again.</p>
{% endif %}
</body></html>
"""

def mcp_response(id_, result):
    return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})

def mcp_error(id_, code, message):
    return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})

def do_step(session_id, command, argument):
    # 1. пустой session_id → новая неаутентифицированная сессия
    if not session_id:
        sid = db.create_session(None, authenticated=False)
        return sid

    # 2. проверить сессию
    session = db.get_session(session_id)
    if not session:
        sid = db.create_session(None, authenticated=False)
        return sid

    # 3. claim
    if command == "claim":
        h = hash_passphrase(argument)
        ws = db.get_workspace_by_passphrase(h)
        if ws:
            active = db.get_active_session(ws['id'])
            if active:
                resume_sid = active['session_id']
                task_id = db.create_task(resume_sid, "_echo", "_echo", "session resumed. ready.", "/tmp")
                db.set_task_running(task_id)
                db.set_result(task_id, resume_sid, "session resumed. ready.")
                db.set_task_done(task_id)
                return resume_sid
            new_sid = db.create_session(ws['id'], authenticated=True)
            db.rotate_session(session_id, new_sid)
            # auto-help after successful auth
            claim_help = """authenticated. workspace ready.

commands:
  help                          — show this message
  exec <shell command>          — run shell command in workspace
  python write <path>\\n<code>   — write Python file (path on line 1, code after \\n)
  python run <path>             — run Python file

examples:
  exec ls -la
  exec pip3 install requests -q
  python write /tmp/hello.py\\nprint('hello world')
  python run /tmp/hello.py

result always via request(session_id). poll if 'still working'."""
            task_id = db.create_task(new_sid, "_echo", "_echo", claim_help, "/tmp")
            db.set_task_running(task_id)
            db.set_result(task_id, new_sid, claim_help)
            db.set_task_done(task_id)
            return new_sid
        # неверная фраза
        new_sid = db.create_session(None, authenticated=False)
        db.rotate_session(session_id, new_sid)
        return new_sid

    # 4. help + пустая команда — результат через request()
    if command in ("help", "") or not command:
        if not session.get('authenticated'):
            help_text = "available: help, claim"
            new_sid = db.create_session(None, authenticated=False)
        else:
            help_text = "available: help, claim, exec, python"
            new_sid = db.create_session(session['workspace_id'], authenticated=True)
        db.rotate_session(session_id, new_sid)
        task_id = db.create_task(new_sid, "_echo", "_echo", help_text, "/tmp")
        db.set_task_running(task_id)
        db.set_result(task_id, new_sid, help_text)
        db.set_task_done(task_id)
        return new_sid

    # 6. проверить аутентификацию
    if not session.get('authenticated'):
        new_sid = db.create_session(None, authenticated=False)
        db.rotate_session(session_id, new_sid)
        task_id = db.create_task(new_sid, "_echo", "_echo", "not authenticated. use: claim <passphrase>", "/tmp")
        db.set_task_running(task_id)
        db.set_result(task_id, new_sid, "not authenticated. use: claim <passphrase>")
        db.set_task_done(task_id)
        return new_sid

    # 7. создать задачу для плагина
    ws = db.get_workspace(session['workspace_id'])
    if not ws:
        new_sid = db.create_session(None, authenticated=False)
        db.rotate_session(session_id, new_sid)
        task_id = db.create_task(new_sid, "_echo", "_echo", "error: workspace not found", "/tmp")
        db.set_task_running(task_id)
        db.set_result(task_id, new_sid, "error: workspace not found")
        db.set_task_done(task_id)
        return new_sid

    plugin = command
    if command in ('python',):
        sub_parts = argument.split(' ', 1)
        sub_command = sub_parts[0] if sub_parts else ''
        sub_argument = sub_parts[1] if len(sub_parts) > 1 else ''
        task_id = db.create_task(session_id, plugin, sub_command, sub_argument, ws['workdir'])
    else:
        task_id = db.create_task(session_id, plugin, command, argument, ws['workdir'])
    new_sid = db.create_session(session['workspace_id'], authenticated=True)
    db.rotate_session(session_id, new_sid, task_id)
    return new_sid

def do_request(session_id):
    if not session_id:
        return "invalid"
    result = db.get_result_by_session(session_id)
    if result is not None:
        return result
    if db.is_running(session_id):
        return "still working"
    session = db.get_session(session_id)
    if not session:
        return "invalid"
    return "still working"

@app.route('/charlie', methods=['POST'])
@app.route('/mcp', methods=['POST'])
def charlie():
    try:
        body = request.get_json()
        if not body:
            return mcp_error(None, -32700, "parse error")
        id_ = body.get('id')
        method = body.get('method', '')
        params = body.get('params', {})

        # MCP initialize
        if method == 'initialize':
            return mcp_response(id_, {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "f42charlie", "version": "0.1.0"}
            })

        if method == 'notifications/initialized':
            return '', 204

        # tools/list
        if method == 'tools/list':
                    return mcp_response(id_, {"tools": [
                {
                    "name": "step",
                    "description": (
                        "F42Charlie remote executor. Submit a command, get a new session_id.\n\n"
                        "WORKFLOW:\n"
                        "  1. step('', '', '') -> session_id\n"
                        "  2. step(sid, 'claim', 'PASSPHRASE') -> auth_sid\n"
                        "  3. step(auth_sid, CMD, ARGS) -> new_sid\n"
                        "  4. request(new_sid) -> output\n\n"
                        "COMMANDS (after claim):\n"
                        "  exec <shell>                 run shell command\n"
                        "  python write <path>\\n<code>  write Python file\n"
                        "  python run <path>            run Python file\n\n"
                        "RULES:\n"
                        "  - Always call request() after step()\n"
                        "  - Each session_id is single-use OTP\n"
                        "  - Poll request() if 'still working'\n"
                        "  - Resume: claim again -> returns active session_id\n\n"
                        "EXAMPLE:\n"
                        "  step('','','') -> 'falcon7392'\n"
                        "  step('falcon7392','claim','four word pass') -> 'river4821'\n"
                        "  step('river4821','exec','echo hello') -> 'stone2947'\n"
                        "  request('stone2947') -> 'hello'"
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Current session_id, empty string to start"},
                            "command": {"type": "string", "description": "empty/claim/exec/python"},
                            "argument": {"type": "string", "description": "passphrase for claim, shell cmd for exec"}
                        },
                        "required": ["session_id", "command", "argument"]
                    }
                },
                {
                    "name": "request",
                    "description": (
                        "F42Charlie — get result of last step().\n"
                        "Returns output | 'still working' (poll again) | 'invalid' (re-run step)."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "session_id from last step()"}
                        },
                        "required": ["session_id"]
                    }
                }
            ]})

        # tools/call
        if method == 'tools/call':
            name = params.get('name', '')
            args = params.get('arguments', {})
            if name == 'step':
                result = do_step(
                    args.get('session_id', ''),
                    args.get('command', ''),
                    args.get('argument', '')
                )
                return mcp_response(id_, {"content": [{"type": "text", "text": result}]})
            elif name == 'request':
                result = do_request(args.get('session_id', ''))
                return mcp_response(id_, {"content": [{"type": "text", "text": result}]})
            else:
                return mcp_error(id_, -32601, f"unknown tool: {name}")

        return mcp_error(id_, -32601, f"unknown method: {method}")

    except Exception as e:
        return mcp_error(None, -32603, str(e))

@app.route('/charlie/admin', methods=['GET', 'POST'])
def admin():
    passphrase = None
    name = workdir = ''
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        workdir = request.form.get('workdir', '').strip()
        if name and workdir:
            import os
            os.makedirs(workdir, exist_ok=True)
            passphrase = generate_passphrase()
            h = hash_passphrase(passphrase)
            db.create_workspace(name, workdir, h)
    return render_template_string(ADMIN_HTML, passphrase=passphrase, name=name, workdir=workdir)

if __name__ == '__main__':
    daemon.start()
    # cleanup thread
    def cleanup_loop():
        while True:
            time.sleep(86400)
            n = db.cleanup_expired()
            print(f"[cleanup] removed {n} expired records", flush=True)
    threading.Thread(target=cleanup_loop, daemon=True).start()
    print(f"[f42charlie] starting on port {PORT}", flush=True)
    app.run(host='0.0.0.0', port=PORT, debug=False)
