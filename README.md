# f42charlie

MCP server with OTP session chain, plugin architecture, and async task execution.

## Architecture

```
claude.ai → MCP → bridge (mcp_server.py) → f42charlie (server.py) → daemon → plugins/
```

## Protocol

Two MCP tools: `request` and `report`.

```
# Submit job
job_id = request(dst="your passphrase", task="run", payload="exec echo hello")

# Poll result
output = report(job_id=job_id, stream="stdout")
# → "hello" | "still working" | "invalid"
```

## Session flow (OTP chain)

```
step("", "", "")              → session_id (unauthenticated)
step(sid, "claim", passphrase) → authenticated session_id
step(sid, "exec", "ls -la")   → new_sid (task queued)
request(new_sid)               → "still working" | result
```

Session IDs are single-use OTPs: `word1234` format from a 41k word dictionary.

## Plugins

| Command | Plugin | Usage |
|---------|--------|-------|
| `exec` | `plugins/exec.py` | `exec ls -la` |
| `python write` | `plugins/python.py` | `python write /path/file.py\ncode here` |
| `python run` | `plugins/python.py` | `python run /path/file.py` |

## Install

```bash
# Create user
sudo useradd -m -s /bin/bash f42charlie

# Clone
sudo -u f42charlie git clone https://github.com/tango4004/f42charlie /home/f42charlie/app

# Install deps
pip3 install flask python-dotenv

# Create workspace
curl -X POST http://localhost:9002/charlie/admin \
  -d "name=myws&workdir=/home/f42charlie/workspaces/myws"

# Run
sudo systemctl start f42charlie
```

## systemd

```ini
[Unit]
Description=F42Charlie MCP Server
After=network.target

[Service]
User=f42charlie
WorkingDirectory=/home/f42charlie/app
ExecStart=/usr/bin/python3 -u server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Database

SQLite at `/home/f42charlie/data/f42charlie.db`:
- `workspaces` — name, workdir, passphrase_hash
- `sessions` — OTP chain, TTL 30 days
- `tasks` — plugin queue, status: pending→running→done
- `results` — output cache, TTL 1 day

## MCP endpoint

`https://c2.tango4004.com/mcp`
