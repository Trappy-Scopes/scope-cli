# AI Generated -- near-total rewrite by Claude (Anthropic), 2026-09-08/09:
# schema v2 frontmatter, local-first git-backed resolution/provenance,
# copy()/follow()/enable_shortcuts()/mark_as_executed(). See
# docs/notes/protocols.md for the full design record.

import os
import re

import yaml
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from rich import print
from rich.align import Align
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from core.permaconfig.config import TrappyConfig
from core.gitutil import ensure_cloned, provenance

from .experiment import Experiment

_MD = MarkdownIt("commonmark").enable("strikethrough").enable("table")

## Schema v2 list-typed frontmatter fields, and the older, inconsistent
## spellings real files in Trappy-Scopes/protocols actually use for them
## (author/Author/authors, editor/edited/editors, reference/references, ...).
## Not touching those files (see docs/notes/protocols.md §5/§9) -- this
## normalizes what's read, so today's files still parse sensibly under the
## new schema instead of silently losing whoever they credit.
_LIST_FIELDS = {
    "authors": ("authors", "author", "Author"),
    "editors": ("editors", "editor", "edited", "Editor"),
    "outcome": ("outcome",),
    "requires_protocols": ("requires_protocols",),
    "see_also": ("see_also",),
    "references": ("references", "reference"),
}


def _split_frontmatter(text):
    """Separate a leading ``--- ... ---`` frontmatter block from the body.

    Returns ``(meta, body)`` where ``meta`` is whatever dict ``yaml.safe_load``
    makes of the block (``{}`` if there's no frontmatter, or it isn't valid
    YAML, or it isn't a mapping). Real YAML parsing (not a per-line
    ``key: value`` split) so list-typed fields -- ``authors: [a, b]`` --
    actually work; the naive per-line split this replaced never could.
    """
    match = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    block, body = match.groups()
    try:
        meta = yaml.safe_load(block)
    except yaml.YAMLError:
        meta = None
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def _normalize_meta(meta):
    """Fold every alias in _LIST_FIELDS into its schema v2 canonical, list-
    typed key (accepting a bare scalar, a comma-separated string, or an
    already-correct list), and default ``kind`` to "protocol" when absent
    (see docs/notes/protocols.md §5)."""
    out = dict(meta)
    for canonical, aliases in _LIST_FIELDS.items():
        value = None
        for alias in aliases:
            if alias in out:
                value = out.pop(alias)
                break
        if value is None:
            value = []
        elif isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        elif not isinstance(value, list):
            value = [value]
        out[canonical] = value
    out.setdefault("kind", "protocol")
    return out


def _headings(text):
    """Yield ``(level, title, start_line)`` for every ATX heading.

    Parsing through markdown-it means ``#`` characters inside fenced code
    blocks are correctly ignored.
    """
    tokens = _MD.parse(text)
    out = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            out.append((int(tok.tag[1]), tokens[i + 1].content, tok.map[0]))
    return out


def _split_sections(body):
    """Split a markdown body by its ``#``/``##`` headings.

    Returns ``(title, sections)`` where ``title`` is the ``#`` heading and
    ``sections`` maps each ``##`` heading to its raw markdown. Content between
    the title and the first ``##`` is stored under ``"Preamble"``. ``###``
    headings stay inside their parent section.
    """
    lines = body.split("\n")
    title = ""
    sections = {}
    current = "Preamble"
    start = 0

    for level, text, line_no in _headings(body):
        if level > 2:
            continue
        sections[current] = "\n".join(lines[start:line_no]).strip()
        current = text if level == 2 else "Preamble"
        if level == 1:
            title = text
        start = line_no + 1

    sections[current] = "\n".join(lines[start:]).strip()
    return title, sections


def _split_macro_steps(steps_text):
    """Split the Steps section into ``(title, body)`` pairs by ``###`` headings."""
    if not steps_text:
        return []

    lines = steps_text.split("\n")
    headings = [h for h in _headings(steps_text) if h[0] == 3]
    steps = []
    for idx, (_, title, line_no) in enumerate(headings):
        end = headings[idx + 1][2] if idx + 1 < len(headings) else len(lines)
        steps.append((title, "\n".join(lines[line_no + 1:end]).strip()))
    return steps


def _python_blocks(md_text):
    """Return the source of every ```python fenced block in ``md_text``."""
    return [
        tok.content
        for tok in _MD.parse(md_text)
        if tok.type == "fence" and tok.info.strip().lower().startswith("python")
    ]


def _yaml_blocks(md_text):
    """Return the source of every ```yaml fenced block in ``md_text`` --
    used to find a step's ``shortcut:`` declaration (see
    docs/notes/protocols.md §10.4). Kept separate from ``_python_blocks``
    even though the fence-scanning is identical, since a step's yaml
    fence is metadata to read, never something to ``exec``."""
    return [
        tok.content
        for tok in _MD.parse(md_text)
        if tok.type == "fence" and tok.info.strip().lower() == "yaml"
    ]


def _split_substeps(body):
    """Split a macro-step body into its numbered sub-steps.

    Returns a list of ``(raw_markdown, [python_sources])`` — one entry per
    top-level ordered-list item. Returns ``[]`` when the macro step has no
    numbered list, in which case the caller treats the whole body as one step.
    """
    if not body.strip():
        return []

    tree = SyntaxTreeNode(_MD.parse(body))
    lines = body.split("\n")
    substeps = []
    for node in tree.children:
        if node.type != "ordered_list":
            continue
        for item in node.children:
            start, end = item.map
            raw = "\n".join(lines[start:end]).strip()
            code = [
                n.content
                for n in item.walk()
                if n.type == "fence" and n.info.strip().lower().startswith("python")
            ]
            substeps.append((raw, code))
    return substeps


def _protocols_dirs():
    """Experiment.protocols_dirs, expanded to real paths. A single-source
    ("most specific wins") field, like almost everything else -- not
    "expand" semantics (union across config_files layers) unless that's
    explicitly requested later, the same way Experiment.scripts_dirs was
    (see docs/notes/protocols.md, README's "Expanded config fields" table)."""
    TrappyConfig()  # ensures TrappyConfig.current is set
    dirs = TrappyConfig.current.leaf("Experiment", "protocols_dirs") or []
    if isinstance(dirs, str):
        dirs = [dirs]
    return [os.path.expanduser(d) for d in dirs]


def _git_dependency_url(path):
    """The config.git_dependencies URL declared for local `path`, if any
    -- git_dependencies maps url -> local path, so this is a reverse
    lookup, used only to clone a declared-but-not-yet-cloned protocols_dir
    (see docs/notes/protocols.md §6)."""
    deps = TrappyConfig.current.expanded("config", "git_dependencies") or {}
    path = os.path.expanduser(path)
    for url, local in deps.items():
        if os.path.expanduser(local) == path:
            return url
    return None


def _resolve(name):
    """Find `name` under one of Experiment.protocols_dirs. If it isn't
    there yet but config.git_dependencies maps one of those dirs to a
    GitHub URL, clone it first -- rather than falling back to a second,
    hardcoded fetch path (the old githubfiles.get_file(), which always
    hit raw.githubusercontent.com/Trappy-Scopes/... regardless of what
    was actually configured). Returns (full_path, repo_root, relpath)."""
    dirs = _protocols_dirs()

    for repo_root in dirs:
        candidate = os.path.join(repo_root, name)
        if os.path.exists(candidate):
            return candidate, repo_root, name

    for repo_root in dirs:
        url = _git_dependency_url(repo_root)
        if url:
            ensure_cloned(url, repo_root)
            candidate = os.path.join(repo_root, name)
            if os.path.exists(candidate):
                return candidate, repo_root, name

    raise FileNotFoundError(
        f"Protocol '{name}' not found under any of Experiment.protocols_dirs "
        f"{dirs}, and no config.git_dependencies entry maps to one of them "
        f"to clone from."
    )


class Protocol:
    """Parse, render and execute a scientific protocol written in markdown.

    Expected document layout::

        ---
        kind: protocol
        authors: [TrappyUser]
        editors: []
        description: ...
        outcome: [...]
        requires_protocols: []
        see_also: []
        references: []
        ---
        # Title of the protocol
        1. Preamble line
        ## Requirements
        1. Requirement
        ## Steps
        ### Macro step 1
        1. Sub-step (optional)
           ```python
           scope.beacon.blink()   # run automatically
           ```
        ## Additional Information
        Optional closing notes.

    Resolved locally, from Experiment.protocols_dirs (see _resolve()) --
    never fetched over the network unless that local clone itself needs
    to be created first (via config.git_dependencies). Provenance (which
    commit, whether the working tree has uncommitted changes, and a
    GitHub permalink built from local git metadata alone) is computed at
    load time and logged once, not stored in the file itself -- see
    docs/notes/protocols.md §6.

    Three independent ways to actually go through it, sharing the same
    loaded state: `copy()` (freestyle -- just keep a copy for the
    record), `follow()` (sequential, prompts + optional per-step notes),
    and `enable_shortcuts()`/`disable_shortcuts()` (checkpoint-style,
    non-sequential, keyboard-shortcut-driven). `mark_as_executed()` /
    `unmark_as_executed()` record, independent of which mode was used,
    whether the protocol was actually carried out as loaded.
    """

    def __init__(self, protocol):
        self.name = protocol
        path, repo_root, relpath = _resolve(protocol)
        with open(path, encoding="utf-8") as handle:
            self.text = handle.read()

        self.commit, self.uncommitted_changes, self.permalink = provenance(repo_root, relpath)
        self.category = os.path.dirname(relpath)

        raw_meta, body = _split_frontmatter(self.text)
        self.meta = _normalize_meta(raw_meta)
        self.kind = self.meta["kind"]
        self._had_frontmatter = bool(raw_meta)

        self.title, sections = _split_sections(body)

        self.preamble = sections.get("Preamble", "")
        self.requirements = sections.get("Requirements", "")
        self.additional = sections.get("Additional Information", "")
        self.steps = _split_macro_steps(sections.get("Steps", ""))
        self.done = [False] * len(self.steps)
        self.responses = [[] for _ in self.steps]  # one list of responses per macro step

        self._log_loaded()

    def _publish_remote_link(self):
        """Per-file frontmatter overrides the repo-wide default (config's
        Experiment.protocols.publish_remote_link, default True)."""
        if "publish_remote_link" in self.meta:
            return bool(self.meta["publish_remote_link"])
        return TrappyConfig.current["Experiment"]["protocols"]["publish_remote_link"].get(True)

    def _log_loaded(self):
        """The "fanfare" log entry -- one event per load, whether or not
        the protocol is ever actually followed. No-op outside an open
        experiment (e.g. inspecting a protocol interactively)."""
        if Experiment.current is None:
            return
        publish = self._publish_remote_link()
        Experiment.current.log("protocol_loaded", attribs={
            "name": self.name,
            "kind": self.kind,
            "category": self.category,
            "commit": self.commit,
            "uncommitted_changes": self.uncommitted_changes,
            "permalink": self.permalink if publish else None,
            "authors": self.meta.get("authors"),
            "outcome": self.meta.get("outcome"),
        })

    def _require_protocol_kind(self, action):
        if self.kind != "protocol":
            raise ValueError(
                f"'{self.name}' is kind={self.kind!r}, not an executable protocol "
                f"-- refusing to {action} it (see docs/notes/protocols.md §5)."
            )

    def _require_open_experiment(self, action):
        if Experiment.current is None:
            raise RuntimeError(f"{action} needs an open experiment.")
        return Experiment.current

    def _render(self):
        """Serialise the protocol back to its markdown source.

        Completed steps (``self.done[i]`` is True) get a ``✓`` on their heading.
        """
        parts = []
        if self.meta:
            body = "\n".join(f"{key}: {value}" for key, value in self.meta.items())
            parts.append(f"---\n{body}\n---")

        parts.append(f"# {self.title}")
        if self.preamble:
            parts.append(self.preamble)
        if self.requirements:
            parts.append(f"## Requirements\n{self.requirements}")

        if self.steps:
            chunk = ["## Steps"]
            for (title, body), done in zip(self.steps, self.done):
                title = title[:-2] if title.endswith(" ✓") else title  # idempotent
                chunk.append(f"### {title} ✓" if done else f"### {title}")
                if body:
                    chunk.append(body)
            parts.append("\n".join(chunk))

        if self.additional:
            parts.append(f"## Additional Information\n{self.additional}")

        return "\n\n".join(parts) + "\n"

    def write(self, path, mark_done=False):
        """Write the protocol to ``path`` as markdown.

        mark_done: if True, flag every step as done before writing. Otherwise
                   the file reflects whatever was completed during ``follow()``.
        """
        if mark_done:
            self.done = [True] * len(self.steps)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self._render())
        return path

    def copy(self, dest_dir=None):
        """Freestyle mode -- keep a copy of this protocol's *original*
        source (not the annotated ``write()`` rendering) for the record,
        with no stepping through it. Defaults to exp_dir/protocols/, the
        same layout the real longterm scripts already use."""
        if dest_dir is None:
            exp = self._require_open_experiment("Protocol.copy() with no dest_dir")
            dest_dir = os.path.join(exp.exp_dir, "protocols")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(self.name))
        with open(dest, "w", encoding="utf-8") as handle:
            handle.write(self.text)
        return dest

    def show(self):
        """Render the static part of the protocol (metadata, preamble, requirements)."""
        print(Rule(self.title or self.name, style="bold"))

        if not self._had_frontmatter:
            print("[dim]No frontmatter declared for this file.[/dim]")
        elif self.meta:
            table = Table.grid(padding=(0, 1))
            table.add_column(style="bold cyan", justify="right")
            table.add_column()
            for key, value in self.meta.items():
                table.add_row(f"{key}:", str(value))
            print(Panel(table, title="Metadata", border_style="cyan"))

        if self.preamble:
            print(Markdown(self.preamble))
        if self.requirements:
            print(Panel(Markdown(self.requirements), title="Requirements", border_style="yellow"))

    def follow(self, globals_=globals()):
        """Sequential mode -- run the protocol step by step (blocking on
        user prompts), with an optional free-text note after each step's
        confirmation (see docs/notes/protocols.md §7).

        globals_: namespace in which inline ```python blocks are executed.
        """
        self._require_protocol_kind("follow")
        exp = self._require_open_experiment("Protocol.follow()")
        exp.log("protocol_followed", attribs={"name": self.name, "commit": self.commit})
        self.show()

        print(Panel(Align.center("Procedure"), style="bold yellow on blue"))
        for index, (title, body) in enumerate(self.steps, start=1):
            print(Markdown(f"## Step {index}: {title}"))

            # Each numbered sub-step runs and is confirmed on its own. A macro
            # step with no numbered list is treated as a single sub-step.
            substeps = _split_substeps(body) or [(body, _python_blocks(body))]
            replies = []
            for sub, (raw, code) in enumerate(substeps, start=1):
                if raw:
                    print(Panel(Markdown(raw), style="bold white on blue"))
                for source in code:
                    exec(source.strip(), globals_)
                label = f"{self.name}: {title} ({sub}/{len(substeps)})"
                replies.append(exp.user_prompt("done", label=label))

                note = Prompt.ask("Notes for this step? [Enter to skip]", default="")
                if note:
                    exp.log("protocol_step_note",
                            attribs={"protocol": self.name, "step": title, "note": note})

            self.responses[index - 1] = replies
            self.done[index - 1] = True

        if self.additional:
            print(Panel(Markdown(self.additional), title="Additional Information", border_style="green"))
        print(Panel(Align.center("Protocol Finished"), style="bold black on green"))

    def mark_as_executed(self, note=None):
        """Record that this protocol was actually carried out as loaded,
        independent of which mode (copy/follow/shortcuts) was used, and
        callable any time. Events are append-only (see
        docs/notes/protocols.md §2), so calling this and
        unmark_as_executed() back and forth just appends each time --
        the current status is whichever came last, with the full
        back-and-forth still visible in the log."""
        exp = self._require_open_experiment("Protocol.mark_as_executed()")
        exp.log("protocol_marked_executed",
                attribs={"name": self.name, "commit": self.commit, "note": note})

    def unmark_as_executed(self, note=None):
        """The opposite record -- this protocol was loaded/present for
        the experiment but not actually carried out (or a prior
        mark_as_executed() was wrong), with an optional reason."""
        exp = self._require_open_experiment("Protocol.unmark_as_executed()")
        exp.log("protocol_unmarked_executed",
                attribs={"name": self.name, "commit": self.commit, "note": note})

    def _step_shortcuts(self):
        """(step_title, keys, run) for every macro step declaring a
        ```yaml fence with a `shortcut:` key (see
        docs/notes/protocols.md §10.4) -- `run` (optional) is a snippet of
        real code to actually perform when the shortcut fires (e.g.
        `record_toss()`), not just a bare checkpoint marker; `None` if the
        step only wants the checkpoint logged, no code run."""
        found = []
        for title, body in self.steps:
            for block in _yaml_blocks(body):
                try:
                    data = yaml.safe_load(block)
                except yaml.YAMLError:
                    continue
                if isinstance(data, dict) and "shortcut" in data:
                    found.append((title, data["shortcut"], data.get("run")))
        return found

    def enable_shortcuts(self):
        """Checkpoint mode -- bind each step's declared shortcut so
        pressing it, in whatever order and however many times the user
        actually does the steps, both runs that step's declared `run`
        code (if any) and logs the checkpoint. The registered chord
        inserts `run` directly into the REPL line ahead of the checkpoint
        call -- same "insert literal code, auto-submit" mechanism every
        other keyboard shortcut already uses (utilities.keyboard_shortcuts),
        not a second, parallel exec path -- so `run` sees exactly the
        live __main__ namespace a person typing it by hand would.
        Registers under source="protocol", so disable_shortcuts()
        (== clear("protocol")) removes exactly these and nothing else."""
        self._require_protocol_kind("enable_shortcuts on")
        from core.utilities import keyboard_shortcuts
        import __main__

        def _checkpoint(step_title):
            if Experiment.current is not None:
                Experiment.current.log("protocol_checkpoint",
                                        attribs={"protocol": self.name, "step": step_title})
            print(Panel(f"Checkpoint logged: {step_title}", style="green"))

        __main__._protocol_checkpoint = _checkpoint

        keyboard_shortcuts.clear("protocol")
        shortcuts = self._step_shortcuts()
        for title, keys, run in shortcuts:
            checkpoint_call = f"_protocol_checkpoint({title!r})"
            code = f"{run}; {checkpoint_call}" if run else checkpoint_call
            keyboard_shortcuts.register(keys, code, submit=True, description=title, source="protocol")
        if shortcuts:
            keyboard_shortcuts.show_shortcuts()
        else:
            print(f"[dim]'{self.name}' declares no step shortcuts.[/dim]")

    def disable_shortcuts(self):
        """Un-bind whatever enable_shortcuts() bound."""
        from core.utilities import keyboard_shortcuts
        keyboard_shortcuts.clear("protocol")
