"""Show the introduction. Deferred: wraps the existing intro() as-is."""


def show():
	from utilities.fluff import intro
	intro()


if __name__ == "__main__":
	show()
