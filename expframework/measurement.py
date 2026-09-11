from numpy import nan as Nan
import datetime
import time
from copy import deepcopy

from core.permaconfig.sharing import Share
from .experiment import ExpEvent
from .experiment import Experiment as Experiment_
from core.bookkeeping.session import Session
from core.uid import uid
import logging as log
from .plotter import *
import plotext as plt

from pandas import DataFrame, concat

from pprint import pformat
from rich.pretty import Pretty
from rich.panel import Panel
from rich import print
from rich import pretty
from rich.table import Table

class Measurement(ExpEvent):
	"""

	Every time you look at the system, you perturb it.
	--------------------------------------------------

	A measurment is a type of dictionary that is compatible with the
	dataframe (pandas) data-structure and gives all the necessary in-
	-formation necessary for every entry. T								s allows the user to com-
	-bine arbitrary number of experiments for analysis, **without any
	data filtering**.

	Measurement <modality>
		.
		|- type           (type="Experiment.Measurement")
		|- scopeid        (M1, M2, ...)
		|- mid            (Microscope uid)
		|- scriptid       (Defined for an experiment that is repeated multiple times)
		|- eid            (experiment id)
		|- sid            (session id; for SingleSession experiments, it is the same as eid)
		|- df             (datetime)
		|- sessiontime    (time elapsed in seconds since experiment)
		|- exptime        (total time of the experiment - sum of all sessions)
		|- machinetime    (nanosecond tick - since epoch time)
		|- measureid      (epochtime/ measurement mode id - assigned by a MeasurementStream object)
		|- measureidx     (measurement index - deafults to -1 : arbitrary sequence order)
		|- success        (flag that must be set after measurement to indicate its completion)
		|- <statevar 1>   (duration_s, setup, exptype are common fields)
		|- <statevar 2>
		:       :::
		|- <statevar n>
		|- <measurand 1>
		|- <measurand 2>
		:       :::
		|- <measurand n>
		|- <list-of-measurands>
		|- <list-of-statevars>
		+
	"""



	def __init__(self, **kwargs):

		super().__init__()
		self.update({
					"type"         : "measurement",
			  		"measureid"    : Experiment_.current.eid,
			   		"measureidx"   : 0,
			   		"success"      : None,
		   			})

		# Initial keys
		if len(kwargs) != 0:
			for key in kwargs:
				self[key] = kwargs[key]



	def panel(self):
		print(Panel(Pretty(self.copy()), title=f"Measurement: {self['measureidx']}"))
	    
	def get(self):
		return self
	


class MeasurementStream:
	"""
	Returns time adjusted copies of a measurement.
	"""
	def __init__(self, measurement={}, name=None):
		self.name = name
		self.datapoint = Measurement(**measurement)
		self.uid = uid()
		self.datapoint["measureid"] = self.uid
		self.datapoint["measureidx"] = -1

		self.readings = []
		## AI Generated -- version counter backing the lazy `.df` property
		## below, replacing the old eagerly-maintained DataFrame.
		self._version = 0
		self._df_cache = None
		self._df_cache_version = -1

		self.detections = []
		self.measurements = []
		self.monitors = []
		## AI Generated -- {field: {label, unit, unit_latex, description,
		## kind}}, populated by add_measurement/add_detection/add_monitor
		## below (docs/notes/scripts_measurements_plotting.md §C.2).
		self.descriptors = {}
		## AI Generated -- [(label, Clock)] -- see subscribe_clock() below.
		self.clock_subscriptions = []

		self.auto_update_tables = False
		self.auto_update_explogs = False
		self.tables = {}

	@property
	def df(self):
		"""AI Generated -- lazy, cached pandas view over self.readings.
		Rebuilt only when self._version has changed since the last build
		(a new reading appended), never incrementally -- avoids the
		classic pandas anti-pattern of growing a DataFrame one row at a
		time via `.loc[len(df)] = row`, which is O(N^2) over a stream's
		life. See docs/notes/scripts_measurements_plotting.md §C.1/§G.2."""
		if self._df_cache_version != self._version:
			self._df_cache = DataFrame(self.readings)
			self._df_cache_version = self._version
		return self._df_cache

	## AI Generated -- _add_field() below is the shared body for
	## add_measurement/add_detection/add_monitor (§C.2's pros/cons --
	## option (c): keep the three readable, self-documenting public
	## names, kill the tripled body). No longer eagerly rebuilds a
	## DataFrame here -- `.df` is the lazy property above now, so
	## registering a field doesn't need to touch it at all.
	def _add_field(self, key, kind, label=None, unit=None, unit_latex=None, description=None):
		{"measurement": self.measurements, "detection": self.detections,
		 "monitor": self.monitors}[kind].append(key)
		self.datapoint[key] = Nan
		self.descriptors[key] = {"label": label or key, "unit": unit,
								  "unit_latex": unit_latex, "description": description, "kind": kind}

	def add_detection(self, key, label=None, description=None):
		self._add_field(key, "detection", label=label, description=description)

	def add_measurement(self, key, label=None, unit=None, unit_latex=None, description=None):
		self._add_field(key, "measurement", label=label, unit=unit, unit_latex=unit_latex, description=description)

	def add_monitor(self, key, label=None, unit=None, unit_latex=None, description=None):
		self._add_field(key, "monitor", label=label, unit=unit, unit_latex=unit_latex, description=description)

	def subscribe_clock(self, clock, label=None):
		"""AI Generated -- subscribe to one existing Clock -- deliberately
		singular, no whole-ClockGroup form, so every addition to a stream
		stays a visible, chosen decision rather than a bulk import (see
		docs/notes/scripts_measurements_plotting.md §G.6). Every future
		reading records this clock's elapsed time as a monitor field,
		f"{label}_elapsed" -- unit "s" always, a Clock's own unit, never
		asked of the caller."""
		from core.idioms.clock import Clock
		if not isinstance(clock, Clock):
			raise TypeError(f"subscribe_clock() needs an existing Clock, got {type(clock)}")
		label = label or f"clock_{len(self.clock_subscriptions)}"
		self.clock_subscriptions.append((label, clock))
		self.add_monitor(f"{label}_elapsed", unit="s", description=f"Elapsed time on the '{label}' clock")


	def tabulate(self, *args, title=None):
		"""
		Create a tabulated view of the measurement stream with the provided keys.
		"""
		filtered_args = [arg for arg in args if arg in self.datapoint.keys()]
		if list(args) != list(filtered_args):
			log.error("Missing keys passed to MeasurementStream.tabulate. Ignoring those keys.")

		table = Table(*filtered_args, title=f"Table {len(self.tables)}{f' : {title}'*bool(title)}")
		self.tables[tuple(args)] = table
		for i, key in enumerate(args):
			table.columns[i].style = f"color({i+1})"
		return table


	## AI Generated -- the old first plot() definition here (`def
	## plot(self, *args, title=None): Plotter.show()`) was dead code,
	## silently shadowed by the real one further down (`plot(self, x, y,
	## label="")`) since Python just keeps the last definition of a name
	## in a class body -- and it would have raised AttributeError anyway
	## (Plotter has no .show()). Removed rather than fixed; see
	## docs/notes/scripts_measurements_plotting.md §B.1.

	def __call__(self, **kwargs):
		self.readings.append(deepcopy(self.advance()))
		for k, v in dict(kwargs).items():
			self.readings[-1][k] = v

		## Tables ----------------------------------------
		if self.auto_update_tables:
			for tab in self.tables:
				row = []
				for key in tab:
					row.append(str(self.readings[-1][key]))
				self.tables[tab].add_row(*row)

		## Exp logs ---------------------------------------
		if self.auto_update_explogs and Experiment_.current != None:
			Experiment_.current.logs["results"].append(dict(self.readings[-1]))
			Experiment_.current.__save__()

		self._version += 1  # AI Generated -- invalidates the .df cache; replaces the old eager .loc[] append
		return self.readings[-1]

	def measure(self, **kwargs):
		return self.__call__(**kwargs)

	def advance(self, **kwargs):
		self.datapoint["sessiontime"] = Session.current.timer_elapsed()
		self.datapoint["exptime"]     = Experiment_.current.expclock.time_elapsed()
		self.datapoint["machinetime"] = time.time_ns()
		self.datapoint["dt"] = datetime.datetime.now()
		self.datapoint["measureidx"] = self.datapoint["measureidx"] + 1
		for label, clock in self.clock_subscriptions:  # AI Generated
			self.datapoint[f"{label}_elapsed"] = clock.read()
		return self.datapoint
	
	def __repr__(self):
		return pretty.pretty_repr({"detections" : self.detections,
								   "measuremnts": self.measurements,
								   "monitors"   : self.monitors,
								   "readings"   :self.readings})

	def panel(self):
		print((Panel(Pretty({"detections" : self.detections,
								   "measuremnts": self.measurements,
								   "monitors"   : self.monitors,
								   "readings"   :self.readings}),
			title=f"Measurement Stream {f':: {self.name}'*(self.name!=None)}")))

	def screen(self, table):
		from rich.live import Live
		with Live(table, refresh_per_second=4, screen=True) as live:
			for _ in range(40):
				time.sleep(0.4)
				live.update(table)

	def plot(self, x, y, label=""):
		plt.cld()
		plt.plot(self.df[x], self.df[y], label=label)
		plt.xlabel(x)
		plt.ylabel(y)
		plt.title(f"Measurement Stream Plot{f':: {self.name}'*(self.name!=None)} :: {x}-{y}")
		plt.show()
