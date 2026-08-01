#!/usr/bin/env python3
"""notepad/erase — delete a note. One operation."""
import sys, json, os

arg = sys.argv[2]
workdir = sys.argv[3]

data = json.loads(arg)
name = data.get('name', '')

if not name:
    print('error: name required')
    sys.exit(1)

note_path = os.path.join(workdir, 'notes', name + '.txt')
if os.path.exists(note_path):
    os.remove(note_path)
    print(f'ok: erased {name}')
else:
    print(f'ok: {name} did not exist (noop)')
