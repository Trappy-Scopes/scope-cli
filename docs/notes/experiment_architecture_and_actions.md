# Experiment architecture, actions, sync, and scheduling — review

!!! note "Provenance"
    Written by **Claude** (Anthropic), in conversation with Yatharth on
    2026-09-08. Review-only, same cadence as
    [protocols.md](protocols.md) and
    [scripts_measurements_plotting.md](scripts_measurements_plotting.md) —
    explicitly requested while those two are still pending review. Nothing
    here is implemented. Deliberately does not touch the core `Experiment`
    class body itself (per your own framing — "very central... touching
    it last") beyond what's needed to explain the findings below.

!!! danger "Found while reviewing: `exp.events()` is currently unreachable"
    Not something you asked me to look for — found it while tracing the
    mixin `__init__` chain for §B below, and it's urgent enough to lead
    with: **`ExpReport.__init__` sets `self.events = ""` (a plain string,
    meant to hold rendered report text), which — because it runs after
    `Experiment`'s own class body is already defined — shadows the
    `events()` *method* I added to `Experiment` earlier this session
    (`docs/notes/protocols.md` §2.4/§8).** Verified directly: on a real,
    freshly-constructed `Experiment`, `exp.events` is the string `''`, and
    `exp.events()` raises `TypeError: 'str' object is not callable`. This
    predates my changes — `ExpReport.__init__`'s `self.events = ""` line
    was already there — but it means the `RecordSet`-backed event editor I
    built this session is currently correct in isolation (unit-tested
    against a fake) but **inert on a real Experiment** until this
    collision is resolved (rename `ExpReport`'s field — it's clearly
    meant to be report-rendering scratch space, not "the event log").
    Flagging rather than fixing, since you asked me to hold all changes
    until review — but you should know before relying on `exp.events()`
    for anything. **Correction, since you've since said `ExpReport` is
    *not* being removed yet**: this needs its own direct fix (rename the
    `self.events` field to something like `self._report_events_str`),
    not something that rides along with a removal that isn't happening
    in this pass. Doesn't change the broader mixin-`__init__` finding in
    §B below either way — that's a pattern risk, not tied to this one
    class.

---

## A. Extracting `track`/`delay`/`user_prompt`/`multiprompt`/`note`/`write`/`interrupted`

Yes — these seven methods are already a coherent unit (every one of them
is decorated `@is_event @autosave` and exists specifically to wrap a
common experimental action in automatic logging), and the codebase
already has the exact precedent to follow: `ExpSync`
(`expframework/expsync.py`), `ExpReport` (`expframework/report.py`), and
`ExpNotebook` (`expframework/notebook.py`) are each already a `class Exp*`
mixed into `Experiment`'s own multiple-inheritance list. A new
`expframework/actions.py` → `class ExpActions` holding these seven methods
is a direct, low-risk application of a pattern this codebase already
uses three times, not a new architectural decision.

Proposed name: **`ExpActions`**, since "task" collides with `schedule`'s
own vocabulary (§D) and "try" isn't any current method's real name (see
below) — happy to use whatever reads best to you.

One naming note while reviewing these: I could not find an
`Experiment.try` or `Experiment.task` anywhere in the codebase — the
closest real matches to what you likely meant are `Experiment.track()`
(wraps calling a function, logs duration + a description — this is what
`celltracking/livetrack.py`'s `track_sample()` actually uses, confirmed
via this session's earlier scripts survey) and `Experiment.user_prompt()`
(the confirmation-wait primitive `Protocol.follow()` also now uses, per
`docs/notes/protocols.md`). If you had a third, different method in mind,
tell me its real name and I'll fold it in.

---

## B. Is mixin-via-multiple-inheritance the right pattern?

Traced the actual `__init__` chain rather than assuming the pattern works
because it's already used three times. It's shakier than it looks:

```python
class Experiment(ExpSync, ExpReport, ExpNotebook, ClockGroup):
```

`Experiment.__init__` calls exactly two of these four explicitly/via
`super()`:

- `super().__init__(self.name, destination_dir=self.destination_dir)` —
  reaches `ExpSync.__init__` (first in the MRO). **`ExpSync.__init__` has
  no `super().__init__()` call of its own** — confirmed by reading the
  whole file — so the cooperative chain **stops there**. `ExpReport`,
  `ExpNotebook`, and `ClockGroup`'s own `__init__` methods are never
  reached through this call at all.
- `ExpReport.__init__(self, self.eid)` — called separately, explicitly,
  right after. This is the one that sets `self.events = ""` (see the
  danger box above).

`ExpNotebook.__init__` and `ClockGroup.__init__` are **never called by
anything**. For `ClockGroup` this is harmless by accident —
`Experiment.__init__` happens to set `self.expclock`/`self.all_clocks`
itself, duplicating what `ClockGroup.__init__` would have done. For
`ExpNotebook` it is **not harmless**:

```python
# ExpNotebook.__init__ -- never actually called, and dangerous if it were:
def __init__(self):
    self.logs = {}       ## Inherited object
    self.note = None     ## Inherited object
    self._notebook = None
```

If this *were* ever reached (e.g. by "fixing" the broken `super()` chain
the naive way — making every mixin cooperatively call `super().__init__()`),
it would silently **wipe `self.logs`** (the entire event/results/session
log, already loaded from disk by this point) and **replace the
`Experiment.note()` method with `None`**, breaking `ExpNotebook`'s own
`_set_notebook()` two lines later (`self.note(text)` → `TypeError:
'NoneType' object is not callable`). The `## Inherited object` comments
read as placeholders — documentation of what the author expected some
other class in the chain to already provide — not real initialization.

**What this means for the pattern, concretely**: today's mixins aren't
really cooperating via MRO at all — each one is a bag of methods that
*assumes* `Experiment.__init__`'s own body has already set up whatever
state it needs, by coincidence of call order, not by contract. The
`self.events = ""` collision is exactly what happens when that
assumption is wrong: two mixins independently claiming the same attribute
name, with nothing in the language or the code structure to catch it.
Multiple inheritance flattens every mixin's names into one shared
instance namespace — there's no `self.report.events` vs
`self.notebook.events` distinction, they're all just `self.events`.

**Deferred, on request — major restructuring, not a quick patch**: fixing
this properly means auditing every mixin's `__init__` for what it
actually needs vs. what it wrongly assumes it owns (`ExpNotebook`'s
`self.logs = {}`/`self.note = None` need to go entirely, not just move),
then wiring a real cooperative `super().__init__()` chain across all
four (plus whatever `ExpActions` becomes). Not attempting this now;
recorded here so it isn't lost. Confirmed harmless to leave alone in the
meantime — grepped every call site of `.events` in the whole codebase
(`scripts/`, `expframework/`, `launcher/`, `hive/`, `utilities/`,
`core/`): the only two hits are the `self.events = ""` line itself and an
aspirational comment in `Experiment`'s own docstring
(`## Clean until exp.events() return coherant...`) — `exp.events()` (the
method, before or after this session's change) has **never actually been
called anywhere**, so today's collision has zero blast radius on existing
code; it only blocks the new `RecordSet`-based editing feature from being
reachable.

**Recommendation for `ExpActions` (and anything new going forward)**:
same multiple-inheritance mixin pattern is fine to keep using *if* each
new mixin (a) declares no `__init__` at all, or (b) if it must, is
audited against every sibling mixin's own attribute names first — cheap
now, with four mixins; expensive to audit by hand once there are ten.
`ExpActions` specifically is low-risk either way, since `track`/`delay`/
`user_prompt`/etc. don't need their own `__init__` state (they only touch
`self.logs`/`self.expclock`, already set up by `Experiment.__init__`
itself) — but worth deciding now, once, whether future mixins should
move to **true composition** instead (`self.sync = ExpSync(...)`,
`self.notebook = ExpNotebook(...)`, called explicitly, name-namespaced by
construction) rather than adding a fifth name to the flat shared
namespace. Not proposing a rewrite of the three existing mixins — just
flagging the fork before a fourth or fifth one gets added on the current
pattern.

---

## C. `ExpSync` — the reconnect-negotiates-a-new-directory bug, found precisely

Traced `destination_dir` through both files. `Experiment.__init__`:

```python
self.destination_dir = None
if "destination_dir" in self.logs:
    self.destination_dir = self.logs["destination_dir"]
super().__init__(self.name, destination_dir=self.destination_dir)
```

This clearly *intends* to reuse a previously-negotiated directory —
checking `self.logs` (loaded from the experiment's own `experiment.yaml`)
for one first. But **`self.logs["destination_dir"]` is never written
anywhere** — grepped the whole file, these three lines are the only
references to it. `ExpSync.__init__` receives `destination_dir=None` on
every single open (since it's never actually found in `self.logs`),
and — because `destination_dir` is falsy — always recomputes a *fresh*
one from `effify(ExpSync.destination_fmt, locals())`, using the
config's `destination` template (e.g. `"{date}"`) evaluated against
**today's** date/time, not the experiment's original creation date. Two
sessions of the same experiment on two different days negotiate two
different remote directories, exactly as you described.

**The fix is one line** — after `ExpSync`'s init resolves
`self.destination_dir` (freshly computed, or reused), persist it back:
`self.logs["destination_dir"] = self.destination_dir`, anywhere before
the next save. Small and surgical; not applying it yet since this whole
document is pending review, but wanted the root cause nailed down
precisely rather than a vague "it's probably somewhere in there."

Otherwise, agree this module is close to done — `sync_dir`/`sync_file`/
`sync_file_bg` are coherent, and the `ionice`/`--no-compress`/`--inplace`
choices for large binary experiment files are sound as documented in the
code's own comments.

---

## D. `ExpScheduler` — the unused method, and the "past regression" story

The method you mean is almost certainly **`post_register(self, name)`** —
searched the whole codebase for anything priority-shaped and found
nothing else close; happy to be corrected if you meant something else.
Grepped every call site: **exactly one**, in
`scripts/calibration/peristaltic/longterm_perfusion_test.py`. It is not
invoked automatically by `schedule.Scheduler.every(...).do(...)` (the
underlying third-party `schedule` library — checked its actual API
surface directly — has no hook, no "on job registered" callback, no
concept of priority at all) — `post_register()` only ever produces a log
entry if the script author remembers to call it, by hand, immediately
after every `.do(...)` call. Across every script this session's earlier
survey read, only one out of a dozen+ scheduling call sites does this.
**Confirms your own read exactly: a feature that requires the scientist
to remember an extra, separate call every time it's registered, with
nothing enforcing it, is going to go unused** — this is really the same
underlying problem as §F below (things only get logged if someone
remembers to call the logging-shaped wrapper).

On the past regression: I have no way to see what that earlier change
actually did (not in this session's history, and the working tree today
reflects whatever state things eventually settled to) — but the
class as it stands now (`__init__`, `post_register`, `loop`) is small and
legible; nothing about it looks currently broken. If you want a concrete
second opinion on a specific past diff/commit, point me at it and I'll
review that directly rather than speculating about what went wrong
before.

---

## E. Precision timing — no such module exists; the real finding is in `delay()` itself

Searched the whole codebase for anything matching "precision"/"timing" —
nothing at `core.idioms` or anywhere else corresponds to a dedicated
precision-timing module. `Experiment.delay(name, seconds, steps=100)`
(the actual, only, timing-related method) does:

```python
for i in track(range(steps), description=...):
    time.sleep(seconds/steps)
```

Researched this specifically (§F) rather than assume it's fine because it
exists: **subdividing a sleep into `steps` separate `time.sleep()` calls
for a progress bar is a confirmed anti-pattern, not a precision
mechanism** — PsychoPy's own timing documentation is explicit that each
additional sleep call overshoots by its own OS-scheduling jitter, and
that jitter *accumulates* across calls; their own "non-slip timing"
guidance is to never chain relative sleeps, only ever wait to one
absolute deadline computed up front. `delay()`'s 100-step default
subdivision is, if anything, *less* precise than one bare `time.sleep(seconds)`
would be, purely because it has 100x the OS-scheduling overshoot
opportunities. Worth fixing regardless of anything else in this
document — see §F's concrete recommendation.

---

## F. External research — auto-logging every action, not just the ones with a wrapper

Delegated this to a research pass rather than guess; findings, with the
concrete recommendation each one leads to:

**Bluesky's `RunEngine`/`Msg` model** (NSLS-II/Brookhaven's beamline
orchestration framework) is the most directly relevant prior art. A
"plan" is a generator that `yield`s `Msg` objects (`Msg('set', ...)`,
`Msg('sleep', ...)`, ...) instead of calling hardware directly — the
architecture's own documentation states plans should *never* touch
hardware directly. That's the actual mechanism behind "everything gets
logged automatically": **logging isn't opt-in per action, because there
is structurally only one place any action can happen at all** — the
`RunEngine`'s central dispatch loop, which every `Msg` must pass through
to have any effect, and which logs (or can hook) every message
regardless of type. This is the real answer to "do I need a decorator, or
can I replace the action" — closer to your "replace the action" instinct
than a decorator: **the action's only legitimate entry point should be
the logging wrapper, not a parallel path that happens to also be
logged if you remember to call it.**

**PsychoPy/PsychToolbox** confirm §E precisely, and give the concrete
recipe: sleep coarsely for most of the interval, then busy-poll a
high-resolution clock for the last ~100-200ms where precision actually
matters (`PsychoPy.core.wait`'s `hogCPUperiod`) — full accuracy without
burning CPU for the whole duration.

**No heavyweight AOP needed for the general "auto-log arbitrary calls"
problem.** Two lightweight, already-idiomatic-in-Python options came back
as the standard answers: a context-manager-scoped monkeypatch (revert
cleanly on experiment close — the `pytest.monkeypatch` pattern), or —
more fitting here — a thin transparent proxy (`wrapt.ObjectProxy`) wrapped
around a *device* the moment it's mounted onto `ScopeAssembly`, so every
method call on that device logs itself for free, with **zero change
required to the scientist's own code** (`scope.motor.move(5)` gets logged
even though nobody wrapped that specific call). `sys.settrace`/PEP 669's
`sys.monitoring` (3.12+) is real and much cheaper than the old
`settrace`, but is a debugger/profiler-shaped tool, not an audit-trail
one — not recommending it here.

**Concrete recommendations**:

1. **Fix `delay()`'s drift** per the PsychoPy recipe: one coarse
   `time.sleep()` against an absolute deadline (`start + seconds`, not a
   chain of `seconds/steps` sleeps), then a short busy-poll for the final
   ~100-200ms if sub-second precision is ever actually needed; drive the
   progress bar's animation off wall-clock-elapsed-so-far, decoupled
   entirely from how the actual wait is implemented.
2. **For auto-logging arbitrary actions**, don't build a global
   decorator or monkeypatch everything — wrap *devices* the moment
   `ScopeAssembly.add_device()` mounts them (`hive/assembly.py`, already
   the single choke point every device passes through) in a thin
   `wrapt`-based proxy that logs each method call to
   `Experiment.current`, if one is open. This gets you Bluesky's actual
   payoff (nothing can act on hardware without it being logged, because
   the logging is structurally unavoidable at the one place hardware
   gets touched) without adopting Bluesky itself, and without needing
   the scientist to remember anything — closest match to "tag everything
   automatically" of everything researched.

---

## G. Summary of open items

1. §A — `ExpActions` as the module/class name — fine, or prefer something
   else?
2. §B — the `self.events = ""` collision needs a fix regardless of
   anything else here (it's blocking work already shipped this
   session) — rename `ExpReport`'s field to something like
   `self._report_events_str`? Your call on the name.
3. §B — composition vs. continued multiple-inheritance for future mixins
   — decide now, or defer until a fifth mixin is actually proposed?
4. §D — confirmed `post_register` is the method you meant? If you had a
   specific past commit/regression in mind, point me at it for a real
   review rather than my current best-guess read of the class as it
   stands.
5. §F — comfortable wrapping mounted devices in a `wrapt` proxy for
   automatic call-logging, or does that feel like too much magic
   happening behind `scope.<device>.<method>()` calls?
