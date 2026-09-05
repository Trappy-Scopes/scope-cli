"""
Device registry: which physical MicroPython boards (identified by UID --
the USB serial-number descriptor, which for RP2040 boards is the flash's
own unique ID, verified this session to match machine.unique_id() read
over the REPL exactly) have been registered, and what role each one is
playing.

A device becomes registered by deliberate action -- the "Register
device" launcher utility (launcher/utilities/register_device.py), or
eventually mounting it onto a ScopeAssembly -- never automatically just
by showing up in the device tree. Once registered, a UID's cached
mpy_version/circuit_id/role can be read without opening the device's
serial port at all, since the UID itself is already free (read at USB
enumeration time, no port open needed) -- only an *unregistered* device
needs the actual raw-REPL round trip to find out what it is.

Stored as plain YAML under trappyverse/state/ (not shelve, unlike
hive/physical.py's runtime state) -- this is meant to be human-
inspectable and hand-editable, same reasoning as every other YAML config
file in this codebase, not a private runtime cache.
"""

import datetime
import os

import yaml

_REGISTRY_FILE = "device_registry.yaml"


def _registry_path():
    statedir = os.path.join(os.path.expanduser("~"), "trappyverse", "state")
    os.makedirs(statedir, exist_ok=True)
    return os.path.join(statedir, _REGISTRY_FILE)


def load():
    """{uid: {...}} -- empty dict if the registry doesn't exist yet."""
    path = _registry_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}


def save(registry):
    with open(_registry_path(), "w") as f:
        yaml.safe_dump(registry, f, sort_keys=True, default_flow_style=False)


def get(uid):
    """This UID's registry entry, or None if it isn't registered."""
    return load().get(uid)


def register(uid, **fields):
    """
    Set or update one UID's entry. Re-registering an already-known UID
    (the point of calling this on a device that's already registered --
    its role changed, or it was reflashed with different pico_firmware)
    keeps `registered_at` from the first registration and bumps
    `updated_at`; a first-time registration sets both to now.
    """
    registry = load()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    existing = registry.get(uid, {})
    entry = {**existing, **fields}
    entry["registered_at"] = existing.get("registered_at", now)
    entry["updated_at"] = now
    registry[uid] = entry
    save(registry)
    return entry
