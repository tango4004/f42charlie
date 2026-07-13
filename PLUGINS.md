# F42Charlie — Plugin Development Guide

Plugins are Python scripts in `plugins/`. The daemon calls them as subprocesses.

## Interface

```
python3 plugins/myplugin.py <command> <argument> <workdir>
```

- `command` — subcommand (e.g. `run`, `write`, `query`)
- `argument` — everything after the command
- `workdir` — workspace directory for this session
- Output goes to **stdout** — that's what the user gets back
- Errors go to **stderr** — appended to output with `[stderr]` prefix

## Minimal plugin

```python
# plugins/hello.py
import sys

command  = sys.argv[1] if len(sys.argv) > 1 else ""
argument = sys.argv[2] if len(sys.argv) > 2 else ""
workdir  = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

if command == "say":
    print(f"Hello, {argument}!")
else:
    print(f"error: unknown command '{command}'. use: say")
```

Usage: `payload="hello say world"` → `Hello, world!`

## Shell plugin example

```python
# plugins/exec.py
import sys, subprocess

command = sys.argv[1] if len(sys.argv) > 1 else ""
argument = sys.argv[2] if len(sys.argv) > 2 else ""
workdir  = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

full_cmd = f"{command} {argument}".strip()
try:
    r = subprocess.run(full_cmd, shell=True, cwd=workdir,
                       capture_output=True, text=True, timeout=30)
    print(r.stdout, end="")
    if r.stderr:
        print("\n[stderr]\n" + r.stderr, end="")
except subprocess.TimeoutExpired:
    print("error: timeout")
except Exception as e:
    print(f"error: {e}")
```

## Rules

- Always handle missing/unknown `command` gracefully — print `error: ...`
- Use `workdir` as the working directory for file operations
- Plugin knows nothing about sessions, auth, or the database
- Timeout: daemon kills plugin after 60 seconds
- Exit code is ignored — output is what matters
- Keep it stateless: no files outside `workdir` unless explicitly needed

## Registering a plugin

Drop `myplugin.py` into `plugins/`. No registration needed — daemon finds it by name.

Call it: `payload="myplugin <command> <argument>"`

## Built-in plugins

| Plugin | Commands | Example payload |
|--------|----------|-----------------|
| `exec` | any shell cmd | `exec ls -la` |
| `python` | `write`, `run` | `python write /tmp/x.py\nprint(1)` |
