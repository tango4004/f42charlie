import sys, subprocess

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    argument = sys.argv[2] if len(sys.argv) > 2 else ""
    workdir = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

    if not command:
        print("error: no command")
        return

    full_cmd = f"{command} {argument}".strip()
    try:
        r = subprocess.run(
            full_cmd, shell=True, cwd=workdir,
            capture_output=True, text=True, timeout=30
        )
        output = r.stdout
        if r.stderr:
            output += "\n[stderr]\n" + r.stderr
        print(output, end="")
    except subprocess.TimeoutExpired:
        print("error: timeout")
    except Exception as e:
        print(f"error: {e}")

if __name__ == "__main__":
    main()
