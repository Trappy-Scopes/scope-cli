# Electronic protocols — schema & event-editing design

!!! note "Provenance"
    Written by **Claude** (Anthropic), in conversation with Yatharth on
    2026-09-08, as a review-before-build design note for formalizing
    `expframework/protocol.py` and adding event editing to `Experiment`.
    Nothing in this document has been implemented yet — it is the proposal
    Yatharth asked to review before an API is written.

---

## 1. Why this document exists

Two related asks, both explicitly "propose, then let me review, then build":

1. A version-controlled, GitHub-backed protocol system that supports three
   distinct ways of running a protocol (free-load, sequential+annotated,
   checkpoint/keyboard-shortcut-driven), with real provenance (which commit
   ran, when, from where).
2. A way to **edit** events after the fact — `exp.note()`, `user_prompt()`,
   protocol steps, and measurements all currently produce immutable,
   append-only log entries. Editing needs to be selective (some fields must
   never be touched), safe at scale (an experiment can have thousands of
   events), and must actually reach `experiment.yaml` on disk.

---

## 2. Facts established by reading the code (not guesses)

These are load-bearing for the design below, so recording exactly what's
true today before proposing anything.

### 2.1 Good news: `experiment.yaml` is fully re-dumped, not appended

`Experiment.__save__()` and `Experiment.close()` both do:

```python
with open(self.log_file, "w") as f:
    f.write(yaml.dump(self.logs))
```

`self.logs` is dumped **whole, fresh, every time** — not appended to
incrementally. This means the concern raised ("if the YAML is composed from
raw objects every time, editing just works; if not, we need a propagation
patch") resolves cleanly: **no patch is needed.** Any in-place edit to
`self.logs["events"][i]` is automatically correct on the next save, because
every save re-serializes the live in-memory structure. Editing infrastructure
just needs to mutate the right in-memory dict and lean on the existing
`@autosave` decorator (already used throughout `Experiment`) to trigger a
write.

### 2.2 Real blocker: events are cast to plain `dict` on append

```python
def log(self, event, attribs={}):
    self.logs["events"].append(dict(ExpEvent(kind=event, attribs=attribs)))
```

`dict(ExpEvent(...))` throws away the `TSEvent`/`ExpEvent` class the moment
an event is stored — what lives in `self.logs["events"]` is a bare `dict`,
with no `.edit()` method to call even if we add one to `TSEvent`. Any editing
API has to either:

- **(a)** stop casting to `dict` and register a custom YAML representer so
  `yaml.dump` can still serialize a `TSEvent`/`ExpEvent`/`Measurement`
  subclass directly, or
- **(b)** keep storing plain dicts (zero risk to the existing YAML format)
  and provide a thin wrapper that is handed back on *read* (`exp.events()[i]`
  returns a wrapper around `self.logs["events"][i]`, mutating the same
  underlying dict in place).

**(b) is recommended** — it's a read-side concern only, touches no stored
format, and can't silently break `yaml.dump` on an event type it's never
seen serialize before.

### 2.3 The field split you remembered is already real

`TSEvent.__init__` sets fixed, computed keys once: `type`, `scopeid`, `mid`,
`sid`, `dt`, `sessiontime`, `machinetime`, `attribs`. `ExpEvent` adds `eid`,
`scriptid`, `exptime`. **Every one of those is computed at creation time from
system state** (the clock, the session, the scope). Everything the *user*
actually typed or annotated lives inside `attribs`. So "never editable" vs.
"user's own words" is already a clean, existing boundary — an editor only
ever needs to touch `event["attribs"]`, never the top-level keys.

### 2.4 `Experiment.events()` is currently wrong

```python
def events(self):
    return list(self.logs.keys())
```

This predates the current shape of `self.logs` (a dict with `"events"` as
one key holding the actual list) and returns `["user", "results", "events",
"eid", ...]` — the top-level log *section names*, not the events. This needs
fixing as part of building the editor, since the editor's whole surface is
"get me the events, then let me touch one/some of them."

### 2.5 `Measurement` already has the field the ask wants restricted

```python
self.update({..., "success": None, ...})
```

`Measurement(ExpEvent)` already carries a `success` flag explicitly meant to
be set after the measurement completes. This lines up exactly with "the user
should only be allowed to toggle the success flag" — no new field needed,
just a narrower `edit()` on `Measurement` that only accepts `success`.

### 2.6 Today's protocol files don't agree with each other, or with the README's own schema

The README documents one frontmatter shape (`author`, `editor`, `description`,
`references`) and one body shape (`# Title` → `## Requirements` → `## Steps`
→ `### Macro step` → `## Additional Information`). Real files diverge on
every axis:

| File | Frontmatter keys actually used | Body shape |
|---|---|---|
| `masterprotocol1.md` | `Author`, `date` | `## Macro procedures` then `## Procedure` (lettered sub-items, not `### Macro step`) |
| `masterprotocol_June26.md` | `author`, `description` | Matches README schema, incl. `### Macro step` |
| `masterprotocol_nov25.md` | *(none)* | `## Introduction` → `### Part I`/`### Part II` — no `## Requirements`/`## Steps` at all |
| `streaking_plates.md` | `authors` (plural), `description` | Matches |
| `tapp_media.md` | `authors`, `description`, `references` | `## Introduction` instead of preamble |
| `piranha_solution_prep.md` | `author`, `edited`, `date: (2024, 05, 09)`, `outcome` | Matches |
| `bsa_treatment.md` | `author`, `date`, `outcome`, `reference` (singular) | Matches |
| `selectswimmers.md` | *(none)* | No `##` sections at all |

Concretely: `_split_macro_steps()` reads `sections.get("Steps", "")` — for
`masterprotocol_nov25.md` that's `""`, so `Protocol` would parse zero steps
from a file that clearly has real procedural content. This isn't a parser
bug to silently patch; it's evidence the schema itself needs to be finalized
and then the real files migrated to it (a separate, later pass — not part of
this design).

One field worth keeping that the README never documented: **`outcome`**,
used ad hoc in two files to name what the protocol produces (e.g.
`bsa_stock_solution`). That's a genuinely useful, missing piece of structure
— see §4.

---

## 3. Design goals, distilled from the discussion

1. **Local-first**, because it must work offline in a lab, and because the
   repo's identity should come from configured `git_dependencies`, not a
   parallel, hardcoded fetch path — see §6.
2. Still get a **GitHub permalink** recorded per run, by default — derived
   from the local clone's own git state (remote URL + commit hash),
   **without a network call**. This is what makes protocol provenance
   credible for a published dataset while keeping day-to-day operation
   fully offline.
3. **Not every file in a protocols repo is a protocol.** A repo has READMEs,
   category overviews, and reference material a protocol may need to point
   to for context it doesn't repeat itself. The schema needs a `kind` so
   tooling (and `Protocol.__init__`) can tell the difference and refuse to
   "execute" a reference file.
4. **Three usage modes**, not one:
   - *Freestyle load*: pull a protocol in for the record (payload-copy +
     one log event), no stepping through it — today's actual usage in
     `scripts/longterm/mjpeg_*.py`.
   - *Sequential, annotated*: today's `execute()`, improved with an optional
     note per step instead of a rigid "type `done`" gate.
   - *Checkpoint / keyboard-shortcut-driven*: steps don't run in order; each
     step can bind a key sequence (`esc 1`, `esc p`, …) that, once the
     protocol is loaded, logs that specific step as done whenever it's
     pressed — for hands-busy, non-linear lab work.
5. **Images stay out of the markdown schema** — link to them, don't embed
   them. (Confirmed intentional; see §7.)
6. **Event editing**, scoped narrowly: only `attribs` fields, never the
   system-computed ones; bulk edits across many events need to be safe and
   renderable at scale (thousands of events); `Measurement` only ever
   exposes `success` for editing.

---

## 4. Proposed frontmatter schema v2

```yaml
---
kind: protocol              # protocol | reference | index — see §5
title: BSA stock solution preparation
authors: [Yatharth Bhasin, Camila Costa]
editors: []
created: 2025-08-08         # real ISO date, not the "(2025, 08, 08)" string seen today
description: >
  Preparation of BSA stock solution for microfluidic device treatment.
outcome: [bsa_stock_solution]     # what this protocol produces — formalizes the ad hoc field already in use
requires_protocols: []            # e.g. [mediaprep/stocksol_prep.md] — protocols this one assumes were already run
see_also: [microfluidics/README.md]   # parent/context files — the README-as-higher-context case
references: [Marco Polin lab]
publish_remote_link: true         # per-file override of the repo-level config default (§6)
---
```

Dropped `category` from the frontmatter on request — it doesn't need to be
authored by hand. `microfluidics/treatment/bsa_treatment.md`'s category
*is* `microfluidics/treatment`: it's exactly the file's own path relative to
the protocols repo root, already known the moment the file is resolved
(§6). Category becomes a computed property, never a field to keep in sync
by hand.

Notes on each new/changed field:

- **`kind`** is the load-bearing addition — `Protocol.__init__` should
  refuse (clearly, not silently) to treat a `kind: reference` or
  `kind: index` file as an executable protocol.
- **`authors`/`editors` as lists**, always — ends the
  singular/plural/capitalization drift in §2.6 without losing anyone
  currently credited.
- **`created` as a real date** — currently a couple of files write
  `date: (2024, 05, 09)`, which YAML parses as a *string* (not a date), so
  it was never actually machine-usable.
- **`requires_protocols` / `see_also`** are the two link fields discussed:
  `requires_protocols` for a hard prerequisite (run this first),
  `see_also` for context that doesn't need to be *run*, just read (the
  category README). Kept separate because they mean different things to
  automation — one could eventually be checked ("has `stocksol_prep` been
  run in this experiment?"), the other is purely informational.
- **`publish_remote_link`** exists per-file so an individual protocol can
  override the repo-level default in §6 (default **true** — see §6) in
  either direction: opt a specific file *out* if it shouldn't be linked
  (still-unpublished work, say), or opt it in even when the repo default is
  off.

**What is deliberately *not* in the frontmatter**: the git commit hash and
permalink. Those describe *when this file was loaded for a run*, not
something the file says about itself — see §6. Baking a commit hash into the
file itself would make every edit invalidate its own metadata.

---

## 5. Repository conventions

- A file with `kind: reference` (a facility-requirements doc, a mutants
  list — real background information that isn't itself a procedure) is
  loadable via `see_also`/`requires_protocols` links and via
  `Protocol.context()` (read its text for display) but never via
  `Protocol.follow()` (§7).
- **`kind: index`** — a file whose entire job is to *point at* other files,
  not to say anything substantive itself. The top-level README's "List of
  protocols" section, or a category's own README that's just a bullet list
  of the files in that folder, are both `index` files: pure
  table-of-contents, no procedure and no background information of its
  own. The distinction from `reference` is content, not location — a
  category README that also explains real background (e.g. why a category
  exists, shared safety notes) is `reference`; one that's just a links list
  is `index`. Both are equally non-executable; the split exists so tooling
  cataloging a repo can tell "this is where to look" apart from "this is
  what you need to know."
- Files with **no frontmatter at all** (`selectswimmers.md`,
  `masterprotocol_nov25.md` today) are treated as `kind: protocol` by
  default with all other fields empty, so nothing currently loadable breaks
  — but `Protocol.show()` should visibly flag "no metadata declared" rather
  than silently rendering an empty metadata panel, so the gap is obvious
  instead of invisible.
- **Not touching the real files in `Trappy-Scopes/protocols` at all, for
  now** — no migration to this frontmatter, no fix to
  `masterprotocol_nov25.md`'s structure, nothing. This design only covers
  the parser/API side; the repo's own content is out of scope until
  separately requested.

---

## 6. Local-first resolution + permalink, without a network call

```
1. Resolve the protocol's repo root from Experiment.protocols_dirs
   (a local git clone kept current by git_dependencies/repo_sync).
2. If the requested path exists in that clone:
     a. Read the file directly off disk. No network access at all.
     b. Run locally, no network required:
          git -C <repo> rev-parse HEAD           -> commit hash
          git -C <repo> status --porcelain <path> -> dirty check for this file
          git -C <repo> remote get-url origin     -> https://github.com/<org>/<repo>(.git)
     c. Build the permalink by string substitution, no API call:
          https://github.com/<org>/<repo>/blob/<commit>/<path>
     d. If the file has uncommitted local changes, the permalink is still
        recorded but flagged uncommitted_changes=true — the run is
        reproducible from disk, just not yet from that exact commit.
3. If the clone doesn't exist yet, that's not a reason to fetch from a
   second, separate, hardcoded source (today's `githubfiles.get_file()`
   always hits `raw.githubusercontent.com/Trappy-Scopes/...` — an org name
   baked into code, nowhere near config). `git_dependencies` already states
   the repo's identity explicitly and correctly
   (`https://github.com/Trappy-Scopes/protocols` -> local path) — so the
   fix for "not cloned yet" is to run the *same clone step*
   `repo_sync`/`git_dependencies` already knows how to do, then resolve
   locally as normal. This keeps exactly one place that says where
   protocols come from (`git_dependencies` in config), instead of two.
4. Whether the permalink is actually written into the experiment's log
   (vs. kept purely local) is governed by config:
     Experiment.protocols.publish_remote_link: true   # repo-wide default
   overridable per file via `publish_remote_link` in its own frontmatter
   (§4).
```

This gets the explicitly-wanted outcome — "if there's a direct method of
doing this from the local repository, favor the local repository... I really
want the GitHub link" — without ever needing dual local+remote calls, and
without a second, implicit notion of "which GitHub repo is this" living
only in `githubfiles.py`: the permalink is *derived* from local git
metadata that `git_dependencies` already made explicit, not *fetched*.

**On "dirty"**: yes, that's the actual git term (`git status` calls an
unclean working tree "dirty" vs. "clean") — it's correct, just used a lot
above because it comes up at every step of this section. The field/flag
itself is named `uncommitted_changes` throughout the design (not `dirty`)
precisely so nothing user-facing needs the jargon — "dirty" only shows up
here, explaining where the concept comes from.

---

## 7. Three usage modes — proposed API sketch

Renamed away from the more technical `stage()`/`execute()`/`arm_checkpoints()`
verbs to plainer ones that say what actually happens:

```python
p = Protocol("microfluidics/treatment/bsa_treatment.md")
# ^ resolves locally, computes commit/permalink, refuses if kind != protocol,
#   logs one "protocol_loaded" event with: path, kind, commit,
#   uncommitted_changes, permalink, frontmatter (authors/outcome/etc.) --
#   this is the "fanfare" log entry.

# Mode A -- freestyle load (today's actual usage in mjpeg_*.py)
p.copy()                  # copies the markdown into exp_dir/protocols/,
                           # governed by an on/off config flag, not automatic.
                           # No stepping through it.

# Mode B -- sequential, annotated
p.follow()                 # unchanged in spirit: runs embedded ```python blocks,
                            # prompts per sub-step. Confirmation gate changes from
                            # "type done or get reprompted forever" to:
                            #   Enter/'done' to confirm, then an optional
                            #   "notes for this step? [Enter to skip]" prompt,
                            # stored on that step's user_prompt event's attribs.

# Mode C -- keyboard-shortcut-driven, non-sequential
p.enable_shortcuts()        # reads each step's shortcut declaration (§10.4),
                             # registers them via utilities.keyboard_shortcuts
                             # under source="protocol" (already source-tagged,
                             # so p.disable_shortcuts() == clear("protocol")) --
                             # naming matches this session's existing
                             # enable_history_logging()/disable_history_logging()
                             # and repl_history.enable()/disable() pattern.
                             # Pressing a bound sequence logs that one step done,
                             # in whatever order the user actually does them.

# Any mode, any time -- a symmetric pair rather than one negatively-framed flag:
p.mark_as_executed(note=None)     # records that this protocol was actually
                                   # carried out as loaded, with an optional note.
p.unmark_as_executed(note=None)   # records the opposite -- present/loaded for
                                   # this experiment, but not actually carried
                                   # out (or a prior mark_as_executed() was
                                   # wrong), with an optional reason.
```

Both are valid any time, independent of which mode (A/B/C) was used, and
even after just `p.copy()` with no stepping at all — this is a fact about
the whole run, not about one step, so it's separate from per-step notes.
Because events are append-only (§2), calling one after the other doesn't
edit anything — it appends a second event. The *current* status is just
whichever came last, but the full back-and-forth stays visible in the log
for free (e.g. marked executed, then later corrected) — no editing
machinery needed for this particular case.

All three modes share the same `protocol_loaded` event and the same
commit/permalink provenance — they differ only in *how completion gets
logged*, which matches "mixed protocols policy: you execute it step by step
and annotate it... or... freestyle... or... checkpoints tied to keyboard
shortcuts" as one object with three ways to drive it, not three objects.

---

## 8. Event-editing API — proposed shape

```python
# TSEvent gains an edit() that only ever touches attribs:
class TSEvent(dict):
    def edit(self, **fields):
        self["attribs"].update(fields)
        return self

# Measurement overrides it to a single allowed field:
class Measurement(ExpEvent):
    def edit(self, *, success):
        self["attribs"]["success"] = success
        return self
```

Read-side wrapper (per §2.2's option (b) — storage format is untouched).
Naming lines up with §9's generalized `RecordSet` rather than a
one-off `EventSet` — events are just the first `RecordSet` use site:

```python
# Experiment.events() fixed to actually return the events list,
# wrapped in the same general core.idioms.recordeditor.RecordSet §9 proposes,
# so .edit() reaches the same dict stored in self.logs["events"]:
def events(self):
    return RecordSet(self.logs["events"], on_change=self.__save__)
```

`RecordSet` itself is defined once, generally, in §9 — nothing
event-specific about `__getitem__`/`filter`/`edit_all`/`table` beyond what
each record type (`TSEvent`, `Measurement`, ...) declares as its own
editable fields.

**Resolved: yes, keep an edit trail, but as an optional, separate file** —
not `attribs["_edit_history"]` on the event itself. `experiment.yaml`'s own
shape stays untouched by editing; a *second* file
(`exp_dir/event_edits.yaml`) records each edit as its own timestamped entry
— reusing the same `create_yaml_logger()` mechanism already used for
`logs.yaml` and `repl_history.py`'s `repl_history.yaml`, rather than a third
logging approach:

```python
# One editable-record wrapper, from core.idioms.recordeditor (§9) --
# generic over what "record" and "editable fields" mean for a given type:
class EditableRecord:
    def edit(self, track_history=True, **fields):
        if track_history:
            _edit_logger.info("record_edited", extra={
                "record_type": self._record.get("type", type(self._record).__name__),
                "record_dt": self._record.get("dt"),
                "changed": {k: {"from": self._record[k], "to": v}
                            for k, v in fields.items()},
            })
        self._record.update(fields)
```

`track_history` defaults to on but is a real per-call (or config) opt-out,
per "should be optional." Keeping it in a separate file also means a
`RecordSet.edit_all()` bulk edit produces one compact trail file to review,
instead of bloating every touched record inline. Since `RecordSet` (§9) is
shared across record types, this same trail file and the same
`track_history` toggle apply whether the edited record is an event, a
measurement, or eventually a notebook entry — one mechanism, not one per
record type.

---

## 9. Confirmed out of scope (for this pass)

- **Images embedded in protocol markdown** — confirmed intentional. Links
  only. No change proposed here; revisit only if a concrete need comes up.
- **Touching the real files in `Trappy-Scopes/protocols`** — no migration
  to schema v2, no structural fix to `masterprotocol_nov25.md`, nothing.
  Not bundled with the parser/API work; a separate ask for later.

### A visual editor is wanted — generalized beyond just events

Widening the scope on request: this codebase already has *several* places
that are really the same problem — "a collection of dict-like records, some
fields user-editable and some not, that needs browsing and in-place
editing" — each currently solved separately, or not solved at all:

| Records | Where today | Editable today? |
|---|---|---|
| `Experiment.logs["events"]` | `expframework/experiment.py` | No |
| `Measurement` rows in a `MeasurementStream` | `expframework/measurement.py` | No |
| `ExpNotebook` entries | `expframework/notebook.py` | Unread this session — likely also no |
| `sessions.yaml` history | `Session`/`experiment.py` | No |
| A single `PhysicalObject`'s fields | `hive/physical.py` | Yes — `update()`'s own bespoke dialog |

Rather than one `eventeditor.py` built just for `Experiment.events()`,
propose one general **`RecordSet`** — home: **`core/idioms/recordeditor.py`**
(alongside `core/idioms/dicttools.py`, `core/idioms/platform.py`, `core/idioms/clock.py`
— that's already where this codebase keeps cross-cutting, reusable
patterns, not tied to `hive` or `expframework`):

```python
class RecordSet:
    """A live view over any list of dict-like records. Wraps the list
    in place (no copies) -- editing through this reaches the same objects
    the caller is holding, so @autosave-style persistence keeps working
    unchanged (per §2.1).

    Each record type declares which of its own fields are user-editable
    (e.g. TSEvent -> ("attribs",); Measurement -> ("success",);
    PhysicalObject -> all of `attribs`) -- RecordSet itself stays
    type-agnostic and never hardcodes what "editable" means for any one
    kind of record.
    """
    def __init__(self, records, on_change=None): ...
    def filter(self, **kwargs) -> "RecordSet": ...
    def table(self, *fields, page=50): ...          # paginated rich.Table
    def edit(self, index, track_history=True, **fields): ...
    def edit_all(self, track_history=True, **fields): ...
    def edit_interactive(self, index=None): ...      # opens the shared dialog
```

The `prompt_toolkit` `Dialog`/`TextArea`/Save-Cancel piece
`PhysicalObject.update()` already built becomes the one implementation
`edit_interactive()` calls — factored out of `hive/physical.py` into
`core/idioms/recordeditor.py` itself (or a sibling it imports), rather than
kept as a second copy. `PhysicalObject.update()` becomes
`RecordSet([self.attribs]).edit_interactive(0)`; `Experiment.events()`
becomes `RecordSet(self.logs["events"], on_change=self.__save__)`; the same
class is available, unmodified, the day `MeasurementStream` or
`ExpNotebook` want the same treatment.

---

## 10. Review outcome

All four questions from the first draft are settled:

1. Frontmatter shape (§4) — approved, `category` dropped (now computed
   from path, not authored — §4).
2. `kind: protocol | reference | index` — approved; `index` meaning
   clarified in §5 (pure table-of-contents vs. `reference`'s real
   background content).
3. Edit trail — yes, optional, in a **separate file**
   (`event_edits.yaml`), not inline in `attribs` — §8.
4. Per-step shortcut declaration — a small YAML block scoped to its step,
   "whatever works best in YAML" rather than a separate `## Shortcuts`
   section. Proposed concretely:

   ```markdown
   ### Trap cells gently
   ```yaml
   shortcut: esc 1
   ```
   1. Add the syringes to the other stopcock...
   ```

   Parsed the same way `_python_blocks()` already finds ` ```python ` fences
   scoped to a macro-step or sub-step body (§2.6's parser) — a
   ` ```yaml ` fence is just another fence type `_headings()`/the substep
   splitter already walks past, read for `shortcut:` instead of executed.
   It keeps the step self-contained (the fence sits right where the step
   it applies to lives) without inventing a new top-level section.

Since the first draft: `flag_not_followed()` became the symmetric
`mark_as_executed(note=None)` / `unmark_as_executed(note=None)` pair (§7) —
each logs its own event (`protocol_marked_executed` /
`protocol_unmarked_executed`) via the existing `exp.log()`, carrying the
protocol's path/commit and the optional note; and §9's visual-editor
proposal was widened from an `Experiment`-only `eventeditor.py` into a
general `RecordSet` (`core/idioms/recordeditor.py`) covering events,
measurements, and any future record type the same way.
