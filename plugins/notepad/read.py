#!/usr/bin/env python3
"""notepad/read — read text from a note. One operation."""
import sys, json, os

arg = sys.argv[2]
workdir = sys.argv[3]

data = json.loads(arg)
name = data.get('name', '')

if not name:
    print('error: name required')
    sys.exit(1)

note_path = os.path.join(workdir, 'notes', name + '.txt')
if not os.path.exists(note_path):
    print(f'error: note "{name}" not found')
    sys.exit(1)

with open(note_path, 'r') as f:
    print(f.read())
