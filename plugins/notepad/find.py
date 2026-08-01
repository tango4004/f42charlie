#!/usr/bin/env python3
"""notepad/find — find lines matching pattern in a note. One operation."""
import sys, json, os

arg = sys.argv[2]
workdir = sys.argv[3]

data = json.loads(arg)
name = data.get('name', '')
pattern = data.get('pattern', '')

if not name:
    print('error: name required')
    sys.exit(1)

note_path = os.path.join(workdir, 'notes', name + '.txt')
if not os.path.exists(note_path):
    print(f'error: note "{name}" not found')
    sys.exit(1)

with open(note_path, 'r') as f:
    lines = f.readlines()

matches = [(i+1, line.rstrip()) for i, line in enumerate(lines) if pattern in line]
if matches:
    for num, line in matches:
        print(f'{num}: {line}')
else:
    print(f'no matches for "{pattern}" in {name}')
