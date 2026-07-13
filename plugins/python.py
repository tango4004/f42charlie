import sys, subprocess, os

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    argument = sys.argv[2] if len(sys.argv) > 2 else ""
    workdir = sys.argv[3] if len(sys.argv) > 3 else "/tmp"

    if command == "write":
        # первая строка argument = путь к файлу
        # остальное = код
        lines = argument.split("\n", 1)
        if len(lines) < 2:
            print("error: write requires path\\ncode")
            return
        path = lines[0].strip()
        code = lines[1]
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else workdir, exist_ok=True)
        with open(path, "w") as f:
            f.write(code)
        print(f"written: {path}")

    elif command == "run":
        path = argument.strip()
        try:
            r = subprocess.run(
                ["python3", path], cwd=workdir,
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

    else:
        print(f"error: unknown command '{command}'. use: write, run")

if __name__ == "__main__":
    main()
