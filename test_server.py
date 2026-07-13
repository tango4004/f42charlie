import sys, time
sys.path.insert(0, '/home/f42charlie/app')
from db import DB
from auth import generate_passphrase, hash_passphrase
from daemon import Daemon
from server import app, db as server_db, daemon as server_daemon

# использовать in-memory db для теста
test_db = DB(':memory:')
phrase = generate_passphrase()
ws_id = test_db.create_workspace('testws', '/tmp', hash_passphrase(phrase))

# подменить db в server
import server
server.db = test_db
server_daemon.stop()
test_daemon = Daemon(test_db)
test_daemon.start()
server.daemon = test_daemon

c = app.test_client()

def mcp(name, args):
    return c.post('/charlie', json={
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": args}
    })

def parse(r):
    return r.get_json()['result']['content'][0]['text']

# T1: start session
r = mcp('step', {'session_id': '', 'command': '', 'argument': ''})
sid1 = parse(r)
assert sid1 and sid1[-4:].isdigit(), f"T1 failed: {sid1}"
print(f"T1 OK: new session {sid1}")

# T2: help (unauthenticated)
r = mcp('step', {'session_id': sid1, 'command': 'help', 'argument': ''})
resp = parse(r)
sid2 = resp.split()[0]
assert 'claim' in resp, f"T2 failed: {resp}"
print(f"T2 OK: help = {resp}")

# T3: claim wrong passphrase
r = mcp('step', {'session_id': sid2, 'command': 'claim', 'argument': 'wrong phrase here now'})
sid3 = parse(r)
assert sid3, f"T3 failed: {sid3}"
print(f"T3 OK: wrong claim → new sid {sid3}")

# T4: claim correct passphrase
r = mcp('step', {'session_id': sid3, 'command': 'claim', 'argument': phrase})
sid4 = parse(r)
assert sid4 and sid4 != sid3, f"T4 failed: {sid4}"
print(f"T4 OK: authenticated {sid4}")

# T5: exec echo
r = mcp('step', {'session_id': sid4, 'command': 'exec', 'argument': 'echo f42charlie works'})
sid5 = parse(r)
assert sid5, f"T5 failed: {sid5}"
print(f"T5 OK: task created, new sid {sid5}")

# T6: request result
for i in range(10):
    time.sleep(0.5)
    r = mcp('request', {'session_id': sid5})
    result = parse(r)
    if result not in ('still working', 'invalid'):
        break
assert 'f42charlie works' in result, f"T6 failed: {result}"
print(f"T6 OK: result = {result.strip()}")

# T7: старый sid → invalid
r = mcp('request', {'session_id': sid4})
assert parse(r) == 'invalid', f"T7 failed: {parse(r)}"
print("T7 OK: old sid → invalid")

# T8: resume session (claim снова)
r = mcp('step', {'session_id': sid5, 'command': 'claim', 'argument': phrase})
sid_resume = parse(r)
assert sid_resume == sid5, f"T8 failed: expected {sid5}, got {sid_resume}"
print(f"T8 OK: resume → same sid {sid_resume}")

test_daemon.stop()
print("ALL TESTS PASSED")
