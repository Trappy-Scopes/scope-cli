# Restructuring plan

!!! note "Provenance"
    This document was written by **Claude** (Anthropic), in conversation with
    Yatharth on 2026-09-05, as a working plan for restructuring the
    Trappy-Scopes CLI. It records decisions taken in that session, the state of
    the repository at the time, and the reasoning behind each proposed change.

!!! success "Status — 2026-09-05, branch `restructure-20260905`"
    **Phases 0, 1 and 3 are done.** Phases 2, 4 and 5 are not started, and
    §3 (task stream), the ScriptEngine rework and the `analysis` recipe were
    explicitly deferred. Each phase in §5 carries its own status line.

    The boot has **not** been verified end-to-end — see §5 Phase 0/3 for
    exactly what was and was not tested.

---

## 1. The philosophy this is meant to serve

Trappy-Scopes has **two monolithic objects**:

- **`scope`** — the hardware. It is what generates data.
- **`exp`** — the experiment. It *drives* the scope and owns the data.

The synergy between them is what produces anything. At no point is the scope
meaningful by itself: the scope never runs a self-organised loop that collects
data without populating an experiment. It is the experiment's job to call the
scope to produce data.

This has one hard architectural consequence, from which most of this plan
follows:

!!! danger "The dependency rule"
    `expframework` may import from the hardware layer.
    The hardware layer may **never** import from `expframework`.

---

## 2. State of the repository (2026-09-05)

Findings from a survey of the tree, recorded here because several of them are
load-bearing for the plan.

### 2.1 The EXPENV hook already existed and was dead ✅ *now live*

`core/permaconfig/default_config.yaml:59` declared:

```yaml
startup_recipie: core.startup  # Startup procedure that defines how the CLI environment is created.
```

**No Python code read this key.** The pluggable-environment design was
specified in the config schema and never implemented. Phase 3 finished
something already started, rather than inventing it.

As of Phase 3, `expenv.build()` reads this key. The legacy value
`core.startup` is mapped to `freestyle`, so configs already deployed on the
scopes keep working without edits.

### 2.2 `exec()`-based loading was the central structural problem ✅ *removed*

```
main.py:12          exec(open("core/startup/__init__.py").read())
  └─ startup:167    exec(open("core/startup/useractions.py").read())
```

This was not a style wart. It was *why* environments could not be swapped:
both files only worked because they were textually injected into `main.py`'s
globals and depended on names (`exp`, `scope`) already existing there. That is
not something you can select, parameterise, compose or test.

It also actively breaks ordinary Python. During this session, adding a single
normal `import` that touched `core.startup` caused the import machinery to
re-execute the whole startup file in a fresh namespace, which crashed at
`User.exp_hook = exp` with `NameError: name 'exp' is not defined`.

!!! important "The distinction that matters"
    `exec` for **user scripts** is fine and should stay — it is morally what
    `python script.py` does, and it is what keeps lab scripts dumb and
    readable. `exec` for **module loading** is what has to go. Nothing about
    fixing the second requires giving up the first. See §4.

### 2.3 Layering violations, and how contained they are

| Violation | Locations | Status |
|---|---|---|
| `core` → `expframework` / `hive` | all inside `core/startup/`, plus `core/argparser.py:128` | ✅ **Fixed** (Phases 0/1). `core` has no upward imports; enforce with a CI grep. |
| `detectors` → `expframework` | `detectors/cameras/abstractcamera.py:12`, `detectors/cameras/rpi_hq_picam2.py:28` | ⏳ Open — inverts the dependency rule; fixed by §3, deferred |

### 2.4 Byte-identical duplicate files

- `core/external/pyboard.py` == `utilities/pyboard.py` — **identical**, 909 lines each ✅ *`utilities/` copy deleted; `core/external/` is the one `hive` imports*
- `core/utilities/fluff.py` == `utilities/fluff.py` — **identical**, 92 lines each ✅ *`core/` copy deleted; see the lesson in §2.5*
- `core/installer/installer.py` (138) vs `utilities/installer.py` (90) — **diverged**; someone edited one copy ⏳ *deliberately untouched, needs its own plan*

### 2.5 Caveat for any pruning work

**Two blind spots, both of which have now drawn blood.**

1. **YAML dotted paths.** This codebase resolves classes from strings in
   config (`kind: detectors.cameras.nullcamera.Camera`) through
   `import_module`. Static "who imports this" analysis *undercounts*: a file
   can look dead while being live in a deployed config on M1–M8.

2. **Relative imports.** In Phase 1 `core/utilities/fluff.py` was deleted
   after grepping for `core.utilities` and finding nothing. It was reached by
   `core/permaconfig/config.py` as `from ..utilities import fluff` — which no
   absolute-path grep matches. It broke the whole config import chain and was
   caught only by actually trying to import the recipes.

!!! warning "Rule"
    Nothing is deleted, and no module is renamed, without grepping for the
    absolute path, the **relative** form (`from ..x`, `from .x`), and the
    YAML `kind:` strings on every scope — and then actually importing the
    affected modules.

---

## 3. Design: the device task stream

### 3.1 The problem

`detectors/cameras/*.py` imports `Experiment` so a camera can record when it
turned on and off. The instinct is right — **the hardware layer must be
self-documenting** — but the mechanism inverts the dependency rule.

### 3.2 The design

Invert the flow. The hardware does not reach up to the experiment; the
experiment reaches down and subscribes.

```mermaid
graph LR
  cam("cam.capture()") -- emit --> TS
  pump("pump.run()") -- emit --> TS
  pico("pico.set()") -- emit --> TS
  TS["ScopeAssembly.taskstream"] -- subscribe --> exp["Experiment"]
  exp --> yaml["experiment.yaml"]
```

**One stream, on the assembly. Devices push. The experiment subscribes.**

A device emits whether or not an experiment exists. If nothing is subscribed,
events accumulate in a bounded ring buffer and nothing else happens — so the
scope still *works* standalone, while remaining not-meaningful standalone.
When an `Experiment` opens, it attaches to the stream and (optionally)
backfills what the ring buffer already holds.

### 3.3 Answering: per-device streams, merged?

**No — one central stream.** Per-device buffers would mean merging by
timestamp, which is exactly the "lot of computation" to be avoided, and it
makes live streaming impossible (you cannot merge a stream that has not ended).

The single exception is **remote devices** (RPyC over the network, the M1→M2
case). Those cannot append synchronously to a local list, so they buffer
locally and drain into the central stream, recording *both* clocks — the
remote emit time and the local receipt time — because the two machines'
clocks are not the same clock.

### 3.4 Answering: how do events register themselves?

An opt-in decorator, defined in the ABC layer, on the set of methods that
should record. Explicit, greppable, no magic, no cost on methods that do not
use it.

```python
# proposed: hive/recording.py  (later scopeparts/abc/recording.py)

class TaskStream:
    """Single-writer, append-only record of what the hardware did."""

    def __init__(self, maxlen=100_000):
        self._events = deque(maxlen=maxlen)   # bounded: long runs must not grow forever
        self._seq = itertools.count()         # atomic under the GIL
        self._sinks = []                      # Experiment attaches here

    def emit(self, event):
        event["seq"] = next(self._seq)
        event["machinetime"] = time.time_ns()
        self._events.append(event)
        for sink in self._sinks:
            try:
                sink(event)
            except Exception:
                log.exception("task sink failed")   # a bad sink never propagates
        return event


def records(kind="device_task"):
    """Mark a device method as one that registers itself on the task stream."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            stream = getattr(self, "_taskstream", None)
            if stream is None:
                return fn(self, *args, **kwargs)      # standalone device still works
            start, ok, err = time.time_ns(), True, None
            try:
                return fn(self, *args, **kwargs)
            except BaseException as e:
                ok, err = False, repr(e)
                raise
            finally:
                try:
                    stream.emit({"type": kind, "device": getattr(self, "name", None),
                                 "task": fn.__name__, "start_ns": start,
                                 "end_ns": time.time_ns(), "ok": ok, "error": err})
                except Exception:
                    log.exception("task recording failed")   # never kills the call
        return wrapper
    return decorator
```

Usage stays trivial, and the camera stops importing `Experiment` entirely:

```python
class Camera(Detector):
    @records()
    def capture(self, action, name, **kwargs):
        ...
```

`ScopeAssembly.add_device()` injects the stream at mount time
(`deviceobj._taskstream = self.taskstream`), so nothing has to be wired by hand
per device.

### 3.5 Answering: aggregation

With one central stream, aggregation is free — there is nothing to merge.
Ordering is by `machinetime` (`time.time_ns()`, already the convention in
`ExpEvent` and `Measurement`) with the monotonic `seq` as tie-breaker. `seq`
also makes **dropped events detectable**: a gap in the sequence is a lost
record, which a timestamp alone would never reveal.

### 3.6 Safety

This runs a lab with pumps, lights and live cultures. The rules, in priority
order:

1. **Recording must never kill a hardware call.** Every emit is wrapped in
   `try/except` that logs and swallows. A full disk must not abort a perfusion.
   This is the single most important rule here.
2. **A failure must never go unrecorded.** `try/finally`, so an exception still
   emits before it propagates. A failed capture is scientifically meaningful.
3. **Emit must not block.** Append to memory only; flush to disk
   asynchronously. A synchronous write or network push inside `emit()` could
   stall an actuator control loop mid-operation.
4. **Bounded memory.** `deque(maxlen=…)`. `scripts/longterm/` runs for days;
   an unbounded list is an eventual OOM on a Raspberry Pi.
5. **Thread safety.** `ExpScheduler` already runs a background thread, and
   pumps and cameras may run in their own. `deque.append` is atomic under the
   GIL and `itertools.count()` is atomic — this is why they are used above
   rather than a plain list and an `n += 1` counter, which is a race.
6. **Drain on close.** `Experiment.close()` must drain the stream before
   writing final YAML, or the last events of every run are lost.
7. **Clock skew across machines** is recorded, never silently reconciled — see
   §3.3.

---

## 4. Design: EXPENV builders, and how scripts keep their globals

### 4.1 `main.py` stays trivial

```python
from core.permaconfig.config import TrappyConfig
from expenv import build

env = build(TrappyConfig())   # reads config.startup_recipie, returns a namespace
```

The recipe is a **function that returns a namespace**, not a file that mutates
an ambient one. That is the whole change, and it is what makes recipes
selectable, parameterisable and testable.

### 4.2 Answering: how to stop passing `globals()` to `ScriptEngine`

The reason `exec` was reached for is that **things need to live at the top
level** — a lab script should be able to say `scope.cam.capture(...)` with no
imports and no boilerplate. That requirement is correct and is not being given
up.

The trick is that the REPL's top level *is* a real, addressable namespace:
`__main__.__dict__`. So the builder merges into it explicitly —

```python
import __main__
vars(__main__).update(env)     # scope, exp, tools are now genuinely top-level
```

— and `ScriptEngine.run()` defaults to that namespace instead of being handed
one:

```python
def run(scripts=None, namespace=None, raise_exceptions=False):
    namespace = namespace if namespace is not None else vars(__main__)
    ...
    exec(source, namespace)
```

Which means:

- Scripts stay exactly as dumb as they are today — plain `.py`, top to bottom,
  `scope` and `exp` simply present. **No change to any existing script.**
- `ScriptEngine.run(globals(), ...)` becomes `ScriptEngine.run([...])`.
- `exec` is still used for scripts, on purpose. Only *module loading* by `exec`
  goes away.

This also closes a latent bug: today `ScriptEngine.run(globals_)` receives
`main.py`'s globals only as an accident of the `exec` chain, so a script that
rebinds `exp` does not reliably update anything else that holds it.

### 4.3 The recipes

| Recipe | Behaviour |
|---|---|
| **`freestyle`** | Today's behaviour: full scope assembly, experiment environment, all user tools, banners, tree, keybindings. The default, and the one for freestyling experiments. |
| **`raw`** | Minimal. Constructs the `ScopeAssembly` — hardware really does come up — and imports nothing else. Prints one line (`scope assembly created`), no banner, no device tree, no error summary. For calling the utility directly and then driving it by hand. |
| **`analysis`** | No hardware at all. See §4.4. |

### 4.4 On the analysis environment

This one is worth building because the payoff is **already designed and
unused**. The `Measurement` docstring in `expframework/measurement.py` states
the goal explicitly: a schema that "allows the user to combine an arbitrary
number of experiments for analysis, **without any data filtering**". Every
measurement already carries `eid`, `sid`, `scopeid`, `measureid`, `measureidx`
and three separate clocks. Nothing currently consumes that.

An `analysis` recipe would be the consumer:

- **Touches no hardware.** No serial ports, no `ScopeAssembly`, no RPyC server.
  Safe on a laptop, on the IGC cluster, or on any machine where the scope is
  physically absent.
- **Opens experiments read-only.** This needs a new path —
  `Experiment.__init__` currently creates directories, appends a session,
  `chdir`s and mutates `experiment.yaml`, none of which an analysis session
  should do. A read-only `Experiment.load(eid)` is a prerequisite.
- **Loads many experiments into one frame.** `df = load_experiments([...])`
  returning the concatenated measurement table — across scopes, across runs,
  across days. This is the thing the `Measurement` schema was built for.
- **Hands off to IPython/Jupyter** rather than owning a REPL loop, since there
  is no hardware to hold.

Prior art worth reading before building: the `exp-legacy-read` skill already
knows how to load legacy experiment directories, measurement streams and
day-level Metaexperiment logs. The analysis recipe should not reinvent that.

---

## 5. Revised phase plan

Order reflects decisions taken on 2026-09-05.

### Phase 0 — Replace `exec` module loading with an explicit namespace ✅ done

*Commit `363a347`.* The enabling change; nothing else was safely possible first.

- `main.py` calls a builder and merges the result into `__main__` (§4.1, §4.2).
  It is now two lines.
- **Deferred:** `ScriptEngine.run()` still takes an explicit namespace argument
  rather than defaulting to `vars(__main__)`. The recipe passes it the
  namespace it just built, so no script changed — but the ScriptEngine rework
  in §4.2 has not been done.
- One constraint the script→function conversion forced: `from core.argparser
  import *` had to become a plain import, because **`import *` is a
  SyntaxError inside a function**. `Share` is now imported explicitly.

### Phase 1 — Mechanical moves, zero behaviour change ✅ done

*Commit `6cdef3f`.*

- `core/startup/` → `expenv/` — this alone removed the `core` → `expframework`
  violation.
- Fixed `core/argparser.py:128`: it records the scriptlist in `Share.argparse`
  and the recipe hands it to the ScriptEngine.
- Deleted the two byte-identical duplicates (§2.4) — one of which broke the
  build via a relative import; see the lesson in §2.5.
- Moved `gui/fim.py` into `utilities/` (+5 import sites in `scripts/`).
- **Explicitly out of scope: `installer.py`.** The diverged copies are a
  symptom of an unsolved problem — how installation should work at all — and
  that needs its own plan. Not touched.
- **Checkpoint met:** `core` imports nothing above it. Still worth a CI grep so
  it cannot regress.

### Phase 2 — Task stream (§3) ⏳ deferred

- `TaskStream` + `@records` in the ABC layer.
- `ScopeAssembly` owns one stream and injects it at `add_device`.
- `Experiment` subscribes on open, drains on close.
- **Cameras stop importing `Experiment`** — the violation in §2.3 disappears.
- This is additive: it does not move or rename any module.

### Phase 3 — EXPENV for real (§4) ✅ done (minus `analysis`)

*Commit `363a347`.*

- `expenv.build()` reads `config.startup_recipie` and dispatches. Accepts a
  short name, a full dotted path to any module exposing `build(config)`, or the
  legacy `core.startup` → `freestyle` (§2.1).
- Shipped `freestyle` and `raw`. **`analysis` deferred** — it needs a read-only
  `Experiment.load(eid)` first (§4.4).
- `useractions` is imported rather than `exec`'d, and gained the
  `ScopeAssembly` import it always referenced but never had. **It has not been
  split into separately registered tools** — that part of the phase is
  outstanding.

!!! warning "Not verified by booting"
    The CLI was not started end-to-end: startup opens serial ports, starts an
    RPyC server and can mount SMB shares. `expenv`, `raw` and `useractions`
    import cleanly and all recipes compile and resolve, but `freestyle`'s
    import chain cannot complete on a machine without `pypandoc`, `reportlab`
    and `html2rml` — imported unconditionally by `expframework/report.py`, on
    `main` too, so pre-existing rather than a regression. **Boot on a real
    scope before trusting this.**

### Phase 4 — Eviction and pruning ⏳ not started

- `pico_firmware/` → its own repository. It is MicroPython, for a different
  interpreter on different hardware; it is not part of this package.
- `gui/` → delete if it is empty of anything real.
- `optics/` → **retained**, and eventually folded into the hardware layer
  alongside actuators, detectors, assemblies and monitors.
- Prune dead code against **both** Python imports and YAML `kind:` strings
  (§2.5). First candidates: `_to_delete/`, `optics/old_cli/`, `gui/dev/`,
  `utilities/autocompleter.py`.

### Phase 5 (last) — `hive` → `scopeparts` ⏳ not started

**Deliberately deferred to the end.** This is the most essential and most
invasive change, and further work is expected to land on top of it that could
change the shape again. Renaming early means renaming twice.

Sketch, for when it happens:

```
scopeparts/
├── abc/          # the pure interfaces — this is what `hive` was meant to be
│   └── BaseDevice, Actuator, Detector, Monitor, TaskStream, @records
├── assembly.py   # ScopeAssembly
├── processors/   # linux, micropython, remote transport
├── actuators/    # implementations (was actuators/)
├── detectors/    # implementations (was detectors/)
├── optics/       # (was optics/)
└── network/      # rpyc, mqtt, exchange
```

The tension to resolve: `actuators/` and `detectors/` provide
*implementations*, while `hive` was meant to be *abstract* — but `hive` also
carries a lot of concrete MicroPython and serial code. The split above puts
interfaces in `abc/` and transport in `processors/`, which is what makes the
absorption coherent rather than just a bigger pile.

!!! warning "Migration cost"
    This phase rewrites every `kind:` dotted path in every deployed YAML on
    every scope. It needs either an alias map from old paths to new, or a
    config migration script — otherwise M1–M8 break on their next `git pull`.
    This cost is the main reason it goes last.

---

## 6. Open questions

- **Installers.** Two diverged copies and no agreed model. Needs its own plan.
- **`utilities/`** is doing too much and is not really a category. Left alone
  for now; worth revisiting after Phase 4.
- **`ScopeAssembly.close()` crashes at exit when no assembly was built.** The
  `atexit` handler at `hive/assembly.py:72` iterates
  `ScopeAssembly.current.devices` without checking that `current` is set, so
  any process that imports the assembly and exits without building one dies
  with `AttributeError: 'NoneType' object has no attribute 'devices'`.
  Pre-existing; a one-line guard.
- **Report dependencies are unconditional.** `expframework/report.py` imports
  `pypandoc`, `reportlab` and `html2rml` at module scope, and
  `Experiment` imports `ExpReport`, so a machine without those three cannot
  import `Experiment` at all. Since `exp_report` is a config flag that
  defaults to `false`, these should be imported lazily.
- **`scripts/`** stays in-tree — a small curated script module is genuinely
  useful here — but the boundary between "example" and "production protocol"
  is undefined.

---

## 7. The configuration layer

Decisions taken 2026-09-05. The agreed order of work is **bottom-up**: settle
the configuration layer first, then let the experiment and the scope inherit
those changes.

!!! danger "`default_config.yaml` is the master document, and it does not boot"
    The template is the file copied to a new scope, so it is the spec. But it
    has drifted from both the code and every deployed config:

    | `default_config.yaml` says | Code reads | Live configs use |
    |---|---|---|
    | `ScopeAssembly:` | `scopeconfig["devices"]` | `devices:` |
    | `Experiment.exp_dir` | `config["config"]["expdir"]` | `config.expdir` |
    | `Experiment.file_server` | `config["config"]["file_server"]` | `config.file_server` |
    | `config.git_sync.repos` | `config["config"]["git_dependencies"]` | `config.git_dependencies` |
    | *(absent)* | `config["Experiment"]["scripts_dirs"]` | `Experiment.scripts_dirs` |

    The code and the eight deployed scopes agree with each other; the template
    and the README are the outliers. Copying `default_config.yaml` to a new
    scope today raises `KeyError: 'devices'` and mounts nothing.

    **Fix direction: bring the template up to what the code and the working
    scopes do.** Changing the code to match the template would break M1–M8.

    The README is a design document — wishful thinking, not a spec. Where the
    two disagree, the template wins; where the template and the code disagree,
    the code and the live configs win until deliberately migrated.

Two more drifts of the same kind, both currently harmless by accident:

- `assembly.py:64` reads `scopeconfig["abstractions"]` (plural); live configs
  write `abstraction:` (singular). Dead only because `freestyle` calls
  `ScopeAssembly(scopeid)` with no config, so the branch never executes.
- At least one live config declares `lit` at top level rather than under
  `devices:`, so it never mounts.

### 7.1 `active:` belongs in TrappyConfig, not in each consumer

Today `active:` is honoured ad hoc: `ExpSync` checks `file_server.active`,
while `startup.py:12` does `if scopeconfig["config"]["git_sync"]:` on a dict,
which is always truthy — so `git_sync.active: false` is silently ignored. For
devices nothing checks it at all.

**Decision:** implement it once, at the `TrappyConfig` level. A block with
`active: false` is simply *not exposed* by the config object — it is still in
the file, but consumers never see it. Absence of the key means `true`.

Consequence to handle deliberately: this lets a user disable configuration
that is actually required (an experiment directory, say), and the failure
would otherwise be silent. So a missing-but-required block must raise a clear
warning naming what was disabled. `confuse` may already have a mechanism for
this — check before hand-rolling.

### 7.2 `config_redact_fields`

Documented, never implemented, and it matters: the `config_server` block
rsyncs `trappyconfig.yaml` — which holds `username`/`password` in cleartext —
to a share.

**Intent:** when a *copy* of the `TrappyConfig` object is requested, the
redacted fields are omitted. The motivating case is that **every experiment
should carry a copy of the configuration it ran under**, so a run is
reproducible from its own directory — but that copy must not carry the
passwords or server addresses.

### 7.3 The launcher (`./trappyscope`)

`git_sync` was never enabled because there was no correct place to call it:
it has to happen *before* the code launches, before the scope is constructed,
before the experiment environment is built. That is a layer that does not
exist yet. The `./trappyscope` script was the beginning of it.

What the launcher should do, in order, before handing off to `main.py`:

1. **Validate the configuration and produce a readable traceback.** Raw
   `PyYAML` errors do not say *where* the mistake is, which makes a broken
   config painful to diagnose on a headless scope. Worth pulling in a schema
   validation library rather than hand-rolling.
2. **Sync the configuration with the config server.** Read the server address
   from the local config, ask whether the stored configuration has changed,
   and if so rewrite the local file and reload. The point is a single place to
   edit the configuration of every microscope at once: each scope picks up its
   new configuration on next boot. (Whether to re-run the whole loop after a
   reload, or apply once and continue, is open — probably apply once.)
3. **Git-sync the declared repositories**, including this codebase, so every
   scope updates itself on launch.
4. **Activate the declared environment.** The `venv` block already exists in
   the template. This must be package-manager agnostic — conda here, but
   possibly `venv` or something else on another machine — so it needs a crude,
   general method of finding the right Python rather than a clean one.

---

## 8. Device coercion — `metaclass`, `read_method`, `write_method`

**Noted, not scheduled.** These are optional and explicitly not being built
yet; this section exists so the design is not lost.

The purpose is the project's central claim — *"seamlessly interfaces with any
existing python package"*. Today `kind:` must point at a class that already
has the right shape, so integrating a foreign library means hand-writing a
wrapper. The coercion mechanism removes that: **you should not need to write
a wrapper for most foreign code.**

`kind:` calls a constructor, and that is all that is required. On top of that:

- **`read_method` / `write_method` alias a foreign method into the Trappy
  contract.** Calling `read()` on an object that has no `read()` dispatches to
  whatever method the config named. The declared `args`/`kwargs` are bound
  with `functools.partial`.
- **Declaring them elevates the object** into a detector or an actuator.
- **`metaclass:` declares intent, and is validated against the methods:**

    | Declared metaclass | Requires |
    |---|---|
    | detector | `read_method` |
    | actuator | `read_method` **and** `write_method` |

    A declaration that does not meet its requirement is a configuration
    error, caught at mount time rather than at first use.

- A **`config_method`** is wanted on the same principle.

This belongs in the scope-parts layer, alongside the ABCs.

---

## 9. `tree` and `devices` are not the same thing

They are currently two flat dicts holding identical objects, which is why the
distinction looks redundant. It is not — it was never finished.

- **`devices`** is the flat list of devices attached to the scope.
- **`tree`** is meant to be *structured*. Proxy devices constructed by another
  device belong inside that device's namespace: the objects `scope.pico`
  creates during handshake should live under `pico`, not at top level.

### 9.1 Aggregates

The tree should also carry **aggregate nodes**. Given four motors mounted as
`scope.motor1` … `scope.motor4`, an aggregate `set` becomes a node covering
all four, so that `scope.set.stop()` stops every motor in it — one call
fanning out across the group, while the individual devices remain
addressable.

This already exists as `ActionSet` in `pico_firmware`, but it is hardcoded:
the motors are declared into the group by hand at construction. Membership has
to be declared *somewhere*, but it should not have to be hardcoded — and for
the proxy objects a device creates during handshake, it can be derived
automatically.

### 9.2 Smaller fixes agreed

- **Device names need a guard.** `add_device` does `setattr(self, name, obj)`
  with no check, so a device called `open`, `close` or `devices` silently
  overwrites the assembly's own API. Either reject names that collide with an
  existing attribute, or keep a reserved-word list — undecided which is
  better.
- **`abstraction` goes.** The concept is not worth keeping; the ignored
  `open(..., abstraction=)` parameter and `__abstraction__()` go with it.
- **The hardcoded `sys.path.append` at `assembly.py:112` goes.** It points at
  one machine and contains a stray quote, so it has never done anything.
- **`__device_type__`** was never made to work. It stays unimplemented rather
  than half-present.

---

## 10. On the config file's location

`TrappyConfig` looks in `~/trappyverse/trappyconfig.yaml` first and falls back
to `~/trappyconfig.yaml`. This is legacy and intent sitting side by side: the
intent is that everything lives in `trappyverse/`, but on most scopes today
the file is still in the home directory. The fallback is deliberate and stays
until the files are moved.

Separately, the utility is meant to be callable from anywhere, which is why
the lookup is absolute rather than relative to the working directory.
