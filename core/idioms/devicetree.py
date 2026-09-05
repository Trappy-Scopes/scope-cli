"""
Device tree: what's physically attached to this machine right now --
serial ports, USB devices, keyboard/mouse, and displays. Read-only
introspection, same shape as platform.py's @fact registry: each
category is collected independently via a `_CATEGORIES` registry, and
a failing collector doesn't take the rest down with it.

No single library enumerates all of this across OSes, so this follows
the OS instead of fighting it -- same call as install_native() in
core/installer/environment.py: pyserial's list_ports is genuinely
cross-platform and used for serial; everything else is macOS
(system_profiler, already on every Mac) or Linux (/sys, /proc --
already on every Linux, no extra dependency), with no attempt made on
other platforms.

Deliberately shows only what's *currently present*, not history --
e.g. macOS Bluetooth pairings that aren't connected right now are
dropped (device_connected only, never device_not_connected), since a
device tree meant to be read at a glance is exactly what gets crowded
out by every accessory ever paired.

The macOS USB/input parsing (system_profiler's JSON shape) and the
Linux paths (/sys/bus/usb/devices, /proc/bus/input/devices,
/sys/class/drm) were checked against real output on this Mac and
against documented sysfs/procfs formats respectively -- the Linux
paths have not been verified against real Linux hardware in this
session (same caveat as the Jetson hardware profile).
"""

import json
import os
import platform as _platform
import subprocess

_CATEGORIES = {}


def category(name):
    def decorator(fn):
        _CATEGORIES[name] = fn
        return fn
    return decorator


def _run_json(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    return json.loads(result.stdout)


# ------------------------------------------------------------- serial ---

@category("serial")
def _serial():
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    devices = []
    for p in list_ports.comports():
        detail = None if p.description in (None, "n/a") else p.description
        devices.append({"label": p.device, "detail": detail})
    return devices


# ---------------------------------------------------------------- usb ---

@category("usb")
def _usb():
    system = _platform.system()
    if system == "Darwin":
        return _usb_macos()
    if system == "Linux":
        return _usb_linux()
    return []


def _usb_macos():
    try:
        data = _run_json(["system_profiler", "SPUSBDataType", "-json"])
    except Exception:
        return []
    devices = []

    def walk(items):
        for item in items:
            if "_items" in item:
                walk(item["_items"])
            # Bus/hub-controller nodes are the tree's own scaffolding, not
            # attached devices -- heuristic by name, not a robust classifier
            # (no external USB device was attached to verify this against).
            elif not item.get("_name", "").endswith("Bus"):
                devices.append({
                    "label": item.get("_name", "USB device"),
                    "detail": item.get("manufacturer"),
                })
    walk(data.get("SPUSBDataType", []))
    return devices


def _usb_linux():
    root = "/sys/bus/usb/devices"
    if not os.path.isdir(root):
        return []
    devices = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        product_file = os.path.join(path, "product")
        if not os.path.isfile(product_file):
            continue  # root hubs and interfaces have no "product" file -- real devices do
        try:
            with open(product_file) as f:
                product = f.read().strip()
            manufacturer = None
            manufacturer_file = os.path.join(path, "manufacturer")
            if os.path.isfile(manufacturer_file):
                with open(manufacturer_file) as f:
                    manufacturer = f.read().strip()
            devices.append({"label": product, "detail": manufacturer})
        except OSError:
            continue
    return devices


# -------------------------------------------------------------- input ---

@category("input")
def _input():
    system = _platform.system()
    if system == "Darwin":
        return _input_macos()
    if system == "Linux":
        return _input_linux()
    return []


def _input_macos():
    """
    macOS has no cross-vendor API for "what keyboard/mouse is attached"
    short of IOKit (would mean a new pyobjc dependency); Bluetooth ones
    are visible via system_profiler, already on every Mac, so that's
    what this uses. A wired USB keyboard/mouse would show up in the usb
    category instead, generically, since SPUSBDataType doesn't classify
    device kind.
    """
    try:
        data = _run_json(["system_profiler", "SPBluetoothDataType", "-json"])
    except Exception:
        return []
    devices = []
    for controller in data.get("SPBluetoothDataType", []):
        for entry in controller.get("device_connected", []):
            for name, info in entry.items():
                minor = info.get("device_minorType")
                if minor in ("Keyboard", "Mouse", "Trackpad"):
                    devices.append({"label": name, "detail": minor})
    return devices


def _input_linux():
    path = "/proc/bus/input/devices"
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return []

    devices = []
    name = None
    handlers = ""

    def flush():
        if name is None:
            return
        if "kbd" in handlers:
            kind = "Keyboard"
        elif "mouse" in handlers:
            kind = "Mouse"
        else:
            return  # neither -- skip to keep this minimal
        devices.append({"label": name, "detail": kind})

    for line in lines:
        if line.startswith("N: Name="):
            name = line.split("=", 1)[1].strip('"')
        elif line.startswith("H: Handlers="):
            handlers = line.split("=", 1)[1]
        elif line == "":
            flush()
            name = None
            handlers = ""
    flush()
    return devices


# ------------------------------------------------------------ display ---

@category("display")
def _display():
    system = _platform.system()
    if system == "Darwin":
        return _display_macos()
    if system == "Linux":
        return _display_linux()
    return []


def _display_macos():
    try:
        data = _run_json(["system_profiler", "SPDisplaysDataType", "-json"])
    except Exception:
        return []
    devices = []
    for gpu in data.get("SPDisplaysDataType", []):
        for d in gpu.get("spdisplays_ndrvs", []):
            devices.append({
                "label": d.get("_name", "Display"),
                "detail": d.get("_spdisplays_resolution"),
            })
    return devices


def _display_linux():
    root = "/sys/class/drm"
    if not os.path.isdir(root):
        return []
    devices = []
    for name in sorted(os.listdir(root)):
        status_file = os.path.join(root, name, "status")
        if not os.path.isfile(status_file):
            continue
        try:
            with open(status_file) as f:
                status = f.read().strip()
        except OSError:
            continue
        if status != "connected":
            continue
        detail = None
        modes_file = os.path.join(root, name, "modes")
        if os.path.isfile(modes_file):
            try:
                with open(modes_file) as f:
                    first_mode = f.readline().strip()
                detail = first_mode or None
            except OSError:
                pass
        devices.append({"label": name, "detail": detail})
    return devices


# ------------------------------------------------------------- storage ---

_SKIP_FSTYPES = {
    "devfs", "autofs", "tmpfs", "proc", "sysfs", "overlay", "squashfs",
    "devtmpfs", "cgroup", "cgroup2",
}


@category("storage")
def _storage():
    """
    Every genuinely separate mounted disk -- root plus anything actually
    plugged in, not the internal bookkeeping of one physical disk. Answers
    "what storage is attached" the same way the other categories answer
    "what's attached": something plugged in after the fact (a new SSD)
    should show up here.

    Filters two kinds of noise, or this list turns into everything the OS
    happens to mount rather than what a person would call "a disk": pseudo-
    filesystems (_SKIP_FSTYPES: devfs, tmpfs, proc/sysfs, container overlay
    layers -- never real storage), and, on macOS specifically, the several
    /System/Volumes/* entries (VM, Preboot, Update, ...) that are internal
    slices of the *same* physical disk "/" already reports.

    macOS also splits that same physical disk into a read-only "/" (a
    synthetic firmlink snapshot) and a read-write /System/Volumes/Data --
    both report the same disk, but "/" alone shows only the tiny system
    snapshot's own usage, not the real figure. When both are present, "/"
    is dropped and Data's real usage is kept, relabelled "/" -- what a
    person means by "the root disk" is the whole thing, not either
    half's own internal name for it.
    """
    try:
        import psutil
    except ImportError:
        return []

    partitions = list(psutil.disk_partitions(all=False))
    mountpoints = {p.mountpoint for p in partitions}
    macos_split_root = "/" in mountpoints and "/System/Volumes/Data" in mountpoints

    devices = []
    for part in partitions:
        if part.fstype in _SKIP_FSTYPES:
            continue
        if part.mountpoint.startswith("/System/Volumes/") and part.mountpoint != "/System/Volumes/Data":
            continue
        if macos_split_root and part.mountpoint == "/":
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        label = "/" if part.mountpoint == "/System/Volumes/Data" else part.mountpoint
        gb = 1024 ** 3
        devices.append({
            "label": label,
            "detail": f"{usage.used / gb:.1f}/{usage.total / gb:.1f} GB used",
        })
    return devices


# ---------------------------------------------------------------- top ---

def collect(categories=None):
    """
    {category: [{"label", "detail"}, ...]}, one key per requested
    category (all registered categories if none given). A category
    whose collector raises gets an empty list rather than breaking the
    others -- same "one bad fact doesn't sink collect()" contract as
    platform.py.
    """
    categories = categories or list(_CATEGORIES)
    result = {}
    for name in categories:
        try:
            result[name] = _CATEGORIES[name]()
        except Exception:
            result[name] = []
    return result
