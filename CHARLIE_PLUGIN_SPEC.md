# Charlie Plugin Spec (v0.2)

Status: **canon** 2026-07-31. Locks: directory/verb structure; params[] array + body last; one abstraction layer per plugin; two tiers (handler/template).  
Supersedes v0.1 (flat plugin file, mixed argument).  
Canon: `CHARLIE_ROADMAP.md` · `CHARLIE_VAULT_SPEC.md` v0.6  
Live host: c2 / `132.226.149.193` (Charlie `f42charlie.service`, Python 3.8)

---

## 0. One-line principle

**A plugin is a directory (one abstraction layer). Each verb is a standalone script. Parameters are an array (order = meaning, from help). Body is always last, immutable, never parsed. "One thing well" = literally one script, one operation.**

---

## 1. Structure: directory = plugin, file = verb

```
plugins/
  notepad/
    write.py         # one script, one operation
    read.py
    append.py
    find.py
    replace.py
    erase.py
    help.py          # optional: returns verb list + param order
  filemgr/           # (future, separate layer)
    list.py
    exists.py
    rename.py
    info.py
    delete.py
  github/            # (P1, template plugins)
    create_issue.yaml
    open_pr.yaml
```

- **Directory** = plugin (one abstraction layer: text, files, github, mail, …)
- **File** = verb (one operation, standalone script)
- **Call** = `dir/verb` (e.g., `"notepad/write"`)
- Plugin path: `plugins/{dir}/{verb}.py`

**God-plugin = mixing abstraction layers in one directory.**  
Notepad (text) and filemgr (files) are separate directories, even if they touch the same files.

---

## 2. Call convention: params[] + body

```
step(sid, "notepad/write", ["my_note"], "текст")
#         verb             params[]      body
```

- **verb** = `dir/verb` string (e.g., `"notepad/write"`)
- **params** = array, meaning = **order**, described in `help`
- **body** = always **last**, **immutable**, **never parsed** by the plugin or Charlie
- Parameters can be N — not just a filename. Notepad happens to need 1–3; other plugins may need more.

### Body rules

1. Body is the **payload** (content, text, raw data).
2. Body is **never** split, parsed, or searched for metadata.
3. If a verb needs structured data (old + new for replace), it goes in **params**, not body.
4. Body can be empty (`""`) for verbs that don't have a payload (read, erase, find).

### Notepad — all verbs

| Verb | params | body |
|------|--------|------|
| `notepad/write` | `[name]` | text content |
| `notepad/read` | `[name]` | *(empty)* |
| `notepad/append` | `[name]` | text to append |
| `notepad/find` | `[name, pattern]` | *(empty)* |
| `notepad/replace` | `[name, old, new]` | *(empty)* |
| `notepad/erase` | `[name]` | *(empty)* |

`replace` — three params, zero body. No `|||` separator, no body parsing. Old and new are params.

---

## 3. Daemon → subprocess

Charlie daemon calls each verb as a standalone subprocess:

```
python3 plugins/notepad/write.py <workdir> <body> <param1> <param2> ...
```

**argv layout:**

| argv | Content | Always present? |
|------|---------|-----------------|
| `[1]` | workdir | yes |
| `[2]` | body | yes (empty string if no payload) |
| `[3+]` | params (variadic, in order) | yes (zero or more) |

Plugin reads:
```python
import sys
workdir = sys.argv[1]
body = sys.argv[2]
params = sys.argv[3:]   # list, order from help
```

### Daemon changes (from current)

```python
def _find_plugin(self, verb):
    """plugins/{verb}.py — verb is 'dir/verb'"""
    if ".." in verb:
        raise ValueError("plugin path contains ..")
    path = os.path.join(self.plugins_dir, f"{verb}.py")
    if not os.path.exists(path):
        return None
    return path

def _run_plugin(self, task):
    path = self._find_plugin(task['verb'])
    if not path:
        self.db.set_result(task['task_id'], task['session_id'],
                           f"error: plugin not found: {task['verb']}")
        self.db.set_task_done(task['task_id'])
        return
    r = subprocess.run(
        ['python3', path,
         task['workdir'],
         task.get('body', ''),
         *json.loads(task.get('params_json', '[]'))],
        capture_output=True, text=True, timeout=60
    )
    # ...
```

### Path traversal check

`verb` must not contain `..`. Directory separator `/` is allowed and expected.

---

## 4. step() API

```
step(session_id, verb, params, body)
```

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `session_id` | string | yes | |
| `verb` | string | yes | `"notepad/write"` |
| `params` | array | yes | `["my_note"]` — can be empty `[]` |
| `body` | string | yes | `""` if no payload |

MCP JSON-RPC:
```json
{"method": "step", "params": {"session_id": "sid", "verb": "notepad/write", "params": ["my_note"], "body": "текст"}}
```

### Old plugins — not a concern

Previous `exec`, `python` plugins used `(sid, command, argument)`. They are **superseded** by the new model. No backward compatibility needed. Old plugin files are trash.

---

## 5. DB schema change

```sql
-- old: tasks(plugin, command, argument, workdir)
-- new:
tasks(
  task_id     TEXT PRIMARY KEY,
  session_id  TEXT,
  verb        TEXT,         -- "notepad/write"
  params_json TEXT,          -- '["my_note"]'
  body        TEXT,          -- "текст" or ""
  workdir     TEXT,
  status      TEXT,
  created_at  INTEGER,
  ...
);
```

`params_json` = JSON array string. `body` = raw text, never JSON.

---

## 6. Help

`step(sid, "notepad/help", [], "")` or `step(sid, "help", [], "")` for all:

```
notepad:
  write    params: [name]            body: text content
  read     params: [name]            body: (empty)
  append   params: [name]            body: text to append
  find     params: [name, pattern]   body: (empty)
  replace  params: [name, old, new]  body: (empty)
  erase    params: [name]            body: (empty)
```

Model learns **param order** from help. Doesn't guess format. Doesn't parse body.

---

## 7. Admin / discovery

Admin scans `plugins/` recursively:

```python
for root, dirs, files in os.walk(plugins_dir):
    for f in sorted(files):
        if f.endswith('.py') and f != 'help.py':
            cat = os.path.basename(root)
            verb = os.path.splitext(f)[0]
            name = f"{cat}/{verb}"
            # → notepad/write, notepad/read, ...
```

Workspace creation → checkboxes grouped by directory:
```
☐ notepad/write    ☐ notepad/read     ☐ notepad/append
☐ notepad/find     ☐ notepad/replace  ☐ notepad/erase
```

After creation, workspace has a fixed set of enabled verbs.

---

## 8. Two tiers

### 8.1 Handler (P0)

- Python file, standalone script
- No vault
- One operation per script
- Called as subprocess by daemon
- Storage: workspace-scoped (`workdir/notes/`)

Examples: `notepad/write.py`, `notepad/read.py`, (future) `filemgr/list.py`

### 8.2 Template (P1)

- Signed YAML manifest
- Vault-backed (declares `vault_slots`)
- One HTTP verb per manifest
- Charlie fills params → vault fills slots → HTTPS → extract → result

```yaml
# plugins/github/create_issue.yaml
name: github/create_issue
vault_slots:
  - name: github/pat
    access: egress_inject
params:
  - {name: repo, type: string, desc: "owner/repo"}
  - {name: title, type: string}
body: {name: body_text, type: string, default: ""}
execute:
  method: POST
  url: "https://api.github.com/repos/${param:repo}/issues"
  headers:
    Authorization: "Bearer ${slot:github/pat}"
  body_json:
    title: "${param:title}"
    body: "${body}"
  extract:
    issue_number: ".number"
    url: ".html_url"
```

Flow: model → `step(sid, "github/create_issue", ["foxtrot42mac/f42vault", "Bug title"], "body text")` → Charlie fills `${param:...}` and `${body}` → vault fills `${slot:...}` → HTTPS → extract → model sees `{issue_number, url}`.

---

## 9. Plugin law

1. **One abstraction layer per directory.** All verbs of that layer in one directory.
2. **One operation per script.** `write.py` writes, nothing else.
3. **params = array, order from help.** Body = last, immutable, never parsed.
4. **Handler = code (Python).** Template = data (signed YAML).
5. **Handler: no vault.** Template: vault required.
6. **Workspace-scoped storage.** Handler operates within `workdir`.
7. **Response = clean result.** Not raw HTTP, not auth headers.
8. **Signed templates gate vault.** Unsigned handler runs without vault.
9. **No cross-layer calls.** Notepad doesn't call filemgr. Model chains if needed.
10. **Old plugins are trash.** No backward compat with `(sid, command, argument)`.

---

## 10. What "one thing well" means

| Misreading | Reality |
|------------|---------|
| one verb per plugin | one **operation per script** — directory groups related scripts |
| plugin = one file with sub-commands | plugin = **directory**, each verb = standalone file |
| body carries metadata | body is **pure payload**, params carry metadata |
| params are flags (`-file:`) | params are **array**, meaning = order, from help |
| plugins call each other | they don't — model chains |

---

## 11. Repo layout

```
tango4004/f42plugins/
  README.md
  LICENSE               # MIT
  notepad/
    write.py
    read.py
    append.py
    find.py
    replace.py
    erase.py
    help.py             # returns verb list + param order
  (future)
  filemgr/
    list.py
    exists.py
    rename.py
    info.py
    delete.py
    help.py
  github/
    create_issue.yaml   # P1 template
    open_pr.yaml
```

Deploy: `cp -r notepad/ /home/f42charlie/app/plugins/`

---

## 12. First handler: notepad

**Status:** ready to build.

**Acceptance:**
- [ ] `write` then `read` returns same text
- [ ] `append` adds to existing
- [ ] `find` returns matching lines
- [ ] `replace` returns count (params: name, old, new — no body)
- [ ] `erase` clears note
- [ ] `help` shows verb list + param order
- [ ] notes workspace-scoped (different ws = different notes)
- [ ] body never parsed
- [ ] params always array, order from help

---

## 13. Roadmap

| Phase | Deliverable |
|-------|-------------|
| **P0** | notepad handler (6 verbs + help), daemon `_find_plugin`, DB schema, `step()` API |
| **P0.5** | spec locked + notepad tested on c2 |
| **P1** | first template plugin (github/create_issue, vault-backed) |
| **P1.5** | signed manifest + store verification |
| **P2** | filemgr handler (list, exists, rename, info, delete) |
| **P3** | more template plugins (agentmail/send, github/open_pr, …) |

Spec version: **v0.2** (directory/verb, params[]+body, daemon changes, old plugins trash).
