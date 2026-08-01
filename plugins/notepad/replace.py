#!/usr/bin/env python3
"""notepad/replace — replace text in a note. One operation."""
import sys, json, os

arg = sys.argv[2]
workdir = sys.argv[3]

data = json.loads(arg)
name = data.get('name', '')
old = data.get('old', '')
new = data.get('new', '')

if not name:
    print('error: name required')
    sys.exit(1)

note_path = os.path.join(workdir, 'notes', name + '.txt')
if not os.path.exists(note_path):
    print(f'error: note "{name}" not found')
    sys.exit(1)

with open(note_path, 'r') as f:
    content = f.read()

count = content.count(old)
if count == 0:
    print(f'ok: no occurrences of "{old}" in {name}')
    sys.exit(0)

content = content.replace(old, new)
with open(note_path, 'w') as f:
    f.write(content)
print(f'ok: replaced {count} occurrence(s) in {name}')
