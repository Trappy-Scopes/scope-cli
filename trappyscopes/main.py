"""
The `trappyscope` installed console script (see pyproject.toml
[project.scripts]).

Dispatches to launcher.fast_track() or launcher.run_launcher() depending on
--launcher. core.argparser is imported first because it's the module that
actually parses sys.argv (a side-effecting import, by existing convention --
see core/argparser.py) and some of its flags (--install, --intro, ...) exit()
before this function would ever branch.
"""


def main():
	import core.argparser  # noqa: F401
	from core.permaconfig.sharing import Share

	if Share.argparse.get("launcher"):
		from launcher import run_launcher
		run_launcher()
	else:
		from launcher import fast_track
		fast_track()


if __name__ == "__main__":
	main()
