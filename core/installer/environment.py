"""
All installation logic for this project lives here -- core/installer/, not
launcher/, not scattered across other modules (established this session:
"the launcher is a minimal UI thing, everything installation-related goes
in core"). launcher/utilities/environment.py is a thin caller of this file
and nothing else.

Responsibilities, in the order ensure() runs them:
  1. PEP 668 / isolated-environment handling
  2. ensure_uv()      -- the Tier 0 -> backbone handoff
  3. discover + select hardware profiles (native, config-declared, machine-
     local, in that precedence order)
  4. plan what each selected profile needs, show it, confirm once
  5. apply the plan -- uv for Python packages, native OS manager (apt/brew)
     or conda-forge for binaries, per hardware-profiles/*/system.yaml

Nothing here ever declares a dependency itself -- every package name comes
from bootstrap-requirements.txt, pyproject.toml, or a hardware-profiles/*/
file. This module only reads those and acts.
"""

import os
import platform as _platform
import shutil
import subprocess
import sys
import sysconfig

import yaml
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from core.permaconfig.config import TrappyConfig


# ------------------------------------------------------------------ uv ---

def ensure_uv(console=None):
	"""Return a working `uv`, installing it via pip if not already present."""
	console = console or Console()
	exe = shutil.which("uv")
	if exe:
		return exe

	console.print("[yellow]uv not found -- installing via `pip install uv`...[/yellow]")
	result = subprocess.run([sys.executable, "-m", "pip", "install", "uv"],
							 capture_output=True, text=True)
	if result.returncode != 0:
		console.print(f"[red]Failed to install uv:[/red] {result.stderr.strip()}")
		return None

	exe = shutil.which("uv")
	if exe is None:
		console.print("[red]uv installed but not found on PATH.[/red]")
	return exe


# ------------------------------------------------------------ PEP 668 ---

def pep668_active():
	"""Whether this interpreter's stdlib is marked externally-managed."""
	marker = os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")
	return os.path.exists(marker)


def in_isolated_environment():
	"""Already inside a venv or conda env -- PEP 668 doesn't apply either way."""
	return sys.prefix != sys.base_prefix or bool(os.environ.get("CONDA_DEFAULT_ENV"))


def ensure_python_environment(console=None):
	"""
	If PEP 668 applies and we're not already isolated, ask whether to
	create a venv or proceed with --break-system-packages.

	Returns extra pip flags for subsequent installs (possibly []), or None
	if a venv was created -- the caller should stop, since a fresh venv
	needs its own interpreter, not this one.
	"""
	console = console or Console()
	if in_isolated_environment() or not pep668_active():
		return []

	console.print("[yellow]This Python is externally managed (PEP 668) -- "
				  "system-wide pip installs are blocked by default.[/yellow]")
	if Confirm.ask("Create an isolated virtual environment instead of "
				   "forcing a system-wide install?", default=True):
		venv_dir = os.path.expanduser("~/.trappyscope-venv")
		console.print(f"Creating venv at {venv_dir} ...")
		subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
		console.print(f"[green]Created.[/green] Re-run trappyscope from "
					  f"{venv_dir}/bin/python to use it.")
		return None

	return ["--break-system-packages"]


# --------------------------------------------------------------- conda ---

def _working_conda():
	for exe in (shutil.which("mamba"), shutil.which("conda")):
		if exe is None:
			continue
		if subprocess.run([exe, "--version"], capture_output=True).returncode == 0:
			return exe
	return None


def ensure_conda(console=None):
	"""
	Return a working conda/mamba, installing Miniforge if none is found --
	only after an explicit confirmation naming exactly what will happen and
	where. Never silent, and never installed into trappyverse/ (that's
	configuration, not software) -- goes to the standard ~/miniforge3
	location every conda user already expects, or reuses an existing
	install (any working conda/mamba, not just one this project made).
	"""
	console = console or Console()
	exe = _working_conda()
	if exe:
		return exe

	console.print("[yellow]No working conda/mamba found.[/yellow]")
	console.print("This would download and run the Miniforge installer "
				  "(conda-forge's own distribution) into ~/miniforge3.")
	if not Confirm.ask("Proceed?", default=False):
		return None

	system = _platform.system()
	arch = _platform.machine()
	url = (f"https://github.com/conda-forge/miniforge/releases/latest/"
		   f"download/Miniforge3-{system}-{arch}.sh")
	installer_path = "/tmp/miniforge-installer.sh"
	console.print(f"Downloading {url} ...")
	subprocess.run(["curl", "-fsSL", url, "-o", installer_path], check=True)
	subprocess.run(["bash", installer_path, "-b", "-p",
					os.path.expanduser("~/miniforge3")], check=True)
	return shutil.which("mamba") or os.path.expanduser("~/miniforge3/bin/conda")


# --------------------------------------------------- profile discovery ---

def _native_profiles_dir():
	# core/installer/environment.py -> core/installer -> core -> repo root
	return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
		os.path.abspath(__file__)))), "hardware-profiles")


def _machine_local_profiles_dir():
	return os.path.expanduser("~/trappyverse/hardware-profiles")


def _configured_profile_dirs(config=None):
	if config is None:
		config = TrappyConfig().get()
	return (config.get("config") or {}).get("hardware_profile_dirs") or []


def discover_profile_roots(config=None):
	"""
	Search roots, LOWEST precedence first: native, then each
	config.hardware_profile_dirs entry, then machine-local. A later root
	shadows an earlier one that declares the same profile name.
	"""
	roots = [_native_profiles_dir()]
	roots += [os.path.expanduser(p) for p in _configured_profile_dirs(config)]
	roots.append(_machine_local_profiles_dir())
	return roots


def _profiles_in(root):
	if not os.path.isdir(root):
		return {}
	found = {}
	for name in sorted(os.listdir(root)):
		d = os.path.join(root, name)
		if os.path.isfile(os.path.join(d, "profile.yaml")) or os.path.isfile(os.path.join(d, "setup.sh")):
			found[name] = d
	return found


def discover_profiles(config=None):
	"""{name: dir}, later (more local) roots overriding earlier ones by name."""
	result = {}
	for root in discover_profile_roots(config):
		result.update(_profiles_in(root))
	return result


def select_profiles(config=None):
	"""
	Every discovered profile whose `detect` command exits 0. A profile
	with no profile.yaml (a bare setup.sh) is unconditional -- there's
	nowhere to put a detect command in that shape.

	`detect` is run via the shell, deliberately -- same trust model as
	config.venv.command elsewhere in this codebase: local, user-authored
	config, not untrusted input.
	"""
	selected = {}
	for name, path in discover_profiles(config).items():
		profile_yaml = os.path.join(path, "profile.yaml")
		if not os.path.isfile(profile_yaml):
			selected[name] = path
			continue
		with open(profile_yaml) as f:
			spec = yaml.safe_load(f) or {}
		detect = spec.get("detect")
		if not detect or subprocess.run(detect, shell=True, capture_output=True).returncode == 0:
			selected[name] = path
	return selected


# -------------------------------------------------------- plan / apply ---

def plan_profile(profile_dir):
	"""
	Pure: describes what applying this profile would do, without doing it.
	No subprocess calls, no side effects -- just reads files.
	"""
	setup_sh = os.path.join(profile_dir, "setup.sh")
	if os.path.isfile(setup_sh):
		return {"setup_sh": setup_sh}

	plan = {"uv_requirements": None, "native": [], "apt_only": [], "conda_forge": []}

	requirements = os.path.join(profile_dir, "requirements.txt")
	if os.path.isfile(requirements):
		plan["uv_requirements"] = requirements

	system_yaml_path = os.path.join(profile_dir, "system.yaml")
	if os.path.isfile(system_yaml_path):
		with open(system_yaml_path) as f:
			system_yaml = yaml.safe_load(f) or {}
		plan["native"] = system_yaml.get("native") or []
		plan["apt_only"] = system_yaml.get("apt_only") or []
		plan["conda_forge"] = system_yaml.get("conda_forge") or []

	return plan


def install_native(packages, console=None, dry_run=False):
	"""apt (Linux) / brew (Mac). No Windows wrapper -- see apply_plan."""
	console = console or Console()
	system = _platform.system()
	if system == "Linux":
		command = ["sudo", "apt-get", "install", "-y", *packages]
	elif system == "Darwin":
		command = ["brew", "install", *packages]
	else:
		console.print(f"[yellow]No native package manager wrapper for {system} -- "
					  f"skipping: {packages}[/yellow]")
		return
	console.print(f"$ {' '.join(command)}")
	if not dry_run:
		subprocess.run(command, check=False)


def install_conda_forge(packages, console=None, dry_run=False):
	console = console or Console()
	exe = ensure_conda(console=console)
	if exe is None:
		console.print(f"[red]No conda available -- skipping: {packages}[/red]")
		return
	command = [exe, "install", "-y", "-c", "conda-forge", *packages]
	console.print(f"$ {' '.join(command)}")
	if not dry_run:
		subprocess.run(command, check=False)


def apply_plan(plan, console=None, dry_run=False, extra_pip_args=(), include_conda_forge=False):
	"""
	Execute a plan_profile() result. setup.sh, if present, is run verbatim
	and nothing else in the plan is consulted -- the escape hatch is
	one-shot and untracked, on purpose.
	"""
	console = console or Console()

	if "setup_sh" in plan:
		console.print(f"Running {plan['setup_sh']} verbatim ...")
		if not dry_run:
			subprocess.run(["bash", plan["setup_sh"]], check=False)
		return

	if plan["uv_requirements"]:
		uv = ensure_uv(console=console)
		command = [uv, "pip", "install", "-r", plan["uv_requirements"], *extra_pip_args]
		console.print(f"$ {' '.join(command)}")
		if not dry_run:
			subprocess.run(command, check=False)

	system = _platform.system()
	if system == "Windows":
		# No native/apt_only wrapper on Windows; apt_only is intentionally
		# excluded even here -- it's board-coupled, meaningless on Windows.
		all_conda = plan["native"] + plan["conda_forge"]
		if all_conda:
			install_conda_forge(all_conda, console=console, dry_run=dry_run)
	else:
		if plan["native"]:
			install_native(plan["native"], console=console, dry_run=dry_run)
		if plan["apt_only"] and system == "Linux":
			install_native(plan["apt_only"], console=console, dry_run=dry_run)
		if plan["conda_forge"] and include_conda_forge:
			install_conda_forge(plan["conda_forge"], console=console, dry_run=dry_run)


# ---------------------------------------------------------------- top ---

def ensure(console=None, dry_run=False):
	"""The full sequence: env/PEP668 -> uv -> discover+plan+confirm -> apply."""
	console = console or Console()

	extra_pip_args = ensure_python_environment(console=console)
	if extra_pip_args is None:
		return  # a venv was created; this interpreter's job is done
	ensure_uv(console=console)

	profiles = select_profiles()
	if not profiles:
		console.print("[dim]No hardware profile matched this machine.[/dim]")
		return

	table = Table(title="Selected hardware profiles")
	table.add_column("Name")
	table.add_column("Source")
	for name, path in profiles.items():
		table.add_row(name, path)
	console.print(table)

	plans = {name: plan_profile(path) for name, path in profiles.items()}

	system = _platform.system()
	include_conda_forge = system == "Windows"  # required there, no native wrapper exists
	conda_forge_pkgs = sorted({pkg for p in plans.values() for pkg in p.get("conda_forge", [])})
	if conda_forge_pkgs and not include_conda_forge:
		include_conda_forge = Confirm.ask(
			f"Also install via conda-forge (opt-in on {system}): {conda_forge_pkgs}?",
			default=False)

	if not Confirm.ask("Proceed with the above?", default=True):
		return

	for plan in plans.values():
		apply_plan(plan, console=console, dry_run=dry_run,
				   extra_pip_args=extra_pip_args, include_conda_forge=include_conda_forge)
