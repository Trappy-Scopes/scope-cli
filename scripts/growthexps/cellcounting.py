# +----------------------------------------------------------------------------+
# |                                                                            |
# |       .-"""""""-.             ___                                          |
# |     .'           '.       _,~"                                             |
# |    /          .##.  \   ,~"                                                |
# |   |           '##'  |~"                                                    |
# |    \                /~,                                                    |
# |     '.            .'   "~,_                                                |
# |       '-........-'        "~,__                                            |
# |                                                                            |
# | Author    : Yatharth Bhasin (yatharth1997+ts@gmail.com)                    |
# | Date      : June 2026                                                      |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# | AI: Written by Clause (reviewed)                                           |
# +----------------------------------------------------------------------------+

import datetime
import time
import os

from rich import print
from rich.panel import Panel
from rich.markdown import Markdown
from rich.pretty import Pretty

from expframework.experiment import Experiment

print(Panel(Markdown(
"""Use `create_exp()` to open a new experiment, or `findexp()` to reopen an old one.
Use `new_count(name, *counts, mutant=...)` to log a cell count for a colony.
Use `log_media_addition(name, volume_before_ml, media_added_ml)` whenever you add fresh media.
Use `fit_curve(names)` or `analyse_growth()` to fit growth-curves and populate the `analysis/` folder.
Use `growth_rate_segments(name)` / `plot_growth_rate_segments(name)` for a colony diluted repeatedly (a continuously-fed culture) - fit_curve calls this automatically for colonies with 2+ media additions.
Use `export_csv()` to dump all recorded counts to a csv.
Shorthand `strain[strainid]` can be used to access measurement streams."""),
title="Cell counting utilities"))


## ---------------------------------------------------------------------------
## Experiment setup
## ---------------------------------------------------------------------------

def create_exp(*attribs, **construct_kwargs):
	"""
	Open a new experiment via `Experiment.Construct` and populate it with the
	`cell_counts` and `media_additions` measurement streams this file needs.
	Call this before anything else - `new_count`, `log_media_addition`,
	`fit_curve`, etc all assume `Experiment.current` is already open.

	Parameters
	----------
	*attribs : str
		Extra name components appended to the constructed experiment name
		(e.g. `create_exp("cellcounting")`). Defaults to just `"cellcounting"`
		if none are given.
	**construct_kwargs
		Passed straight through to `Experiment.Construct` - e.g.
		`scopeid=False`, `username=False`, `date=False`, `time=False`,
		`eid=False` to leave out that part of the name.

	`Experiment.Construct` builds the name from scopeid, username, date and
	time (each on by default) plus the given attribs, and appends a unique
	eid, so you don't need to hand-build the experiment name yourself.
	"""
	global exp
	if not attribs:
		attribs = ("cellcounting",)

	exp = Experiment.Construct(list(attribs), **construct_kwargs)
	populate_exp()
	return exp


def findexp(name):
	"""Reopen an existing experiment by name (thin wrapper - see Experiment.list_all_names())."""
	global exp
	exp = Experiment(name)
	populate_exp()
	return exp


def populate_exp():
	"""
	Make sure the currently-open experiment has both measurement streams
	this file needs, and refresh the `strain` shorthand. Safe to call
	repeatedly.
	"""
	global strain
	ensure_cell_counts_stream()
	ensure_media_additions_stream()
	strain = Experiment.current.mstreams


## Define shorthand - only valid once an experiment is open (see create_exp/populate_exp).
strain = Experiment.current.mstreams if Experiment.current is not None else {}


## ---------------------------------------------------------------------------
## Stream setup
## ---------------------------------------------------------------------------

CELL_COUNTS_STREAM = "cell_counts"
MEDIA_ADDITIONS_STREAM = "media_additions"


def ensure_cell_counts_stream():
	"""
	Make sure the experiment has a `cell_counts` measurement stream with all the
	monitors `new_count` needs. Safe to call repeatedly - it is a no-op if the
	stream already exists.
	"""
	exp = Experiment.current
	if CELL_COUNTS_STREAM not in exp.mstreams:
		exp.new_measurementstream(
			CELL_COUNTS_STREAM,
			measurements=["counts"],
			monitors=["df", "density", "label", "sep", "mutant"],
		)
	return exp.mstreams[CELL_COUNTS_STREAM]


def ensure_media_additions_stream():
	"""
	Make sure the experiment has a `media_additions` measurement stream. Kept
	separate from `cell_counts` - a media addition doesn't have to coincide
	with a count, and the two are merged by colony + timestamp during
	analysis instead of being forced into one event.
	"""
	exp = Experiment.current
	if MEDIA_ADDITIONS_STREAM not in exp.mstreams:
		exp.new_measurementstream(
			MEDIA_ADDITIONS_STREAM,
			measurements=["media_added_ml"],
			monitors=["label", "volume_before_ml", "dilution_fraction"],
		)
	return exp.mstreams[MEDIA_ADDITIONS_STREAM]


## ---------------------------------------------------------------------------
## Recording counts and media additions
## ---------------------------------------------------------------------------

def _resolve_timestamp(date_override=None, time_override=None):
	"""
	Build a timestamp, allowing the caller to override the date (e.g. when
	back-filling after an experiment has finished) while optionally also
	pinning down the time-of-day. If only a date is given, "now"'s
	time-of-day is kept, since that is usually a reasonable guess and is
	explicitly what this override is for (sure of the date, not the time).

	`date_override` / `time_override` accept either `datetime.date` /
	`datetime.time` objects, or strings parseable by `datetime.date.fromisoformat`
	/ `datetime.time.fromisoformat` (e.g. "2026-08-24", "14:30").
	"""
	now = datetime.datetime.now()
	if date_override is None and time_override is None:
		return now
	if isinstance(date_override, str):
		date_override = datetime.date.fromisoformat(date_override)
	if isinstance(time_override, str):
		time_override = datetime.time.fromisoformat(time_override)
	date_part = date_override if date_override is not None else now.date()
	time_part = time_override if time_override is not None else now.time()
	return datetime.datetime.combine(date_part, time_part)


def new_count(name, *counts, df=2, sep=None, mutant=None,
			  date_override=None, time_override=None):
	"""
	Record a new cell count for a colony.

	Parameters
	----------
	name : str
		Colony name. This is the identifier used everywhere downstream
		(analysis groups counts made with the same `name` into one growth
		curve, and matches it against `log_media_addition` events for the
		same colony), so keep it unique per colony/condition and consistent
		across timepoints.
	*counts : float
		Raw counts (e.g. per-square hemocytometer counts).
	df : float
		Dilution factor used when counting (as in the old workflow) - this
		is about the counting method (e.g. sample dilution before loading
		the hemocytometer), not about media being added to the culture. See
		`log_media_addition` for that.
	sep : optional
		Passed straight through to the measurement stream, unused by the
		analysis in this file.
	mutant : str, optional
		Mutant / strain name for this colony. Used to group and compare
		growth across mutants in the analysis step.
	date_override : str or datetime.date, optional
		Use this instead of today's date, e.g. when logging a count after the
		experiment has already finished and you're not sure of the exact time
		it was taken, but are sure of the date.
	time_override : str or datetime.time, optional
		Use this instead of the current time. Usually left unset (you rarely
		know the time when back-filling) - if omitted, "now"'s time-of-day is
		used together with `date_override`'s date.

	Returns
	-------
	The measurement-stream record that was created.
	"""
	import numpy as np
	counts_stream = ensure_cell_counts_stream()
	timestamp = _resolve_timestamp(date_override, time_override)
	c = counts_stream(
		counts=counts,
		label=name,
		df=df,
		sep=sep,
		mutant=mutant,
		dt=timestamp,  # overrides the auto-set "dt" field when back-filling
		density=float(np.mean(counts) * 10000 * df),
	)
	c.panel()
	subtitle = f"mutant={mutant}" if mutant else "mutant=(none)"
	print(Panel(
		f"Culture density is: {c['density']:.2e}\n"
		f"Recorded at: {timestamp.isoformat(sep=' ', timespec='minutes')}",
		title=f"{name} - {subtitle}",
	))
	return c


def log_media_addition(name, volume_before_ml, media_added_ml,
						date_override=None, time_override=None):
	"""
	Record a media-addition event for a colony: how much culture was there
	before, and how much fresh media you added. This is kept as its own
	measurement stream (`media_additions`), independent of `new_count` - it
	does not need to line up with a specific count. `fit_curve` /
	`analyse_growth` merge these events with the colony's counts (by `name`
	and timestamp) to compensate the growth curve for the resulting
	dilution, so growth rate is fit on the underlying population rather
	than the diluted concentration.

	Parameters
	----------
	name : str
		Colony name - must match the `name` used in `new_count` for this
		colony so the analysis can merge the two streams.
	volume_before_ml : float
		Total culture volume immediately before adding media.
	media_added_ml : float
		Volume of fresh media added.
	date_override, time_override : optional
		Same semantics as in `new_count` - use when back-filling.

	Returns
	-------
	The measurement-stream record that was created.
	"""
	media_stream = ensure_media_additions_stream()
	timestamp = _resolve_timestamp(date_override, time_override)
	resulting_volume = volume_before_ml + media_added_ml
	dilution_fraction = media_added_ml / resulting_volume
	m = media_stream(
		media_added_ml=media_added_ml,
		label=name,
		volume_before_ml=volume_before_ml,
		dilution_fraction=dilution_fraction,
		dt=timestamp,
	)
	m.panel()
	print(Panel(
		f"Volume before: {volume_before_ml:.2f} mL, media added: {media_added_ml:.2f} mL "
		f"-> dilution fraction: {dilution_fraction:.3f} (fold = {1.0 / (1.0 - dilution_fraction):.3f}x)\n"
		f"Recorded at: {timestamp.isoformat(sep=' ', timespec='minutes')}",
		title=f"{name} - media added",
	))
	return m


## ---------------------------------------------------------------------------
## Growth-curve analysis
## ---------------------------------------------------------------------------

def _analysis_dir():
	"""
	The `analysis` folder is created for every experiment by Experiment.new(),
	so this just resolves the path (and makes sure it exists in case it was
	ever removed).
	"""
	exp = Experiment.current
	path = os.path.join(exp.exp_dir, "analysis")
	os.makedirs(path, exist_ok=True)
	return path


def _counts_dataframe():
	"""Pull every `cell_counts` record into a tidy pandas DataFrame."""
	exp = Experiment.current
	if CELL_COUNTS_STREAM not in exp.mstreams:
		raise Exception("No `cell_counts` measurement stream found on this experiment yet - use new_count() first.")
	raw = exp.mstreams[CELL_COUNTS_STREAM].df
	counts_df = raw[["label", "mutant", "df", "density", "dt"]].copy()
	counts_df = counts_df.rename(columns={"dt": "timestamp"})
	counts_df = counts_df.dropna(subset=["timestamp"]).sort_values(["label", "timestamp"]).reset_index(drop=True)
	return counts_df


def _media_additions_dataframe():
	"""
	Pull every `media_additions` record into a tidy pandas DataFrame. Returns
	an empty (but correctly columned) DataFrame if no media has been logged.
	"""
	import pandas as pd
	exp = Experiment.current
	if MEDIA_ADDITIONS_STREAM not in exp.mstreams:
		return pd.DataFrame(columns=["label", "volume_before_ml", "media_added_ml", "dilution_fraction", "timestamp"])
	raw = exp.mstreams[MEDIA_ADDITIONS_STREAM].df
	df = raw[["label", "volume_before_ml", "media_added_ml", "dilution_fraction", "dt"]].copy()
	df = df.rename(columns={"dt": "timestamp"})
	df = df.dropna(subset=["timestamp"]).sort_values(["label", "timestamp"]).reset_index(drop=True)
	return df


def _compensate_dilution(counts_sub, media_sub):
	"""
	Reconstruct a continuous "no-dilution" density trace for one colony, by
	merging its counts against its own media-addition events (matched by
	colony name, ordered by time).

	Each media addition contributes a fold-factor `r = 1 / (1 - dilution_fraction)`
	to the culture volume. Diluting by `r` divides the observed concentration
	by `r`, so multiplying a count - and every later count of that colony,
	until the next addition - by the *cumulative* product of all fold-factors
	applied up to that point undoes the dilution and reconnects the growth
	trace to where it left off. This compensated trace, not the raw density,
	is what growth-rate fitting should run on.
	"""
	compensated = []
	for _, row in counts_sub.iterrows():
		applicable = media_sub[media_sub["timestamp"] < row["timestamp"]]
		cumulative = 1.0
		for fraction in applicable["dilution_fraction"]:
			cumulative *= 1.0 / (1.0 - fraction)
		compensated.append(row["density"] * cumulative)
	import pandas as pd
	return pd.Series(compensated, index=counts_sub.index)


def _records_dataframe():
	"""
	Merge `cell_counts` with `media_additions` (by colony `label`) into one
	tidy DataFrame with both the raw `density` and the dilution-compensated
	`compensated_density`, plus a `perturbed` flag per colony (whether any
	media was ever added to it).
	"""
	counts = _counts_dataframe()
	media = _media_additions_dataframe()
	compensated_parts = []
	perturbed_labels = set(media["label"].dropna().unique())
	for label, counts_sub in counts.groupby("label", sort=False):
		media_sub = media[media["label"] == label]
		compensated_parts.append(_compensate_dilution(counts_sub, media_sub))
	import pandas as pd
	counts["compensated_density"] = pd.concat(compensated_parts).sort_index()
	counts["perturbed"] = counts["label"].isin(perturbed_labels)
	return counts


def _fit_growth_rate(sub_df, density_col="compensated_density",
					 t_start_hr=None, t_end_hr=None, min_points=3):
	"""
	Fit exponential growth (log-linear regression) to one colony's density
	timeseries. Returns a dict with growth rate (per hour), doubling time
	(hours), and fit quality, or None if there isn't enough data.

	Parameters
	----------
	t_start_hr, t_end_hr : float, optional
		Restrict the fit to the log-phase window [t_start_hr, t_end_hr]
		(hours relative to the first timepoint). When omitted, all points
		are used - appropriate only if the whole series is in exponential
		growth.
	min_points : int, default 3
		Minimum number of points required after windowing. With only 2
		points a line fits exactly (R^2=1 by construction), giving a
		meaningless quality metric. Returns None and prints a warning when
		fewer than `min_points` points are available.
	"""
	import numpy as np
	if len(sub_df) < 2:
		return None
	t0 = sub_df["timestamp"].iloc[0]
	hours = sub_df["timestamp"].apply(lambda t: (t - t0).total_seconds() / 3600.0).to_numpy()

	mask = np.ones(len(hours), dtype=bool)
	if t_start_hr is not None:
		mask &= hours >= t_start_hr
	if t_end_hr is not None:
		mask &= hours <= t_end_hr
	hours = hours[mask]
	sub_df = sub_df.iloc[mask]

	if len(hours) < min_points:
		label = sub_df["label"].iloc[0] if "label" in sub_df.columns and len(sub_df) else "?"
		print(f"[yellow]fit skipped for '{label}': {len(hours)} point(s) in window, need >= {min_points}[/yellow]")
		return None

	log_density = np.log(sub_df[density_col].to_numpy())
	if np.any(~np.isfinite(log_density)):
		return None

	slope, intercept = np.polyfit(hours, log_density, 1)
	pred = slope * hours + intercept
	ss_res = np.sum((log_density - pred) ** 2)
	ss_tot = np.sum((log_density - log_density.mean()) ** 2)
	r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

	growth_rate = slope  # per hour
	doubling_time = np.log(2) / growth_rate if growth_rate > 0 else float("inf")

	return {
		"growth_rate_per_hr": growth_rate,
		# Same exponential rate constant, expressed per 24h instead of per hour
		# (N(t+24)/N(t) = exp(24*mu)) - not an independent quantity, just a
		# more intuitive "per day" unit for the same fit.
		"growth_rate_per_24hr": growth_rate * 24,
		"doubling_time_hr": doubling_time,
		"r_squared": r_squared,
		"n_points": len(sub_df),
		"slope": slope,
		"intercept": intercept,
	}


def fit_curve(names=None, show=False, t_start_hr=None, t_end_hr=None, min_points=3):
	"""
	Fit and plot growth-curve data for a colony, or a list of colonies.
	Saves one figure per colony (`analysis/<name>_growth.png`) plus an
	overlay plot (`analysis/growth_curves.png`), and returns the fit summary
	as a pandas DataFrame. Each plot shows both the raw measured density
	(faded points, with visible dips at each media addition) and the
	dilution-compensated density (solid line), with the exponential fit -
	and each media-addition timepoint - drawn against the compensated trace.

	If `names` is None, every colony seen in the `cell_counts` stream is
	included.

	Parameters
	----------
	t_start_hr, t_end_hr : float, optional
		Restrict the exponential fit to a log-phase window (hours relative
		to each colony's first timepoint). The full density trace is always
		plotted; only the regression is windowed. Leave unset to fit all
		points (fine when the whole series is in exponential growth).
	min_points : int, default 3
		Minimum points required in the fit window. Colonies below this
		threshold are skipped (no fit line, None in the summary).
	"""
	import matplotlib.pyplot as plt
	import matplotlib.lines as mlines
	import numpy as np
	plt.rcParams["text.usetex"] = False  # use matplotlib's built-in mathtext, not a system LaTeX

	df = _records_dataframe()
	media = _media_additions_dataframe()
	if names is None:
		names = sorted(df["label"].dropna().unique().tolist())
	elif isinstance(names, str):
		names = [names]
	out_dir = _analysis_dir()
	summary_rows = []
	fig_all, ax_all = plt.subplots(figsize=(8, 6))
	media_marker_added_to_legend = False
	for name in names:
		sub = df[df["label"] == name].reset_index(drop=True)
		if sub.empty:
			print(Panel(f"No records found for colony '{name}'", style="white on red"))
			continue
		t0 = sub["timestamp"].iloc[0]
		hours = sub["timestamp"].apply(lambda t: (t - t0).total_seconds() / 3600.0)
		mutant = sub["mutant"].dropna().iloc[0] if sub["mutant"].notna().any() else None
		perturbed_any = bool(sub["perturbed"].iloc[0])
		fit = _fit_growth_rate(sub, density_col="compensated_density",
							   t_start_hr=t_start_hr, t_end_hr=t_end_hr,
							   min_points=min_points)
		fig, ax = plt.subplots(figsize=(7, 5))
		ax.scatter(hours, sub["density"], label="measured (diluted)", color="grey", alpha=0.5)
		ax.plot(hours, sub["compensated_density"], marker="o", label="compensated", color="steelblue")
		ax.set_yscale("log")
		media_sub = media[media["label"] == name]
		media_hours = media_sub["timestamp"].apply(lambda t: (t - t0).total_seconds() / 3600.0)
		for i, mh in enumerate(media_hours):
			ax.axvline(mh, color="orange", linestyle="--", alpha=0.6, label="media added" if i == 0 else None)
		title = f"{name}"
		if mutant:
			title += f" ({mutant})"
		fit_hours = None
		if fit:
			fit_hours = hours[
				(hours >= (t_start_hr if t_start_hr is not None else -np.inf)) &
				(hours <= (t_end_hr   if t_end_hr   is not None else  np.inf))
			]
			ax.plot(fit_hours, np.exp(fit["slope"] * fit_hours + fit["intercept"]),
					color="red",
					label=(rf"fit: $\mu$={fit['growth_rate_per_hr']:.3f} hr$^{{-1}}$"
						   rf" ({fit['growth_rate_per_24hr']:.2f} day$^{{-1}}$), "
						   rf"$t_d$={fit['doubling_time_hr']:.2f} hr, $R^2$={fit['r_squared']:.2f}"))
		ax.set_xlabel("Time (hours)")
		ax.set_ylabel("Density (cells/mL)")
		ax.set_title(title + (" - media added" if perturbed_any else ""))
		ax.legend()
		fig.tight_layout()
		fig.savefig(os.path.join(out_dir, f"{name}_growth.png"))
		if not show:
			plt.close(fig)

		## Combined plot: this colony's compensated trace, its own fit (dashed,
		## same color), and small triangles marking its own media additions.
		line_all, = ax_all.plot(hours, sub["compensated_density"], marker="o",
								 label=f"{name}" + (f" ({mutant})" if mutant else ""))
		color = line_all.get_color()
		if fit and fit_hours is not None:
			ax_all.plot(fit_hours, np.exp(fit["slope"] * fit_hours + fit["intercept"]),
						linestyle="--", color=color, alpha=0.7, linewidth=1)
		if len(media_hours):
			y_marker = sub["compensated_density"].min() * 0.6
			ax_all.scatter(media_hours, [y_marker] * len(media_hours),
						   marker="v", color=color, s=30, zorder=5)
			media_marker_added_to_legend = True
		ax_all.set_yscale("log")

		summary_rows.append({
			"label": name,
			"mutant": mutant,
			"perturbed": perturbed_any,
			"n_points": len(sub),
			"growth_rate_per_hr": fit["growth_rate_per_hr"] if fit else None,
			"growth_rate_per_24hr": fit["growth_rate_per_24hr"] if fit else None,
			"doubling_time_hr": fit["doubling_time_hr"] if fit else None,
			"r_squared": fit["r_squared"] if fit else None,
		})
	ax_all.set_xlabel("Time (hours)")
	ax_all.set_ylabel("Density (cells/mL), dilution-compensated")
	ax_all.set_title("Growth curves - all colonies (dashed = fit, triangle = media added)")
	handles, labels = ax_all.get_legend_handles_labels()
	if media_marker_added_to_legend:
		handles.append(mlines.Line2D([], [], color="grey", marker="v", linestyle="None", markersize=6))
		labels.append("media added")
	ax_all.legend(handles, labels, fontsize=8)
	fig_all.tight_layout()
	fig_all.savefig(os.path.join(out_dir, "growth_curves.png"))
	if not show:
		plt.close(fig_all)
	else:
		plt.show()

	## Colonies that were diluted more than once (e.g. a semi-continuous /
	## serially-passaged culture) get an additional segment-wise growth-rate
	## plot, since a single global fit can smear together intervals that may
	## have genuinely different rates. See plot_growth_rate_segments().
	for name in names:
		if len(media[media["label"] == name]) >= 2:
			try:
				plot_growth_rate_segments(name, show=False)
			except ValueError:
				pass

	import pandas as pd
	summary = pd.DataFrame(summary_rows)
	summary.to_csv(os.path.join(out_dir, "growth_summary.csv"), index=False)
	print(Panel(Pretty(summary.to_dict(orient="records")), title="Growth-curve fit summary"))
	print(Panel(f"Saved plots and growth_summary.csv to: {out_dir}"))
	return summary


## ---------------------------------------------------------------------------
## Segment-wise growth rate (for continuously / repeatedly diluted cultures)
## ---------------------------------------------------------------------------

def _segment_growth_rates(sub):
	"""
	Compute the local growth rate between each consecutive pair of counts for
	one colony (`sub`, already sorted by timestamp, with a `compensated_density`
	column) instead of a single regression over the whole series.

	Why this is needed: for a colony diluted only once or twice, a single
	global fit on the compensated trace is fine. But for a colony diluted at
	(almost) every timepoint - a semi-continuous / serially-passaged culture,
	such as "Gptx" being diluted daily - a single global fit can smear
	together intervals that may have genuinely different growth rates (e.g.
	a lag after each dilution, or a rate that drifts over the course of the
	experiment). Computing the rate interval-by-interval instead shows that.

	Because `compensated_density[i]` already carries the cumulative product
	of every dilution fold-factor up to count `i`, the ratio
	compensated[i+1] / compensated[i] is exactly the dilution-corrected
	growth ratio for that one interval - the earlier cumulative factors
	cancel out - so no re-deriving fold-factors is needed here.

	Returns a list of dict rows: t_start, t_end, duration_hr,
	growth_rate_per_hr, growth_rate_per_24hr.
	"""
	import numpy as np

	rows = []
	for i in range(len(sub) - 1):
		t0, t1 = sub["timestamp"].iloc[i], sub["timestamp"].iloc[i + 1]
		d0, d1 = sub["compensated_density"].iloc[i], sub["compensated_density"].iloc[i + 1]
		duration_hr = (t1 - t0).total_seconds() / 3600.0
		if duration_hr <= 0 or d0 <= 0 or d1 <= 0:
			continue
		rate = float(np.log(d1 / d0) / duration_hr)
		rows.append({
			"t_start": t0,
			"t_end": t1,
			"duration_hr": duration_hr,
			"growth_rate_per_hr": rate,
			"growth_rate_per_24hr": rate * 24,
		})
	return rows


def growth_rate_segments(name):
	"""
	Growth rate computed interval-by-interval for one colony, rather than a
	single fit over the whole series - see `_segment_growth_rates` for why
	this matters for a continuously/repeatedly-diluted culture (e.g. "Gptx"
	in this experiment, diluted at every timepoint, vs. colonies diluted
	only once).

	Returns a DataFrame with one row per interval between consecutive counts:
	label, t_start, t_end, duration_hr, growth_rate_per_hr, growth_rate_per_24hr.
	"""
	import pandas as pd

	df = _records_dataframe()
	sub = df[df["label"] == name].sort_values("timestamp").reset_index(drop=True)
	if len(sub) < 2:
		raise ValueError(f"Need at least 2 counts for '{name}' to compute segment growth rates - found {len(sub)}.")

	rows = _segment_growth_rates(sub)
	result = pd.DataFrame(rows)
	result.insert(0, "label", name)
	return result


def plot_growth_rate_segments(name, show=False):
	"""
	Plot the segment-wise growth rate (see `growth_rate_segments`) for one
	colony over time, and save it to `analysis/<name>_segment_growth_rate.png`
	plus `analysis/<name>_segment_growth_rate.csv`. Useful for a
	continuously/repeatedly-diluted culture, to see whether its growth rate
	is roughly constant across dilutions or drifting (e.g. slowing lag phase
	after each feed).

	`fit_curve` calls this automatically for any colony with 2+ recorded
	media additions; call it directly for a specific colony (including ones
	with just 1 dilution, though there's only one interval to show then).

	Returns the segment DataFrame.
	"""
	import matplotlib.pyplot as plt
	import numpy as np

	segments = growth_rate_segments(name)
	out_dir = _analysis_dir()

	t0 = segments["t_start"].iloc[0]
	mid_hours = segments.apply(
		lambda r: ((r["t_start"] - t0).total_seconds() + r["duration_hr"] * 3600 / 2) / 3600.0, axis=1
	)

	fig, ax = plt.subplots(figsize=(max(6, 1.2 * len(segments)), 4.5))
	ax.bar(mid_hours, segments["growth_rate_per_hr"], width=segments["duration_hr"] * 0.9,
		   color="steelblue", edgecolor="black", linewidth=0.5)
	ax.axhline(segments["growth_rate_per_hr"].mean(), color="red", linestyle="--",
			   label=rf"mean $\mu$={segments['growth_rate_per_hr'].mean():.3f} hr$^{{-1}}$")
	ax.set_xlabel("Time (hours, midpoint of each interval)")
	ax.set_ylabel(r"Growth rate, $\mu$ (hr$^{-1}$)")
	ax.set_title(f"{name} - segment-wise growth rate between dilutions")
	ax.legend()

	secax = ax.secondary_yaxis("right", functions=(lambda mu: mu * 24, lambda mu24: mu24 / 24))
	secax.set_ylabel(r"Growth rate (day$^{-1}$)")

	fig.tight_layout()
	fig.savefig(os.path.join(out_dir, f"{name}_segment_growth_rate.png"))
	if not show:
		plt.close(fig)
	else:
		plt.show()

	segments.to_csv(os.path.join(out_dir, f"{name}_segment_growth_rate.csv"), index=False)
	print(Panel(Pretty(segments.to_dict(orient="records")), title=f"{name} - segment growth rates"))
	return segments


def analyse_growth(show=False, t_start_hr=None, t_end_hr=None, min_points=3):
	"""
	Standard growth-curve analysis over every colony recorded so far, split
	out by mutant and by whether media (a perturbation) was added. Populates
	the experiment's `analysis/` folder with:

	  - one growth-curve plot per colony (`analysis/<name>_growth.png`)
	  - an overlay of all colonies (`analysis/growth_curves.png`)
	  - a per-mutant / per-perturbation comparison plot
		(`analysis/growth_rate_by_mutant.png`)
	  - a summary table (`analysis/growth_summary.csv`)

	Returns the summary DataFrame (same as `fit_curve`, with mutant/
	perturbation columns already included). Growth rates are always
	computed on the dilution-compensated density.
	"""
	import matplotlib.pyplot as plt
	import numpy as np
	plt.rcParams["text.usetex"] = False
	summary = fit_curve(names=None, show=False, t_start_hr=t_start_hr, t_end_hr=t_end_hr, min_points=min_points)
	out_dir = _analysis_dir()
	plot_df = summary.dropna(subset=["growth_rate_per_hr"]).copy()
	if not plot_df.empty:
		plot_df["mutant"] = plot_df["mutant"].fillna("(unlabelled)")
		plot_df["condition"] = plot_df["perturbed"].map({True: "media added", False: "no media"})
		mutants = sorted(plot_df["mutant"].unique())

		# Only include conditions that actually have data for at least one
		# mutant - otherwise a mutant where every colony was (or wasn't)
		# perturbed leaves a phantom, empty legend entry with no visible bar.
		all_conditions = ["no media", "media added"]
		conditions = [c for c in all_conditions if (plot_df["condition"] == c).any()]

		n_cond = len(conditions)
		width = 0.8 / n_cond
		offsets = (np.arange(n_cond) - (n_cond - 1) / 2) * width
		x = np.arange(len(mutants))

		fig, ax = plt.subplots(figsize=(max(6, 1.2 * len(mutants)), 5))
		for offset, cond in zip(offsets, conditions):
			vals, counts_n = [], []
			for m in mutants:
				rows = plot_df[(plot_df["mutant"] == m) & (plot_df["condition"] == cond)]
				vals.append(rows["growth_rate_per_hr"].mean() if not rows.empty else np.nan)
				counts_n.append(len(rows))
			bars = ax.bar(x + offset, vals, width, label=cond)
			for bar, n, val in zip(bars, counts_n, vals):
				if n > 0 and np.isfinite(val):
					ax.annotate(f"n={n}", (bar.get_x() + bar.get_width() / 2, val),
								ha="center", va="bottom", fontsize=7)

		ax.set_xticks(x)
		ax.set_xticklabels(mutants, rotation=30, ha="right")
		ax.set_ylabel(r"Growth rate, $\mu$ (hr$^{-1}$, dilution-compensated)")
		ax.set_title("Growth rate by mutant and perturbation")
		ax.legend()

		# Secondary axis showing the same rate per 24h, since it's the same
		# exponential constant just rescaled (mu_24hr = mu_hr * 24).
		secax = ax.secondary_yaxis("right", functions=(lambda mu: mu * 24, lambda mu24: mu24 / 24))
		secax.set_ylabel(r"Growth rate (day$^{-1}$)")

		fig.tight_layout()
		fig.savefig(os.path.join(out_dir, "growth_rate_by_mutant.png"))
		if not show:
			plt.close(fig)

		if len(conditions) < len(all_conditions):
			missing = sorted(set(all_conditions) - set(conditions))
			print(Panel(
				f"No colonies fall under: {', '.join(missing)}. "
				f"Every recorded colony currently has the opposite perturbation status, "
				f"so that bar is omitted rather than drawn empty.",
				style="yellow", title="growth_rate_by_mutant.png",
			))
	print(Panel(f"Full growth analysis (by mutant + perturbation) saved to: {out_dir}"))
	return summary


## ---------------------------------------------------------------------------
## Export
## ---------------------------------------------------------------------------

def export_csv(path=None):
	"""
	Export every recorded cell count to a csv file (one row per count, with
	columns: label, mutant, df, density, compensated_density, perturbed,
	timestamp).

	By default writes to `analysis/cell_counts.csv` inside the experiment
	folder; pass `path` to write somewhere else instead.
	"""
	df = _records_dataframe()
	if path is None:
		path = os.path.join(_analysis_dir(), "cell_counts.csv")
	df.to_csv(path, index=False)
	print(Panel(f"Exported {len(df)} count(s) to: {path}", title="export_csv"))
	return path


def export_media_additions_csv(path=None):
	"""
	Export every recorded media-addition event to a csv file (label,
	volume_before_ml, media_added_ml, dilution_fraction, timestamp).

	By default writes to `analysis/media_additions.csv` inside the
	experiment folder; pass `path` to write somewhere else instead.
	"""
	df = _media_additions_dataframe()
	if path is None:
		path = os.path.join(_analysis_dir(), "media_additions.csv")
	df.to_csv(path, index=False)
	print(Panel(f"Exported {len(df)} media addition(s) to: {path}", title="export_media_additions_csv"))
	return path