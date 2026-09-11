"""
AI Generated -- replaces expframework/special.py (Claude, Anthropic, 2026-09).

`Test`/`TestExperiment` dropped entirely, on request -- confirmed it was
already non-functional (`Test.testfn()`/`conclude()` called `Rule(...)`,
never imported anywhere in that file) and confirmed via a full-codebase
grep that `expframework.special` was never imported anywhere at all, so
this had zero blast radius either way.

`CalibrationExperiment` built for real (previously just `...`) -- see
docs/notes/scripts_measurements_plotting.md §E.2/§E.3 for the full design
record. A normal Experiment, saved under Experiment.calibration_dir
instead of Experiment.exp_dir via the real `_data_dir()` override hook on
Experiment (expframework/experiment.py). A calibration's *reference*
(eid + path) is attached to the calibrated device's own persistent state
only on confirmed completion (complete_calibration()) -- never eagerly at
construction, so an aborted/failed calibration can't discard the
reference to the last *good* one. Registers itself in
core.bookkeeping.registry.
"""

from core.permaconfig.config import TrappyConfig
from core.bookkeeping.registry import Registry

from .experiment import Experiment


def _device_name(target_device):
	"""Best-effort device name for the Registry tag -- target_device's
	exact expected shape is still an open design question (invited
	discussion, not decided), so this stays permissive rather than
	assuming one type: a bare string, a hive.physical.PhysicalObject
	(whose data lives in .attribs, not a plain dict), or a plain dict."""
	if target_device is None:
		return None
	if isinstance(target_device, str):
		return target_device
	attribs = getattr(target_device, "attribs", None)
	if attribs is not None and hasattr(attribs, "get"):
		return attribs.get("name")
	if hasattr(target_device, "get"):
		return target_device.get("name")
	return None


class CalibrationExperiment(Experiment):
	"""A normal Experiment, saved under Experiment.calibration_dir instead
	of wherever a normal Experiment resolves to. `target_device` (a
	hive.physical.PhysicalObject, a plain dict, or a bare name string --
	see _device_name() above) is the thing being calibrated; its
	`last_calibration` reference only gets set by complete_calibration(),
	never eagerly here, and Registry (core.bookkeeping.registry) always
	keeps the full history regardless of what this one reference points
	at."""

	def __init__(self, name, target_device=None, **kwargs):
		self._target_device = target_device
		super().__init__(name, **kwargs)
		Registry(self.name, "calibration", tag=_device_name(target_device))

	def _data_dir(self):
		return TrappyConfig.current.leaf("Experiment", "calibration_dir") or super()._data_dir()

	def complete_calibration(self):
		"""Call only once the calibration has actually succeeded -- fixes
		a bug in the original design sketch, which set this eagerly in
		__init__ before the run had done anything: an aborted or failed
		calibration would already have overwritten the device's
		reference to the last *good* one."""
		if self._target_device is not None:
			self._target_device["last_calibration"] = {"eid": self.eid, "path": self.exp_dir}
