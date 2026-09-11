"""
Environment setup -- uv, conda, PEP 668/venv, hardware-profile sync. Thin
on purpose: the launcher is a minimal UI layer, so this only calls into
core.installer.environment, which is where all of that logic actually
lives.

This is the concrete implementation of docs/notes/restructuring.md's §7.3
step 0 (environment activation) -- open since the very first session on
this codebase.
"""


def ensure():
	from core.installer import environment
	environment.ensure()


if __name__ == "__main__":
	ensure()
