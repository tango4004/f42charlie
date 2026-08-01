#!/usr/bin/env python3
"""notepad/help — show available verbs and param format. One operation."""
print("""notepad — text notes (one operation per script)

verbs:
  notepad/write    params: {"name":"...","body":"..."}             — write note
  notepad/read     params: {"name":"..."}                         — read note
  notepad/append   params: {"name":"...","body":"..."}            — append to note
  notepad/find     params: {"name":"...","pattern":"..."}          — find lines matching pattern
  notepad/replace  params: {"name":"...","old":"...","new":"..."}  — replace text
  notepad/erase    params: {"name":"..."}                         — delete note

storage: workspace/notes/<name>.txt
layer: text (no file listing, no metadata — that's filemgr)
no vault, no cross-layer""")
