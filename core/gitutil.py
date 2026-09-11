"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

Small, generic GitPython-based helpers for local git provenance and
clone-if-missing -- kept separate from any one feature that needs them
(protocols, the launcher's repository-status utility, ...), per this
codebase's dependency direction: `core` has no dependents inside it, so
anything above it (expframework, launcher) can import from here without
creating a layering cycle (expframework importing launcher directly would
invert the intended direction -- launcher/utilities/repo_sync.py already
uses GitPython the same way, see docs/notes/restructuring.md).
"""

import os

import git


def ensure_cloned(url, path):
	"""Clone `url` into `path` if it isn't already a git repository there.
	Returns True if a clone just happened, False if `path` was already a
	repo. config.git_dependencies already states this url <-> path mapping
	explicitly (see README's "Expanded config fields" table) -- this is
	the one place that actually acts on it, so a dependency that hasn't
	been cloned yet doesn't need a second, separate resolution path (see
	docs/notes/protocols.md §6)."""
	path = os.path.expanduser(path)
	try:
		git.Repo(path)
		return False
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		parent = os.path.dirname(path.rstrip(os.sep)) or "."
		os.makedirs(parent, exist_ok=True)
		git.Repo.clone_from(url, path)
		return True


def permalink_base(remote_url):
	"""https://github.com/<org>/<repo> from either an https or git@ remote
	URL -- so a permalink can be built by string substitution alone, with
	no API call."""
	url = remote_url.strip()
	if url.endswith(".git"):
		url = url[:-4]
	if url.startswith("git@"):
		host, _, path = url[4:].partition(":")
		url = f"https://{host}/{path}"
	return url


def provenance(repo_root, relpath):
	"""(commit, uncommitted_changes, permalink) for `relpath` inside the
	git repository at `repo_root` -- derived entirely from local git
	metadata (HEAD, working-tree status, the `origin` remote), no network
	call. Returns (None, None, None) if `repo_root` isn't actually a git
	repository (e.g. a plain, non-cloned protocols_dirs entry)."""
	try:
		repo = git.Repo(repo_root)
	except (git.InvalidGitRepositoryError, git.NoSuchPathError):
		return None, None, None
	try:
		commit = repo.head.commit.hexsha
	except Exception:
		return None, None, None

	uncommitted_changes = repo.is_dirty(path=relpath)

	permalink = None
	try:
		remote_url = repo.remotes.origin.url
		permalink = f"{permalink_base(remote_url)}/blob/{commit}/{relpath}"
	except Exception:
		pass  # no `origin` remote, or it isn't GitHub-shaped -- permalink stays None

	return commit, uncommitted_changes, permalink
