"""
MicroPython device management: flashing MicroPython itself, and syncing
pico_firmware onto an already-flashed device. Per this session's rule for
core/installer/: this module declares nothing -- the locked MicroPython
version, the firmware image, and the pico_firmware repo location all come
from config.micropython (see core/permaconfig/default_config.yaml), never
hardcoded here.

Flashing: picotool (PICOBOOT protocol, no OS-level mount needed) if it's on
PATH, else a direct fallback -- scan mounted volumes for INFO_UF2.TXT (the
RP2040 bootloader's own marker file; this is the exact mechanism Thonny's
uf2dialog.py uses, verified by reading its source) and copy the firmware
image onto it directly. Getting a device that's already running some
MicroPython into BOOTSEL uses machine.bootloader() over the existing
core.external.pyboard connection; a blank chip needs the physical button.

Sync: wraps hive.processorgroups.micropython.SerialMPDevice.sync_files()
rather than reimplementing file transfer -- that already does incremental
sync (skip_unchanged) and dry_run. Its exclude lists (SKIP_DIRS/SKIP_FILES)
are read from the firmware repo's own sync_what.yaml when present (an
allow-by-default, deny-list manifest -- new files in that repo sync
automatically unless it says otherwise), falling back to SerialMPDevice's
existing hardcoded defaults if the manifest doesn't exist yet. Note this
inherits sync_files()'s own matching granularity: excludes are bare
directory/file names, not full paths -- a same-named directory nested
inside the one you meant to keep (e.g. a stale duplicate copy) can't be
excluded without also excluding the real one. That's a reason to not have
such a duplicate in the repo, not something this tool special-cases around.
"""

import fnmatch
import os
import shutil
import subprocess

import yaml
from rich.console import Console
from rich.prompt import Confirm, IntPrompt

from core.external import pyboard
from core.idioms import devicetree
from core.permaconfig.config import TrappyConfig


def _mpy_config():
    return (TrappyConfig().get().get("config") or {}).get("micropython") or {}


def pick_device(console, candidates=None):
    """Prompt the user to choose among devicetree.micropython_candidates()
    (or an already-fetched list). Returns a ListPortInfo, or None."""
    if candidates is None:
        candidates = devicetree.micropython_candidates()
    if not candidates:
        console.print("[dim]No MicroPython-looking serial devices found.[/dim]")
        return None
    if len(candidates) == 1:
        return candidates[0]
    console.print("[bold]MicroPython devices found:[/bold]")
    for i, p in enumerate(candidates, start=1):
        console.print(f"  {i}. {p.device}  [dim]{p.serial_number or ''}[/dim]")
    choice = IntPrompt.ask("Which device?", choices=[str(i) for i in range(1, len(candidates) + 1)])
    return candidates[choice - 1]


# ----------------------------------------------------------------- flash ---

def _uf2_volumes():
    """Mounted volumes that are an RP2040 in BOOTSEL mode -- identified the
    same way Thonny's uf2dialog.py does: a file named INFO_UF2.TXT at the
    volume's root. No port is opened; this is a filesystem-level check."""
    import psutil
    volumes = []
    for part in psutil.disk_partitions(all=True):
        marker = os.path.join(part.mountpoint, "INFO_UF2.TXT")
        if os.path.isfile(marker):
            volumes.append(part.mountpoint)
    return volumes


def _enter_bootloader(port, console):
    """machine.bootloader() over the existing raw-REPL connection -- the
    device must already be running some MicroPython. Returns True if the
    reset command was sent successfully (not proof it landed in BOOTSEL;
    caller still waits for a UF2 volume to appear)."""
    board_ = None
    try:
        board_ = pyboard.Pyboard(port, 115200)
        board_.enter_raw_repl()
        board_.exec_raw_no_follow("import machine\nmachine.bootloader()")
        return True
    except Exception as e:
        console.print(f"[red]Could not enter bootloader mode: {e}[/red]")
        return False
    finally:
        if board_ is not None:
            try:
                board_.close()
            except Exception:
                pass


def _copy_uf2(image_path, volume, console, dry_run=False, chunk_size=8192):
    dest = os.path.join(volume, os.path.basename(image_path))
    console.print(f"Copying {image_path} -> {dest} ...")
    if dry_run:
        return True
    try:
        with open(image_path, "rb") as src, open(dest, "wb") as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        return True
    except OSError as e:
        console.print(f"[red]Copy failed: {e}[/red]")
        return False


def _flash_with_picotool(image_path, console, dry_run=False):
    command = ["picotool", "load", "-x", image_path]
    console.print(f"$ {' '.join(command)}")
    if dry_run:
        return True
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]picotool failed:[/red] {result.stderr.strip()}")
        return False
    return True


def _firmware_cache_dir():
    cache_dir = os.path.join(os.path.expanduser("~"), "trappyverse", "state", "firmware_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _download_firmware(url, console, dry_run=False):
    """
    Download a firmware image into the local cache, if it isn't there
    already. The cache key is just the URL's own filename -- for
    micropython.org's own downloads that already encodes the version and
    build date (e.g. RPI_PICO_W-20230426-v1.20.0.uf2), so re-running this
    against the same URL reuses the cached file rather than re-fetching.

    Never silent: a real download only happens after an explicit
    confirmation -- same rule as the Miniforge installer in
    core/installer/environment.py -- since this then gets flashed onto
    real hardware, a worse failure mode than a bad software install if
    the download were ever wrong or corrupted.
    """
    filename = os.path.basename(url.split("?")[0])
    cached_path = os.path.join(_firmware_cache_dir(), filename)

    if os.path.isfile(cached_path):
        console.print(f"[dim]Using cached firmware: {cached_path}[/dim]")
        return cached_path

    console.print(f"Firmware image not cached locally: {url}")
    if not Confirm.ask("Download this firmware image?", default=False):
        return None

    if dry_run:
        console.print(f"[dim]Dry run -- would download to {cached_path}[/dim]")
        return cached_path

    import requests
    tmp_path = cached_path + ".part"
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        os.rename(tmp_path, cached_path)
        console.print(f"[green]Downloaded to {cached_path}[/green]")
        return cached_path
    except requests.RequestException as e:
        console.print(f"[red]Download failed: {e}[/red]")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None


def _resolve_firmware_image(image_path, console, dry_run=False):
    """A local path passes through unchanged; a URL is downloaded (once,
    cached) via _download_firmware(). Returns None if a download was
    needed and declined or failed."""
    if image_path.startswith(("http://", "https://")):
        return _download_firmware(image_path, console, dry_run=dry_run)
    return os.path.expanduser(image_path)


def flash(console=None, dry_run=False):
    """
    Flash config.micropython.firmware_image onto a device, skipping it if
    the device already reports config.micropython.version. Uses picotool
    if it's on PATH (verified this session: neither Homebrew on Intel Mac
    nor Debian stable's apt has it, but raspberrypi/pico-sdk-tools ships a
    prebuilt binary for every real target here except 32-bit Raspberry Pi
    OS -- see the picotool/Thonny discussion in this session's notes),
    otherwise the direct UF2-copy fallback.
    """
    console = console or Console()
    cfg = _mpy_config()
    locked_version = cfg.get("version")
    image_path = cfg.get("firmware_image")

    if not image_path:
        console.print("[red]config.micropython.firmware_image is not set -- "
                       "nothing to flash.[/red]")
        return

    candidates = devicetree.micropython_candidates()
    port = None
    if candidates:
        chosen = pick_device(console, candidates)
        if chosen is None:
            return
        port = chosen.device
        if locked_version:
            info = devicetree.probe_micropython(port)
            if info and info.get("mpy_version") == locked_version:
                console.print(f"[green]{port} already reports MicroPython "
                               f"{locked_version} -- nothing to do.[/green]")
                return

    ## Resolved (and, if it's a URL, downloaded) only now -- after the
    ## skip-if-already-current check -- so a device that turns out not to
    ## need flashing never costs a download.
    image_path = _resolve_firmware_image(image_path, console, dry_run=dry_run)
    if not image_path or not (dry_run or os.path.isfile(image_path)):
        console.print("[red]No firmware image available -- nothing to flash.[/red]")
        return

    if port:
        console.print(f"Resetting {port} into bootloader mode ...")
        if not _enter_bootloader(port, console):
            return
    else:
        console.print("[yellow]No running MicroPython device found -- "
                       "put the board in BOOTSEL mode manually "
                       "(hold BOOTSEL while plugging it in).[/yellow]")

    console.print("Waiting for a UF2 volume to appear ...")
    volumes = _uf2_volumes()
    if not volumes:
        if not Confirm.ask("No UF2 volume detected yet. Check again?", default=True):
            return
        volumes = _uf2_volumes()
    if not volumes:
        console.print("[red]No UF2 volume found -- is the device in BOOTSEL mode?[/red]")
        return
    volume = volumes[0]
    console.print(f"Found: {volume}")

    if shutil.which("picotool"):
        ok = _flash_with_picotool(image_path, console, dry_run=dry_run)
    else:
        console.print("[yellow]picotool not found on PATH -- falling back to a direct "
                       "file copy (see docs/notes/devices.md for known reliability "
                       "caveats with this method).[/yellow]")
        ok = _copy_uf2(image_path, volume, console, dry_run=dry_run)

    if ok:
        console.print("[green]Flash complete.[/green]" if not dry_run else "[dim]Dry run -- nothing written.[/dim]")


# ------------------------------------------------------------------ sync ---

def _load_sync_manifest(firmware_dir):
    path = os.path.join(firmware_dir, "sync_what.yaml")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        manifest = yaml.safe_load(f) or {}
    return manifest.get("exclude") or {}


def _resolve_excludes(firmware_dir):
    """
    (skip_dirs, skip_files) for SerialMPDevice.sync_files() -- read from the
    firmware repo's own sync_what.yaml if present (patterns expanded against
    the real directory listing, since sync_files() checks bare-name
    membership, not glob patterns), else SerialMPDevice's own current
    defaults.
    """
    from hive.processorgroups.micropython import SerialMPDevice

    exclude = _load_sync_manifest(firmware_dir)
    if exclude is None:
        return SerialMPDevice.SKIP_DIRS, SerialMPDevice.SKIP_FILES

    dir_patterns = exclude.get("dirs") or []
    file_patterns = exclude.get("files") or []

    all_dir_names, all_file_names = set(), set()
    for _root, dirs, files in os.walk(firmware_dir):
        all_dir_names.update(dirs)
        all_file_names.update(files)

    skip_dirs = tuple(sorted(
        name for name in all_dir_names
        if any(fnmatch.fnmatch(name, pat) for pat in dir_patterns)
    ))
    skip_files = tuple(sorted(
        name for name in all_file_names
        if any(fnmatch.fnmatch(name, pat) for pat in file_patterns)
    ))
    return skip_dirs, skip_files


def sync(console=None, dry_run=False):
    """
    Sync config.micropython.firmware_dir (the pico_firmware repo root) onto
    a device via SerialMPDevice.sync_files() -- incremental (skip_unchanged),
    so this works for both a fresh device (auto-bootstraps board.py and
    blinks, per pico_firmware/main.py) and updating one already running it.
    """
    from hive.processorgroups.micropython import SerialMPDevice

    console = console or Console()
    cfg = _mpy_config()
    firmware_dir = cfg.get("firmware_dir")
    if not firmware_dir:
        console.print("[red]config.micropython.firmware_dir is not set.[/red]")
        return
    firmware_dir = os.path.expanduser(firmware_dir)
    if not os.path.isdir(firmware_dir):
        console.print(f"[red]firmware_dir does not exist: {firmware_dir}[/red]")
        return

    chosen = pick_device(console)
    if chosen is None:
        return

    skip_dirs, skip_files = _resolve_excludes(firmware_dir)
    original = (SerialMPDevice.SKIP_DIRS, SerialMPDevice.SKIP_FILES)
    SerialMPDevice.SKIP_DIRS, SerialMPDevice.SKIP_FILES = skip_dirs, skip_files
    try:
        device = SerialMPDevice(name=chosen.device, connect=True, port=chosen.device)
        device.connect(chosen.device)
        if not device.connected:
            console.print(f"[red]Could not connect to {chosen.device}.[/red]")
            return
        device.sync_files(firmware_dir, "/", dry_run=dry_run, verbose=True)
        device.disconnect()
    finally:
        SerialMPDevice.SKIP_DIRS, SerialMPDevice.SKIP_FILES = original


if __name__ == "__main__":
    pass
