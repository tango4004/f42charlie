import sys, subprocess

command = sys.argv[1] if len(sys.argv) > 1 else ""
argument = sys.argv[2] if len(sys.argv) > 2 else ""
workdir  = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

if argument.strip() == "help":
    print("""exec — run shell commands in workspace

usage:
  step(session_id, "exec", "<shell command>")

examples:
  step(sid, "exec", "ls -la")
  step(sid, "exec", "pip3 install requests -q")
  step(sid, "exec", "cat /path/to/file")
  step(sid, "exec", "echo hello world")

notes:
  - runs in workspace directory
  - stdout and stderr returned via request()
  - timeout: 30 seconds
  - no sudo""")
    sys.exit(0)

if not command:
    print("error: no command. usage: step(sid, \"exec\", \"<shell command>\")")
    sys.exit(1)

full_cmd = f"{command} {argument}".strip()
try:
    r = subprocess.run(full_cmd, shell=True, cwd=workdir,
        capture_output=True, text=True, timeout=30)
    output = r.stdout
    if r.stderr:
        output += "\n[stderr]\n" + r.stderr
    print(output, end="")
except subprocess.TimeoutExpired:
    print("error: timeout (30s)")
except Exception as e:
    print(f"error: {e}")
