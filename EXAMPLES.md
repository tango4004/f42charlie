# F42Charlie — Usage Examples

All examples use `request()` + `report()` via MCP.
Replace `"your four word passphrase"` with your actual passphrase.

---

## 1. Hello World

```python
job_id = request(
    dst="your four word passphrase",
    task="run",
    payload="exec echo hello from f42charlie"
)
result = report(job_id=job_id, stream="stdout")
# → "hello from f42charlie"
```

---

## 2. Write and run Python

```python
# Write the file
job_id = request(
    dst="your four word passphrase",
    task="run",
    payload="python write /home/f42charlie/workspaces/myws/calc.py\ndef add(a, b): return a + b\nprint(add(3, 4))"
)
report(job_id=job_id, stream="stdout")
# → "written: /home/f42charlie/workspaces/myws/calc.py"

# Run it
job_id = request(
    dst="your four word passphrase",
    task="run",
    payload="python run /home/f42charlie/workspaces/myws/calc.py"
)
result = report(job_id=job_id, stream="stdout")
# → "7"
```

---

## 3. Install a package and use it

```python
# Install
job_id = request(dst=PASSPHRASE, task="run", payload="exec pip3 install requests -q")
report(job_id=job_id, stream="stdout")

# Write script
job_id = request(
    dst=PASSPHRASE, task="run",
    payload="python write /home/f42charlie/workspaces/myws/fetch.py\nimport requests\nr = requests.get('https://httpbin.org/get')\nprint(r.status_code)"
)
report(job_id=job_id, stream="stdout")

# Run
job_id = request(dst=PASSPHRASE, task="run", payload="python run /home/f42charlie/workspaces/myws/fetch.py")
result = report(job_id=job_id, stream="stdout")
# → "200"
```

---

## 4. Poll for slow jobs

```python
import time

job_id = request(dst=PASSPHRASE, task="run", payload="exec sleep 5 && echo done")

for i in range(30):
    result = report(job_id=job_id, stream="stdout")
    if result == "still working":
        time.sleep(2)
        continue
    break

print(result)  # → "done"
```

---

## 5. Check environment

```python
for cmd in ["exec whoami", "exec pwd", "exec python3 --version", "exec df -h ."]:
    job_id = request(dst=PASSPHRASE, task="run", payload=cmd)
    print(cmd, "→", report(job_id=job_id, stream="stdout").strip())
```

---

## 6. Multi-file project

```python
files = {
    "main.py": "from utils import greet\nprint(greet('world'))",
    "utils.py": "def greet(name): return f'Hello, {name}!'"
}

base = "/home/f42charlie/workspaces/myws"

for fname, code in files.items():
    job_id = request(dst=PASSPHRASE, task="run",
        payload=f"python write {base}/{fname}\n{code}")
    report(job_id=job_id, stream="stdout")

job_id = request(dst=PASSPHRASE, task="run", payload=f"python run {base}/main.py")
print(report(job_id=job_id, stream="stdout"))
# → "Hello, world!"
```

---

## Error handling

```python
job_id = request(dst=PASSPHRASE, task="run", payload="exec cat /nonexistent")
result = report(job_id=job_id, stream="stdout")
# result starts with "[stderr]" or contains error text

if result.startswith("error:") or "[stderr]" in result:
    print("Command failed:", result)
```
