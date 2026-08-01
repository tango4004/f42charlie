#!/usr/bin/env python3
"""notepad/append — append text to a note. One operation."""
import sys, json, os

arg = sys.argv[2]
workdir = sys.argv[3]

data = json.loads(arg)
name = data.get('name', '')
body = data.get('body', '')

if not name:
    print('error: name required')
    sys.exit(1)

notes_dir = os.path.join(workdir, 'notes')
note_path = os.path.join(notes_dir, name + '.txt')
os.makedirs(notes_dir, exist_ok=True)

with open(note_path, 'a') as f:
    f.write(body)
print(f'ok: appended {len(body)} bytes to {name}')
