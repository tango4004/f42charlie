import sys, subprocess, re

argument = sys.argv[2] if len(sys.argv) > 2 else ""

if argument.strip() in ("help", ""):
    print("""bbs_otp — generate OTP for F42BBS points

usage:
  step(session_id, "bbs_otp", "<node> <addr>")

  node: 1 = ARM1 (foxtrot42.org)  points 1:42/1.*
        2 = ARM2 (tango4004.com)   points 1:42/2.*
  addr: point address e.g. 1:42/1.8 or 1:42/2.1

examples:
  step(sid, "bbs_otp", "1 1:42/1.8")
  step(sid, "bbs_otp", "2 1:42/2.1")""")
    sys.exit(0)

parts = argument.strip().split()
if len(parts) < 2:
    print("usage: bbs_otp <node> <addr>")
    sys.exit(1)

node, addr = parts[0], parts[1]

if node == "1":
    cmd = f"ssh -o StrictHostKeyChecking=no f42agent@129.146.128.5 f42bbs-admin genotp {addr}"
elif node == "2":
    cmd = f"ssh -o StrictHostKeyChecking=no f42agent@129.146.255.186 f42bbs-admin genotp {addr}"
else:
    print(f"unknown node: {node}  (use 1 or 2)")
    sys.exit(1)

try:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    m = re.search(r'^\s{2}([a-z]+ [a-z]+ [a-z]+ [a-z]+)\s*$', output, re.MULTILINE)
    if m:
        otp = m.group(1)
        print(f"OTP for {addr} (node {node}, valid 1h):")
        print(f"  {otp}")
        print(f"bbs_claim(otp='{otp}')")
    else:
        print(f"error:\n{output[:300]}")
except subprocess.TimeoutExpired:
    print("error: timeout")
except Exception as e:
    print(f"error: {e}")
