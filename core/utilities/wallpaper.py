"""
AI Generated -- rewritten by Claude (Anthropic), 2026-09, replacing the
earlier Rich/SVG generator described below with this Pillow-based one.

Desktop wallpaper generation: a glanceable "which device is this, what's it
running, what's declared" panel, rendered as a PNG matching the real
screen's own resolution and (optionally) applied as the actual OS desktop
background.

Replaces the earlier Rich/SVG-based version, whose layout came from
whatever terminal happened to invoke it -- legible or illegible purely by
luck of console size. This one is pinned to the display it will actually
be shown on (via _screen_size()) rather than a hardcoded guess like
1920x1080 -- a fixed guess has the same failure mode as the terminal-size
bug it replaced: a non-16:9 screen (e.g. a MacBook's 16:10 panel) would
force the OS to stretch/distort a mismatched image to fill it.

Deliberately left out, per design discussion: uptime (meaningless for
something regenerated at most once a day/run) and "currently connected"
devices (can't be established reliably at generation time). The *declared*
device tree (config["devices"]'s top-level keys) is shown instead, since
reading config is always available.

Font: DejaVu Sans Mono, bundled with matplotlib (already a project
dependency) rather than vendoring font files into this repo or assuming
one is installed system-wide.
"""

import ctypes
import os
import platform
import shutil
import socket
import subprocess
from datetime import datetime

import git
import matplotlib
from PIL import Image, ImageDraw, ImageFont

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share

REFERENCE_H = 1080  # the height every literal pixel constant below was tuned against

BG = (15, 20, 25, 255)         # matches docs/assets/trappyscopes.png's own baked-in background
ACCENT = (94, 201, 179, 255)   # teal, matches trappyscopes.png's letter color
FG = (232, 230, 222, 255)
DIM = (74, 86, 81, 255)
TICK = (74, 90, 85, 255)
DIVIDER = (32, 36, 34, 255)

## AI Generated -- one more dirname() than before: this file moved from
## utilities/wallpaper.py to core/utilities/wallpaper.py (one directory
## deeper), so getting back to the repo root needs an extra step up. The
## old two-dirname version silently resolved to core/docs/assets/ instead
## of docs/assets/ after the move -- caught via a real crash, not review.
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "white_logo.png")
WORDMARK_PATH = os.path.join(ASSETS_DIR, "trappyscopes.png")

def_wallpaper_path = os.path.join(os.path.expanduser("~"), "trappyverse", "wallpaper.png")


def _font(name, size):
	fontdir = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
	return ImageFont.truetype(os.path.join(fontdir, name), size)


def _screen_size(default=(1920, 1080)):
	"""The real display's resolution -- tkinter is stdlib and works
	headlessly-attached (a Pi with a monitor plugged in included) as long
	as a display is actually reachable; falls back to `default` (e.g. no
	DISPLAY/Aqua session, or running in CI) rather than raising."""
	try:
		import tkinter
		root = tkinter.Tk()
		root.withdraw()
		size = (root.winfo_screenwidth(), root.winfo_screenheight())
		root.destroy()
		return size
	except Exception:
		return default


def _local_ip():
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(("8.8.8.8", 80))
		return s.getsockname()[0]
	except OSError:
		return "unknown"
	finally:
		s.close()


def _disk_free_gb():
	return shutil.disk_usage(os.path.expanduser("~")).free / (1024 ** 3)


def _commit_id():
	try:
		return git.Repo(Share.scopecli_fullpath).head.commit.hexsha[:7]
	except Exception:
		return "unknown"


def _config_name():
	loaded_from = getattr(TrappyConfig.current, "loaded_from", None)
	if loaded_from:
		return os.path.basename(loaded_from)
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			return os.path.basename(candidate)
	return "unknown"


def generate_wallpaper(info, out_path=None, screen_size=None):
	"""
	Render the scope-identification wallpaper from `info` (a materialised
	TrappyConfig dict -- freestyle.py passes the whole config) to
	`out_path` (default: ~/trappyverse/wallpaper.png). Returns the path
	written.

	`screen_size` defaults to the real display's own resolution
	(_screen_size()) -- every literal pixel constant below was tuned
	against a 1080px-tall reference design and is scaled by
	actual_height/1080, so the output always matches the real screen's
	aspect ratio exactly rather than assuming 16:9.
	"""
	out_path = out_path or def_wallpaper_path
	os.makedirs(os.path.dirname(out_path), exist_ok=True)

	W, H = screen_size or _screen_size()
	scale = H / REFERENCE_H

	def s(px):
		return int(round(px * scale))

	f_scopeid = _font("DejaVuSansMono-Bold.ttf", s(96))
	f_label = _font("DejaVuSansMono-Bold.ttf", s(26))
	f_value = _font("DejaVuSansMono.ttf", s(28))
	f_tree = _font("DejaVuSansMono.ttf", s(26))
	f_small = _font("DejaVuSansMono.ttf", s(19))

	img = Image.new("RGBA", (W, H), BG)
	draw = ImageDraw.Draw(img)

	## corner tick marks
	pad, tick = s(40), s(22)
	for x, y, dx, dy in [(pad, pad, 1, 1), (W - pad, pad, -1, 1),
						  (pad, H - pad, 1, -1), (W - pad, H - pad, -1, -1)]:
		draw.line([(x, y), (x + dx * tick, y)], fill=TICK, width=2)
		draw.line([(x, y), (x, y + dy * tick)], fill=TICK, width=2)

	## left column: logo + wordmark
	col_w = int(W * 0.34)
	logo = Image.open(LOGO_PATH).convert("RGBA")
	logo_w = int(col_w * 0.28)
	logo = logo.resize((logo_w, int(logo.height * logo_w / logo.width)))

	wordmark = Image.open(WORDMARK_PATH).convert("RGBA")
	word_w = int(col_w * 0.92)
	wordmark = wordmark.resize((word_w, int(wordmark.height * word_w / wordmark.width)))

	gap = s(40)
	block_h = logo.height + gap + wordmark.height
	block_y = (H - block_h) // 2
	img.alpha_composite(logo, ((col_w - logo.width) // 2, block_y))
	img.alpha_composite(wordmark, ((col_w - wordmark.width) // 2, block_y + logo.height + gap))

	draw.line([(col_w, s(100)), (col_w, H - s(100))], fill=DIVIDER, width=2)

	## right side: scope id, then two independent columns (info / devices)
	rx = col_w + int(W * 0.05)
	ry = int(H * 0.28)

	scope_id = info.get("name") or "unnamed"
	draw.text((rx, ry), str(scope_id), font=f_scopeid, fill=FG)
	ry += s(138)
	draw.line([(rx, ry), (W - pad - s(20), ry)], fill=DIVIDER, width=2)
	ry += s(40)

	info_top = ry
	rows = [
		("instrument", info.get("type") or "unknown"),
		("version", _commit_id()),
		("host", socket.gethostname()),
		("ip", _local_ip()),
		("disk", f"{_disk_free_gb():.1f} GB free"),
	]
	label_w = s(220)
	for label, value in rows:
		draw.text((rx, ry), label, font=f_label, fill=ACCENT)
		draw.text((rx + label_w, ry), str(value), font=f_value, fill=FG)
		ry += s(52)

	ry += s(40)
	draw.text((rx, ry), f"config · {_config_name()}", font=f_small, fill=DIM)

	## devices: declared, top-level only, in their own column so a long
	## tree never disturbs the info block or the config line
	devices = list((info.get("devices") or {}).keys())
	tree_x = rx + s(560)
	tree_y = info_top
	draw.text((tree_x, tree_y), "devices", font=f_label, fill=ACCENT)
	tree_y += s(44)
	for i, dev in enumerate(devices):
		branch = "`--" if i == len(devices) - 1 else "|--"
		draw.text((tree_x + s(20), tree_y), f"{branch} {dev}", font=f_tree, fill=FG)
		tree_y += s(40)

	stamp = f"generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
	stamp_w = draw.textbbox((0, 0), stamp, font=f_small)[2]
	draw.text((W - pad - s(20) - stamp_w, H - pad - s(30)), stamp, font=f_small, fill=DIM)

	img.convert("RGB").save(out_path)
	return out_path


def set_wallpaper(path):
	"""
	Apply `path` as the actual OS desktop background. Best-effort across
	macOS, Linux (GNOME via gsettings, else LXDE/Raspberry Pi OS via
	pcmanfm), and Windows. Returns True if a mechanism ran successfully,
	False if nothing applicable was found for this platform/desktop.
	"""
	path = os.path.abspath(os.path.expanduser(path))
	system = platform.system()

	if system == "Darwin":
		script = f'tell application "System Events" to tell every desktop to set picture to "{path}"'
		return subprocess.run(["osascript", "-e", script]).returncode == 0

	if system == "Linux":
		if shutil.which("gsettings"):
			uri = f"file://{path}"
			ok = subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
								  "picture-uri", uri]).returncode == 0
			subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
							 "picture-uri-dark", uri])
			return ok
		if shutil.which("pcmanfm"):
			return subprocess.run(["pcmanfm", "--wallpaper-mode=fit",
									f"--set-wallpaper={path}"]).returncode == 0
		return False

	if system == "Windows":
		SPI_SETDESKWALLPAPER = 20
		SPIF_UPDATEINIFILE_SENDCHANGE = 3
		return bool(ctypes.windll.user32.SystemParametersInfoW(
			SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE_SENDCHANGE))

	return False


if __name__ == "__main__":
	generate_wallpaper(TrappyConfig().get())
