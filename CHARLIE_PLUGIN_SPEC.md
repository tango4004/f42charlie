# Charlie Plugin Spec (draft v0.1)

Status: **draft** 2026-07-28. Locks: one abstraction layer per plugin; two tiers (handler/template); notepad as first handler.  
Canon: `CHARLIE_ROADMAP.md` · `CHARLIE_VAULT_SPEC.md` v0.6  
Live host: c2 / `132.226.149.193` (Charlie `f42charlie.service`, Python 3.8)

---

## 0. One-line principle

**A plugin owns one abstraction layer, not one verb. All verbs of that layer live in one plugin. Mixing abstraction layers in one plugin = god-plugin.**

---

## 1. Principle: one abstraction layer

| Plugin | Layer | Verbs | What it does NOT touch |
|--------|-------|-------|------------------------|
| **notepad** | text | read, write, append, find, replace, erase | file existence, listing, metadata |
| **filemgr** (later) | files | list, exists, rename, info, delete | text content editing |
| **vault** | secrets | deposit, execute, revoke | text editing, file management |
| **github_create_issue** (P1) | one HTTP call | create_issue | other GitHub endpoints |

**"One thing well" = one layer, all its natural verbs.**  
Notepad reading/writing/replacing text = one layer. `list` files = different layer → different plugin.

**God-plugin = mixing layers.** A "github" plugin with issues + PRs + reviews + actions + blobs = five layers in one file. Instead: five plugins, each one layer.

---

## 2. Two tiers

### 2.1 Handler plugins (P0)

- **Python file** in `plugins/`
- **No vault** — local operations only
- One abstraction layer, set of verbs
- Workspace-scoped storage (`/home/f42charlie/workspaces/<ws>/`)
- Called via Charlie step: `step(sid, "notepad", "read my_note")`
- Charlie daemon loads and executes handler in process

Examples: `notepad`, `exec`, `python`, `filemgr` (later)

### 2.2 Template plugins (P1)

- **Signed YAML manifest** — no executable code
- **Vault-backed** — declares `vault_slots`, vault injects at egress
- One HTTP verb per template
- Charlie fills args → vault fills slots → HTTPS → extract → clean result
- Called: `step(sid, "github_create_issue", '{"repo":"...","title":"..."}')`

Examples: `github_create_issue`, `agentmail_send`, `github_open_pr`

---

## 3. Handler manifest

```yaml
# notepad — handler manifest
name: notepad
version: 0.1.0
description: "Text notes — read, write, append, find, replace, erase"
layer: text
vault_slots: []
verbs:
  - name: read
    syntax: "read <note>"
    desc: "return text content of note"
  - name: write
    syntax: "write <note>: <content>"
    desc: "overwrite note with content"
  - name: append
    syntax: "append <note>: <content>"
    desc: "append content to note"
  - name: find
    syntax: "find <note>: <pattern>"
    desc: "return lines matching pattern"
  - name: replace
    syntax: "replace <note>: <old>: <new>"
    desc: "replace all occurrences of old with new"
  - name: erase
    syntax: "erase <note>"
    desc: "delete note content"
```

**Storage:** workspace-scoped. Handler does not see arbitrary file paths.  
Charlie provides `workdir` (= `/home/f42charlie/workspaces/<ws>/`). Handler stores notes under `workdir/notes/`.

**Notepad does NOT know:**
- whether the note is a file, sqlite row, or memory blob
- what other notes exist (that's filemgr's job)
- file permissions, encoding, extension

---

## 4. Template manifest (P1 — for reference)

```yaml
# github_create_issue — template manifest (signed)
name: github_create_issue
version: 0.1.0
description: "Create a GitHub issue"
layer: http
vault_slots:
  - name: github/pat
    access: egress_inject
    critical: false
args:
  repo: {type: string, required: true, desc: "owner/repo"}
  title: {type: string, required: true}
  body: {type: string, default: ""}
returns:
  issue_number: int
  url: string
execute:
  method: POST
  url: "https://api.github.com/repos/${arg:repo}/issues"
  headers:
    Authorization: "Bearer ${slot:github/pat}"
    Accept: "application/vnd.github+json"
  body:
    title: "${arg:title}"
    body: "${arg:body}"
  extract:
    issue_number: ".number"
    url: ".html_url"
```

Flow: model → args → Charlie fills `${arg:...}` → vault fills `${slot:...}` → HTTPS → extract → model sees `{issue_number, url}`. No key in chat.

---

## 5. Plugin law

1. **One abstraction layer per plugin.** All natural verbs of that layer. No mixing.
2. **Handler = code (Python).** Template = data (signed YAML). Both are plugins.
3. **Handler: no vault.** Template: vault required (declared slots).
4. **Workspace-scoped storage.** Handler operates within `workdir`, not arbitrary paths.
5. **Response = clean result.** Not raw HTTP, not auth headers, not file metadata from a text plugin.
6. **Signed templates gate vault.** Unsigned handler runs without vault. (Charlie policy.)
7. **Discovery via help.** `step(sid, "notepad", "help")` → verb list + syntax.
8. **No cross-layer calls.** Notepad does not call filemgr. If you need both, the model chains them.

---

## 6. What "one thing well" does NOT mean

| Misreading | Reality |
|------------|---------|
| one verb per plugin | one **layer** per plugin, all its verbs |
| one HTTP call per plugin | one **capability** (may need multi-step, but same layer) |
| plugin must be minimal | plugin must be **complete for its layer** (notepad has 6 verbs, not 1) |
| plugins can call each other | they can't — model chains, plugin is isolated |

---

## 7. First handler: notepad

**Status:** draft, ready to build.

```python
# plugins/notepad.py — handler plugin for Charlie
# 6 verbs: read, write, append, find, replace, erase
# storage: workdir/notes/<name>.txt
# no vault, no cross-layer
```

**Acceptance:**
- [ ] `write` then `read` returns same text
- [ ] `append` adds to existing
- [ ] `find` returns matching lines
- [ ] `replace` returns count
- [ ] `erase` clears note
- [ ] `help` shows verb list
- [ ] notes workspace-scoped (different ws = different notes)
- [ ] no file listing (that's filemgr)

---

## 8. Roadmap

| Phase | Deliverable |
|-------|-------------|
| **P0** | notepad handler plugin (6 verbs, workspace-scoped) |
| **P0.5** | plugin spec locked + notepad tested on c2 |
| **P1** | first template plugin (github_create_issue, vault-backed) |
| **P1.5** | signed manifest + store verification |
| **P2** | filemgr handler plugin (list, exists, rename, info, delete) |
| **P3** | more template plugins (agentmail_send, github_open_pr, …) |

Spec version: **v0.1** (draft).
