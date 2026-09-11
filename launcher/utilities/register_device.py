"""
"Register device" menu item: mark which physical MicroPython board
(identified by its USB serial-number descriptor -- its UID, verified
this session to equal machine.unique_id() read over the REPL exactly)
is doing what. Deliberately a separate, explicit action from the device
tree -- registering is a decision a person makes, not something inferred
just because a board happens to be plugged in.

Calling this again on an already-registered device is how you
re-register it -- it always probes fresh regardless of whether the UID
is already known, since the whole point of running it again on a known
device is that its role (or its firmware) changed. Once registered, the
device tree (core/idioms/devicetree.py) reads the cached mpy_version/
circuit_id/role from the registry instead of opening the port again.
"""

from rich.console import Console
from rich.prompt import IntPrompt, Prompt

from core.idioms import devicetree, deviceregistry


def register(console=None):
	console = console or Console()

	candidates = devicetree.micropython_candidates()
	if not candidates:
		console.print("[dim]No MicroPython-looking serial devices found.[/dim]")
		return

	console.print("[bold]MicroPython devices found:[/bold]")
	for i, p in enumerate(candidates, start=1):
		uid = p.serial_number or "(no serial number reported)"
		existing = deviceregistry.get(p.serial_number) if p.serial_number else None
		status = f"registered as '{existing.get('role')}'" if existing else "unregistered"
		console.print(f"  {i}. {p.device}  [dim]{uid}[/dim]  -- {status}")

	if len(candidates) == 1:
		choice = 1
	else:
		choice = IntPrompt.ask("Which device?",
								choices=[str(i) for i in range(1, len(candidates) + 1)])

	port = candidates[choice - 1]
	if not port.serial_number:
		console.print("[red]This device reports no USB serial number -- cannot register it "
					  "(nothing stable to key the registry on).[/red]")
		return

	existing = deviceregistry.get(port.serial_number)
	if existing:
		console.print(f"[yellow]Already registered as '{existing.get('role')}' "
					  f"(since {existing.get('registered_at')}) -- re-registering.[/yellow]")

	console.print(f"Connecting to {port.device} ...")
	info = devicetree.probe_micropython(port.device)
	if not info:
		console.print("[red]Could not connect -- not registered.[/red]")
		return

	summary = f"MicroPython {info['mpy_version']}"
	if info["circuit_id"]:
		summary += f" · pico_firmware: {info['circuit_id']}"
	console.print(summary)

	default_role = existing.get("role") if existing else None
	if default_role is not None:
		role = Prompt.ask("Role (what is this device for)", default=default_role)
	else:
		role = Prompt.ask("Role (what is this device for)")

	deviceregistry.register(
		port.serial_number,
		mpy_version=info["mpy_version"],
		circuit_id=info["circuit_id"],
		role=role,
		last_port=port.device,
	)
	console.print(f"[green]Registered {port.serial_number} as '{role}'.[/green]")


if __name__ == "__main__":
	register()
