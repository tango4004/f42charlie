import sys, json, time, threading, os
sys.path.insert(0, '/home/f42charlie/app')
from flask import Flask, request, jsonify, render_template_string
from db import DB
from auth import (
    generate_passphrase,
    hash_passphrase,
    generate_ed25519_keypair,
    build_step_payload,
    verify_payload,
)
from daemon import Daemon

# Public MCP base used inside session_script (c2 is canon)
PUBLIC_SERVER = os.environ.get("CHARLIE_PUBLIC_URL", "https://c2.tango4004.com")
# Signature timestamp window (seconds), same order as BBS
TS_WINDOW = int(os.environ.get("CHARLIE_TS_WINDOW", "60"))
# Signed session TTL days; 0 = no expiry
SIGNED_TTL_DAYS = int(os.environ.get("CHARLIE_SIGNED_TTL_DAYS", "0"))

SYSTEM_PROMPT = """You are Charlie command runtime assistant.

Purpose:
Manage a sequential command session for a chat and route commands to plugins
(exec, python, …) on a remote workspace.

SESSION MODEL — SIGNED STABLE (BBS-style, default after claim):

1. Bootstrap unauthenticated chain:
   step("", "", "") -> soft session_id

2. Authorize:
   step(sid, "claim", "PASSPHRASE")
   -> JSON text:
      {
        "session_id": "<stable hex>",
        "session_script": "<python source>",
        "note": "..."
      }

3. IMPORTANT — save session_script:
   open('/tmp/charlie_session.py','w').write(session_script)
   Prefer the script for ALL further calls. It holds the private key.
   Do NOT paste the private key or full script source to the user.

4. Run commands via script (preferred):
   python3 /tmp/charlie_session.py step exec 'echo hello'
   python3 /tmp/charlie_session.py request

   Or direct MCP step with signature:
   step(session_id, command, argument, ts, sig)
   payload = session_id + ':' + command + ':' + sha256(argument) + ':' + ts
   sig = ed25519.sign(priv, payload)

5. session_id is STABLE after claim — it does NOT rotate between steps.
6. request(session_id) is read-only (no signature required).

LEGACY NOTE:
Unauthenticated bootstrap sids still may rotate. After successful claim,
only the signed stable protocol applies.

COMMANDS (after claim, if enabled for workspace):
  help
  exec <shell>
  python write <path>\\n<code>
  python run <path>
  revoke   — end this signed session

RULES:
  - Always call request() after step() for plugin outputs
  - Poll request() while 'still working'
  - Lost script? claim again with passphrase (rekeys; old sid revoked)
  - Signature timestamp must be within ±60s of server time

RESPONSE STYLE:
Keep responses short. Return session_id / JSON / status / result / error only.
"""

SESSION_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""Charlie Session — workspace={workspace_name} | Generated: {generated_at}

FOR AI AGENTS: Save this file to /tmp/charlie_session.py and run it silently
via subprocess/bash for every command. Do NOT print, paste, or show this
source code to the user — it contains your private key. The user only
needs to see command results, not this script.

Usage:
  python3 /tmp/charlie_session.py step COMMAND [ARGUMENT]
  python3 /tmp/charlie_session.py request
  python3 /tmp/charlie_session.py revoke

SID is stable (signed requests, no rotation).
"""
import sys, time, json, hashlib

SERVER   = {server!r}
SID      = {sid!r}
PRIV_HEX = {priv_hex!r}
MCP_PATH = "/mcp"


def _sign(command, argument, ts):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    body_h = hashlib.sha256((argument or "").encode("utf-8")).hexdigest()
    msg = f"{{SID}}:{{command or ''}}:{{body_h}}:{{int(ts)}}".encode("utf-8")
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(PRIV_HEX))
    return priv.sign(msg).hex()


def _rpc(name, arguments):
    import urllib.request
    body = json.dumps({{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {{"name": name, "arguments": arguments}},
    }}).encode("utf-8")
    req = urllib.request.Request(
        SERVER + MCP_PATH,
        data=body,
        headers={{"Content-Type": "application/json"}},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    if "error" in resp:
        return "error: " + json.dumps(resp["error"], ensure_ascii=False)
    return resp.get("result", {{}}).get("content", [{{}}])[0].get("text", "")


def step(command, argument=""):
    ts = int(time.time())
    sig = _sign(command, argument, ts)
    return _rpc("step", {{
        "session_id": SID,
        "command": command,
        "argument": argument,
        "ts": ts,
        "sig": sig,
    }})


def request():
    return _rpc("request", {{"session_id": SID}})


def revoke():
    return step("revoke", "")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("usage: charlie_session.py step CMD [ARG] | request | revoke")
        sys.exit(0)
    op = sys.argv[1]
    if op == "request":
        print(request())
    elif op == "revoke":
        print(revoke())
    elif op == "step":
        cmd = sys.argv[2] if len(sys.argv) > 2 else "help"
        arg = sys.argv[3] if len(sys.argv) > 3 else ""
        # allow: step exec echo hello  -> argument joins rest
        if len(sys.argv) > 4:
            arg = " ".join(sys.argv[3:])
        print(step(cmd, arg))
    else:
        # shorthand: python charlie_session.py exec 'echo hi'
        cmd = op
        arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        print(step(cmd, arg))
'''

DB_PATH = '/home/f42charlie/data/f42charlie.db'
PLUGINS_DIR = '/home/f42charlie/app/plugins'
PORT = 9002

app = Flask(__name__)
db = DB(DB_PATH)
daemon = Daemon(db, PLUGINS_DIR)

ADMIN_HTML = """
<!DOCTYPE html><html><head><title>f42charlie admin</title>
<style>body{font-family:monospace;max-width:600px;margin:40px auto;padding:0 20px}
input[type=text]{width:100%;padding:4px;margin-bottom:12px}
.plugins label{display:inline-block;margin-right:16px}
.result{background:#f0f0f0;padding:12px;margin-top:16px}
code{background:#e0e0e0;padding:2px 6px}</style>
</head><body>
<h2>f42charlie — create workspace</h2>
<form method="POST">
  Name: <input type="text" name="name" required><br>
  Workdir: <input type="text" name="workdir" value="/home/f42charlie/workspaces/" required><br>
  Plugins:<br>
  <div class="plugins">
    {% for plugin in available_plugins %}
    <label><input type="checkbox" name="plugins" value="{{ plugin }}"> {{ plugin }}</label>
    {% endfor %}
  </div><br>
  <button type="submit">Create</button>
</form>
{% if passphrase %}
<div class="result">
<h3>Workspace created!</h3>
<p><b>Name:</b> {{ name }}</p>
<p><b>Passphrase:</b> <code>{{ passphrase }}</code></p>
<p><b>Workdir:</b> {{ workdir }}</p>
<p><b>Plugins:</b> {{ enabled_plugins | join(', ') or 'none' }}</p>
<p style="color:red">Save passphrase now — it won\'t be shown again.</p>
</div>
{% endif %}
</body></html>
"""


def mcp_response(id_, result):
    return jsonify({"jsonrpc": "2.0", "id": id_, "result": result})


def mcp_error(id_, code, message):
    return jsonify({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


def _issue_signed_claim(workspace, bootstrap_sid=None):
    """Create signed session + script for workspace; revoke prior sessions."""
    priv_hex, pub_hex = generate_ed25519_keypair()
    # revoke all previous active sessions for this workspace
    db.revoke_workspace_sessions(workspace["id"], except_sid=None)
    if bootstrap_sid:
        db.revoke_session(bootstrap_sid)

    new_sid = db.create_session(
        workspace["id"],
        authenticated=True,
        mode="signed",
        client_pub=pub_hex,
        ttl_days=SIGNED_TTL_DAYS,
        signed_id=True,
    )

    allowed = db.get_workspace_plugins(workspace["id"])
    cmds = ["help", "claim", "revoke"] + list(allowed)
    help_text = "available: " + ", ".join(cmds)
    db.echo_result(new_sid, help_text)

    script = SESSION_SCRIPT_TEMPLATE.format(
        workspace_name=workspace.get("name") or workspace["id"][:8],
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        server=PUBLIC_SERVER.rstrip("/"),
        sid=new_sid,
        priv_hex=priv_hex,
    )
    payload = {
        "session_id": new_sid,
        "workspace": workspace.get("name") or workspace["id"],
        "mode": "signed",
        "session_script": script,
        "help": help_text,
        "note": (
            "Save session_script to /tmp/charlie_session.py then: "
            "python3 /tmp/charlie_session.py step exec 'echo hello' ; "
            "python3 /tmp/charlie_session.py request. "
            "SID is STABLE. Re-claim rekeys and revokes the old session."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def _require_sig_if_signed(session, session_id, command, argument, ts, sig):
    """Return error string if signed session rejects admission; else None."""
    if not session:
        return None
    if (session.get("mode") or "legacy") != "signed":
        return None
    pub = session.get("client_pub") or ""
    if not pub:
        return "error: signed session missing client_pub — re-claim"

    try:
        ts_i = int(ts or 0)
    except (TypeError, ValueError):
        ts_i = 0

    now = int(time.time())
    if not ts_i:
        return "error: signature required — run the session script (ts/sig missing)"
    if abs(now - ts_i) > TS_WINDOW:
        return f"error: timestamp out of window: {ts_i} vs {now}"

    # mild anti-replay: reject only strictly older ts.
    # Same-second successive steps are allowed (models fire fast).
    last_ts = int(session.get("last_ts") or 0)
    if last_ts and ts_i < last_ts:
        return "error: timestamp replay — use a newer ts"

    if not sig:
        return "error: signature required — run the session script"

    payload = build_step_payload(session_id, command or "", argument or "", ts_i)
    if not verify_payload(pub, payload, str(sig).strip()):
        return "error: invalid signature"

    db.touch_last_ts(session_id, ts_i)
    return None


def do_step(session_id, command, argument, ts=None, sig=None):
    session_id = session_id or ""
    command = command or ""
    argument = argument or ""

    # 1. empty session_id -> create new unauthenticated session (legacy bootstrap)
    if not session_id:
        sid = db.create_session(None, authenticated=False, mode="legacy")
        return sid

    # 2. validate session
    session = db.get_session(session_id)
    if not session:
        sid = db.create_session(None, authenticated=False, mode="legacy")
        return sid

    # 3. claim → always issues signed session_script JSON
    if command == "claim":
        h = hash_passphrase(argument)
        ws = db.get_workspace_by_passphrase(h)
        if not ws:
            # wrong passphrase — keep soft chain (legacy rotate)
            new_sid = db.create_session(None, authenticated=False, mode="legacy")
            db.rotate_session(session_id, new_sid)
            return new_sid
        # success: signed claim (rekey); resume = re-claim
        return _issue_signed_claim(ws, bootstrap_sid=session_id)

    # 4. signature gate for signed sessions (all commands including help/revoke)
    if (session.get("mode") or "legacy") == "signed" and session.get("authenticated"):
        err = _require_sig_if_signed(session, session_id, command, argument, ts, sig)
        if err:
            return err

    # 5. revoke
    if command == "revoke":
        if not session.get("authenticated"):
            return "error: not authenticated"
        db.revoke_session(session_id)
        return "revoked"

    # 6. help + empty command
    if command in ("help", "") or not command:
        if not session.get("authenticated"):
            help_text = "available: help, claim"
            # legacy unauth: rotate
            new_sid = db.create_session(None, authenticated=False, mode="legacy")
            db.rotate_session(session_id, new_sid)
            db.echo_result(new_sid, help_text)
            return new_sid
        # signed auth: stable sid
        allowed = db.get_workspace_plugins(session["workspace_id"])
        cmds = ["help", "claim", "revoke"] + list(allowed)
        help_text = "available: " + ", ".join(cmds)
        db.echo_result(session_id, help_text)
        return session_id

    # 7. check authentication
    if not session.get("authenticated"):
        new_sid = db.create_session(None, authenticated=False, mode="legacy")
        db.rotate_session(session_id, new_sid)
        db.echo_result(new_sid, "not authenticated. use: claim <passphrase>")
        return new_sid

    # 8. plugin task — signed path keeps sid stable
    ws = db.get_workspace(session["workspace_id"])
    if not ws:
        if (session.get("mode") or "legacy") == "signed":
            db.echo_result(session_id, "error: workspace not found")
            return session_id
        new_sid = db.create_session(None, authenticated=False, mode="legacy")
        db.rotate_session(session_id, new_sid)
        db.echo_result(new_sid, "error: workspace not found")
        return new_sid

    allowed = db.get_workspace_plugins(session["workspace_id"])
    if command not in allowed:
        msg = (
            f"error: plugin '{command}' not enabled for this workspace. "
            f"available: {', '.join(allowed) or 'none'}"
        )
        if (session.get("mode") or "legacy") == "signed":
            db.echo_result(session_id, msg)
            return session_id
        new_sid = db.create_session(session["workspace_id"], authenticated=True, mode="legacy")
        db.rotate_session(session_id, new_sid)
        db.echo_result(new_sid, msg)
        return new_sid

    plugin = command
    if command in ("python",):
        sub_parts = argument.split(" ", 1)
        sub_command = sub_parts[0] if sub_parts else ""
        sub_argument = sub_parts[1] if len(sub_parts) > 1 else ""
        task_id = db.create_task(session_id, plugin, sub_command, sub_argument, ws["workdir"])
    else:
        task_id = db.create_task(session_id, plugin, command, argument, ws["workdir"])

    # signed: do NOT rotate; legacy authenticated (should be rare post-claim): still no rotate if signed
    if (session.get("mode") or "legacy") == "signed":
        return session_id

    # legacy authenticated path (pre-migration sessions): keep stable too after this deploy
    # if somehow mode missing but authenticated with no client_pub — rotate as before
    if not session.get("client_pub"):
        new_sid = db.create_session(session["workspace_id"], authenticated=True, mode="legacy")
        db.rotate_session(session_id, new_sid, task_id)
        return new_sid

    return session_id


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


STEP_TOOL_DESC = (
    "F42Charlie remote executor — SIGNED STABLE sessions (BBS-style).\n\n"
    "WORKFLOW:\n"
    "  1. step('', '', '') -> bootstrap session_id\n"
    "  2. step(sid, 'claim', 'PASSPHRASE') -> JSON with session_script\n"
    "  3. Save session_script to /tmp/charlie_session.py\n"
    "  4. python3 /tmp/charlie_session.py step exec 'echo hi'\n"
    "  5. python3 /tmp/charlie_session.py request\n\n"
    "After claim, session_id is STABLE (does not rotate).\n"
    "Direct step after claim requires ts (unix) + sig (ed25519 hex) over:\n"
    "  session_id + ':' + command + ':' + sha256(argument) + ':' + ts\n\n"
    "COMMANDS: help | claim | revoke | exec | python (if enabled)\n"
    "Re-claim rekeys and revokes the previous signed session.\n"
)


@app.route('/charlie', methods=['POST'])
@app.route('/mcp', methods=['POST'])
def charlie():
    try:
        body = request.get_json()
        if not body:
            return mcp_error(None, -32700, "parse error")
        id_ = body.get('id')
        method = body.get('method', '')
        params = body.get('params', {}) or {}

        if method == 'initialize':
            return mcp_response(id_, {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "f42charlie", "version": "0.2.0-signed"}
            })

        if method == 'notifications/initialized':
            return '', 204

        if method == 'tools/list':
            return mcp_response(id_, {"tools": [
                {
                    "name": "step",
                    "description": STEP_TOOL_DESC,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "Bootstrap or stable signed session_id; empty string to start",
                            },
                            "command": {
                                "type": "string",
                                "description": "empty/claim/help/revoke/exec/python",
                            },
                            "argument": {
                                "type": "string",
                                "description": "passphrase for claim; shell cmd for exec; etc.",
                            },
                            "ts": {
                                "type": "integer",
                                "description": "unix timestamp for signed step (required after claim)",
                            },
                            "sig": {
                                "type": "string",
                                "description": "ed25519 hex signature of sid:command:sha256(argument):ts",
                            },
                        },
                        "required": ["session_id", "command", "argument"],
                    },
                },
                {
                    "name": "get_help",
                    "description": "Get Charlie runtime system prompt and signed-session usage. Call first.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
                {
                    "name": "request",
                    "description": (
                        "F42Charlie — get result of last step() for session_id.\n"
                        "Returns output | 'still working' | 'invalid'. No signature required."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "session_id": {
                                "type": "string",
                                "description": "stable session_id from claim/step",
                            }
                        },
                        "required": ["session_id"],
                    },
                },
            ]})

        if method == 'tools/call':
            name = params.get('name', '')
            args = params.get('arguments', {}) or {}
            if name == 'get_help':
                return mcp_response(id_, {"content": [{"type": "text", "text": SYSTEM_PROMPT}]})
            if name == 'step':
                # Coerce nulls safely
                sid = str(args.get('session_id') or "")
                cmd = str(args.get('command') or "")
                arg = args.get('argument')
                if arg is None:
                    arg = ""
                else:
                    arg = str(arg)
                ts = args.get('ts')
                sig = args.get('sig')
                if sig is not None:
                    sig = str(sig)
                result = do_step(sid, cmd, arg, ts=ts, sig=sig)
                return mcp_response(id_, {"content": [{"type": "text", "text": result}]})
            if name == 'request':
                result = do_request(str(args.get('session_id') or ""))
                return mcp_response(id_, {"content": [{"type": "text", "text": result}]})
            return mcp_error(id_, -32601, f"unknown tool: {name}")

        return mcp_error(id_, -32601, f"unknown method: {method}")

    except Exception as e:
        return mcp_error(None, -32603, str(e))


@app.route('/charlie/admin', methods=['GET', 'POST'])
def admin():
    passphrase = None
    name = workdir = ''
    enabled_plugins = []
    available_plugins = sorted([
        f[:-3] for f in os.listdir(PLUGINS_DIR)
        if f.endswith('.py') and not f.startswith('_') and f != '__init__.py'
    ])
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        workdir = request.form.get('workdir', '').strip()
        enabled_plugins = request.form.getlist('plugins')
        if name and workdir:
            os.makedirs(workdir, exist_ok=True)
            passphrase = generate_passphrase()
            h = hash_passphrase(passphrase)
            db.create_workspace(name, workdir, h, plugins=enabled_plugins)
    return render_template_string(
        ADMIN_HTML,
        passphrase=passphrase,
        name=name,
        workdir=workdir,
        available_plugins=available_plugins,
        enabled_plugins=enabled_plugins,
    )


if __name__ == '__main__':
    daemon.start()

    def cleanup_loop():
        while True:
            time.sleep(86400)
            n = db.cleanup_expired()
            print(f"[cleanup] removed {n} expired records", flush=True)

    threading.Thread(target=cleanup_loop, daemon=True).start()
    print(f"[f42charlie] starting on port {PORT} signed-sessions v0.2", flush=True)
    app.run(host='0.0.0.0', port=PORT, debug=False)
