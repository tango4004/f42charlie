import sys, subprocess, os

command  = sys.argv[1] if len(sys.argv) > 1 else ""
argument = sys.argv[2] if len(sys.argv) > 2 else ""
workdir  = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

if command.strip() == "help" or argument.strip() == "help":
    print("""python — write and run Python files in workspace

usage:
  step(session_id, "python", "write <path>\\n<code>")
  step(session_id, "python", "run <path>")

examples:
  step(sid, "python", "write /home/f42charlie/workspaces/amd2/hello.py\\nprint('hello')")
  step(sid, "python", "run /home/f42charlie/workspaces/amd2/hello.py")

  step(sid, "python", "write /home/f42charlie/workspaces/amd2/calc.py\\nimport math\\nprint(math.pi)")
  step(sid, "python", "run /home/f42charlie/workspaces/amd2/calc.py")

operations:
  write <path>\\n<code>   write code to file (path on first line, code after newline)
  run <path>             execute python file, return stdout/stderr

notes:
  - files persist in workspace between sessions
  - timeout: 30 seconds
  - use workspace path for persistent files""")
    sys.exit(0)

if command == "write":
    lines = argument.split("\n", 1)
    if len(lines) < 2:
        print("error: write requires path\\ncode")
        sys.exit(1)
    path = lines[0].strip()
    code = lines[1]
    dirpath = os.path.dirname(path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    with open(path, "w") as f:
        f.write(code)
    print(f"written: {path}")

elif command == "run":
    path = argument.strip()
    try:
        r = subprocess.run(["python3", path], cwd=workdir,
            capture_output=True, text=True, timeout=30)
        output = r.stdout
        if r.stderr:
            output += "\n[stderr]\n" + r.stderr
        print(output, end="")
    except subprocess.TimeoutExpired:
        print("error: timeout (30s)")
    except Exception as e:
        print(f"error: {e}")

else:
    print(f"error: unknown operation '{command}'. use: write, run, help")
