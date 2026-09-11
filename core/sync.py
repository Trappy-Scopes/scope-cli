"""
General-purpose file-sync primitives: mount a share, run rsync.

Not experiment- or config-specific. Both `ExpSync` (syncing experiment data)
and the launcher's config-sync utility (syncing the trappyverse/ folder) need
"connect to a share, transfer files" -- this is the one place that logic
lives, so it only has to be gotten right once.

Shells out to the real `rsync` binary rather than a third-party Python rsync
package: rsync already handles archive mode, compression, update-only,
delta-transfer and dry-run as plain CLI flags, and this codebase already had
working precedent doing exactly this (the old ExpSync.sync_file) before this
module existed.

This file replaces a previous, dead `SyncEngine` class here that imported a
`config.common` module which does not exist anywhere in this repository and
was never actually invoked by anything live.
"""

import logging as log
import os
import platform
import subprocess
import time


def mount(server, share, username, password):
	"""
	Mount an SMB share. Returns the local mount point.
	"""
	system = platform.system()

	if system == "Linux":
		mount_point = f"/mnt/{share}"
		command = [
			"sudo", "mount", "-t", "cifs", f"//{server}/{share}", mount_point,
			"-o", f"username={username},password={password},rw,"
				  f"file_mode=0777,dir_mode=0777,uid=1000,gid=1000",
		]
		try:
			subprocess.run(command, check=True)
			time.sleep(5)
		except subprocess.CalledProcessError as e:
			if "error(16)" not in str(e):
				raise
			log.info("Share already mounted.")
		return mount_point

	elif system == "Darwin":
		command = ["open", f"smb://{username}:{password}@{server}/{share}"]
		subprocess.run(command, check=True)
		time.sleep(5)
		return f"/Volumes/{share}"

	else:
		raise NotImplementedError(f"Mounting not implemented for {system!r}.")


## Base flags for each sync mode. "update" (the default) is what "keep the
## latest copy" means: rsync's -u skips a file at the destination if it's
## newer than the source, so running this in both directions (pull, then
## push, or vice versa) never overwrites a newer file with an older one.
MODES = {
	"mirror": ["-a"],                                                # exact copy, always overwrite
	"update": ["-a", "-u"],                                          # skip files newer at the destination
	"archive": ["-a", "-u", "--backup", "--backup-dir=.rsync-backup"],  # update, but keep what it would overwrite
}


def sync(source, destination, mode="update", flags=None, compress=False,
		 dry_run=False, excludes=(), remove_source=False, prefix=(), itemize=False):
	"""
	Run rsync from `source` to `destination`.

	mode:      one of MODES, used to compute the base flags. Ignored if
	           `flags` is given.
	flags:     override the mode's base flags entirely, verbatim -- for
	           callers with their own specific requirements (see ExpSync,
	           which needs -W --no-compress --inplace for large binary
	           experiment files where rsync's delta-transfer algorithm and
	           compression aren't worth the overhead).
	prefix:    command-prefix tokens prepended before `rsync` itself, e.g.
	           ("sudo", "ionice", "-c2", "-n4") to throttle I/O priority so
	           a sync doesn't compete with a live experiment.
	remove_source: pass --remove-source-files (move rather than copy).
	itemize:   pass --itemize-changes -- the result's .stdout then has one
	           line per file actually transferred (see changed_files()),
	           instead of no output at all on success. Opt-in and additive
	           to whatever `mode`/`flags` already computed, so it doesn't
	           change behavior for existing callers (ExpSync) that don't
	           ask for it.

	Returns the completed subprocess.CompletedProcess; does not raise on a
	non-zero exit, so a failed sync doesn't take down its caller -- check
	`.returncode`.
	"""
	if flags is None:
		if mode not in MODES:
			raise ValueError(f"Unknown sync mode: {mode!r}. Choose from {list(MODES)}.")
		flags = list(MODES[mode])
	else:
		flags = list(flags)

	if compress:
		flags.append("-z")
	if dry_run:
		flags.append("--dry-run")
	if remove_source:
		flags.append("--remove-source-files")
	if itemize:
		flags.append("--itemize-changes")
	for pattern in excludes:
		flags.append(f"--exclude={pattern}")

	command = [*prefix, "rsync", *flags, source, destination]
	result = subprocess.run(command, capture_output=True, text=True)
	if result.returncode != 0:
		log.error(f"rsync failed ({result.returncode}): {result.stderr.strip()}")
	return result


## AI Generated -- itemize= param above and changed_files() below, added
## by Claude (Anthropic) for sync_config.py's itemized-change reporting.
def changed_files(result):
	"""Filenames a sync(..., itemize=True) result actually transferred,
	parsed from its --itemize-changes stdout. Each such line is a
	change-code column, a space, then the path (verified directly:
	`>f+++++++++ file.txt` for a new file, `>f..t...... file.txt` for an
	updated one) -- splitting on the first run of whitespace avoids
	assuming an exact column width, which varies with rsync version/flags.
	A file whose contents/timestamp didn't need transferring never gets a
	line at all, so this list is exactly "what changed", not "what was
	compared".

	Only regular files are included -- the code's 2nd character is the
	file-type indicator (verified directly: 'f' for a file, 'd' for a
	directory), and a directory's own line (e.g. ".d..t.... ./") is just
	rsync bumping that directory's timestamp attributes, not a file
	anyone synced actually changing."""
	files = []
	for line in result.stdout.splitlines():
		parts = line.split(None, 1)
		if len(parts) == 2 and len(parts[0]) > 1 and parts[0][1] == "f":
			files.append(parts[1])
	return files
