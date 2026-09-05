#!/usr/bin/env python3
"""Dancing Chlamydomonas reinhardtii — ASCII terminal art, 6 s seamless loop.

Port of the HTML animation. Pure standard library, 24-bit ANSI colour.

    python3 chlamy_dance.py                 # loop in the terminal until Ctrl-C
    python3 chlamy_dance.py --loops 3       # play three times and exit
    python3 chlamy_dance.py --fps 24
    python3 chlamy_dance.py --no-color
    python3 chlamy_dance.py --dump-frame 2.3   # print one frame at t=2.3 s
    python3 chlamy_dance.py --dump-all out/    # write every frame as .txt (plain)
"""

import argparse
import math
import os
import shutil
import sys
import time

# ---------------------------------------------------------------- geometry ---
SCALE = 0.5            # linear scale of the whole drawing; W, H, and every
                        # length-like quantity below (rx, ry, flagellum
                        # length, eyespot size) scale with this. Angles
                        # (spread, curl, wave, lean) are shape parameters,
                        # not distances, and are deliberately left alone.
## Forced even: cx = W/2 must be a whole number. The original 78 is even for
## exactly this reason -- an odd W gives a half-integer center, and Python's
## round() (round-half-to-even) then collides two adjacent x offsets onto
## the same grid column, leaving the other one's column unpainted. Confirmed
## empirically: SCALE=0.5 gives W=39 (odd) and visible gaps in the body fill;
## forcing W=40 (even) removes them.
W = 2 * round(78 * SCALE / 2)
H = 2 * round(36 * SCALE / 2)   # character grid
YS = 2                 # one row is about two column-widths tall
DURATION = 6.0         # seconds, seamless loop

INK = (243, 242, 242)      # white cell rim
GREEN = (61, 220, 107)     # cell body
DEEP = (31, 156, 74)       # body edge shading
EYE = (255, 255, 255)      # eyespot
CIL = (255, 255, 255)      # flagella (cilia)
FRAME = (92, 89, 87)       # terminal frame


# ------------------------------------------------------------------ easing ---
def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def ease_in_out_sine(t):
    return -(math.cos(math.pi * t) - 1) / 2


def glide(frm, to, start, end):
    """animate({from,to,start,end,ease:easeInOutSine}) — returns f(t)."""
    def f(t):
        if t <= start:
            return frm
        if t >= end:
            return to
        return frm + (to - frm) * ease_in_out_sine((t - start) / (end - start))
    return f


def snap(t, per):
    """Mechanical quantisation: `per` snaps per second."""
    return math.floor(t * per) / per


# -------------------------------------------------------------------- grid ---
class Grid:
    def __init__(self):
        self.ch = [[' '] * W for _ in range(H)]
        self.co = [[None] * W for _ in range(H)]

    def put(self, x, y, c, color):
        xi, yi = round(x), round(y)
        if xi < 1 or xi > W - 2 or yi < 1 or yi > H - 2:
            return
        self.ch[yi][xi] = c
        self.co[yi][xi] = color


def slope_glyph(dx, dy):
    a = math.atan2(dy * YS, dx)
    d = abs(a)
    if d < 0.39 or d > math.pi - 0.39:
        return '-'
    if abs(d - math.pi / 2) < 0.39:
        return '|'
    if a > 0:
        return '\\' if a < math.pi / 2 else '/'
    return '/' if a > -math.pi / 2 else '\\'


# ---------------------------------------------------------------- the cell ---
def draw_body(g, cx, cy, rx, ry, scale=1.0):
    """Solid green block body, solid white rim, solid white eyespot."""
    for y in range(-math.ceil(ry) - 1, math.ceil(ry) + 2):
        for x in range(-math.ceil(rx) - 1, math.ceil(rx) + 2):
            d = math.hypot(x / rx, y / ry)
            if d > 1.0:
                continue
            g.put(cx + x, cy + y, '█', DEEP if d > 0.8 else GREEN)

    for i in range(420):
        a = (i / 420) * math.pi * 2
        g.put(cx + rx * math.cos(a) * 1.02, cy + ry * math.sin(a) * 1.02, '█', INK)

    # Eyespot extent is in whole character cells, so it doesn't scale for
    # free the way rx/ry (continuous) do -- scaled explicitly here.
    # scale=1.0 reproduces the original range(-2,3)/(-1,0,1)/2.2/1.1 exactly.
    ex, ey = cx + rx * 0.5, cy - ry * 0.3
    eye_w, eye_h = max(1, round(2 * scale)), max(0, round(1 * scale))
    for y in range(-eye_h, eye_h + 1):
        for x in range(-eye_w, eye_w + 1):
            if math.hypot(x / (eye_w + 0.2), y / (eye_h + 0.1)) > 1:
                continue
            g.put(ex + x, ey + y, '█', EYE)


def draw_flagellum(g, bx, by, h0, curl, length, wave, phase):
    x, y, last = bx, by, ''
    N = 96
    ds = length / N
    for i in range(N + 1):
        f = i / N
        h = h0 + curl * f * f + wave * math.sin(f * math.pi * 1.7 + phase) * f
        dx, dy = math.cos(h) * ds, math.sin(h) * ds / YS
        key = f'{round(x)},{round(y)}'
        if key != last:
            g.put(x, y, '.' if f > 0.92 else slope_glyph(dx, dy), CIL)
            last = key
        x += dx
        y += dy


def frame(T):
    """The whole animation as a pure function of authored time (0..6 s)."""
    g = Grid()
    cx, cy, rx, ry = W / 2, H / 2 + 1, 6.4 * SCALE, 8.6 * SCALE

    beat = snap(T, 8)                        # eight snaps a second
    stroke = math.sin(beat * math.pi * 4)    # two beats a second
    phase = beat * math.pi * 4
    band_y = cy - ry * 0.92

    spread, length, curl, wave, lean = 0.34, 12.5, 1.5, 0.5, 0.0

    if T < 1.5:                              # Bob — symmetric breaststroke
        spread = 0.32 + abs(stroke) * 0.3
        length = 12.5 + stroke * 2.2
        curl = 1.45 + stroke * 1.35
    elif T < 3.0:                            # Hop — sweeps side to side
        k = math.floor((T - 1.5) / 0.375)
        local = ((T - 1.5) % 0.375) / 0.375
        direction = 1 if k % 2 == 0 else -1
        lean = direction * glide(-0.4, 0.4, 0, 0.65)(local)
        spread = 0.3 + abs(stroke) * 0.24
        length, curl, wave = 13.5, 1.35, 0.55
    elif T < 4.5:                            # Spin — a rolling whip
        p = (T - 3.0) / 1.5
        spread = 0.3 + math.sin(p * math.pi * 4) * 0.3
        lean = math.sin(p * math.pi * 4) * 0.36
        length = 14 + math.sin(p * math.pi * 8) * 1.6
        curl = 2.1 + math.cos(p * math.pi * 4) * 1.1
        wave = 0.85
    else:                                    # Freeze — flare, shiver, return
        p = (T - 4.5) / 1.5
        shiver = ((1 if round(beat * 8) % 2 else -1) * (1 - p) * 0.12) if p < 0.7 else 0
        spread = glide(0.78, 0.32, 0.45, 1)(p) + shiver
        length = glide(15.5, 12.5, 0.45, 1)(p)
        curl = glide(2.6, 1.45, 0.45, 1)(p)
        wave = glide(0.9, 0.5, 0.45, 1)(p)

    length *= SCALE  # curl/wave/spread/lean are angles, not distances -- left alone

    for side in (-1, 1):
        # keep every flagellum in the upward fan: no tip swings below its base
        h0 = clamp(-math.pi / 2 + side * (0.2 + spread) + lean, -math.pi + 0.55, -0.55)
        room = (-0.3 - h0) if side > 0 else (h0 + math.pi - 0.3)
        draw_flagellum(g, cx + side * rx * 0.5, band_y, h0,
                       side * clamp(curl, 0.4, max(0.4, room)),
                       length, side * wave, phase * 0.5)

    draw_body(g, cx, cy, rx, ry, scale=SCALE)

    for x in range(W):
        g.ch[0][x] = g.ch[H - 1][x] = '─'
        g.co[0][x] = g.co[H - 1][x] = FRAME
    for y in range(H):
        g.ch[y][0] = g.ch[y][W - 1] = '│'
        g.co[y][0] = g.co[y][W - 1] = FRAME
    g.ch[0][0], g.ch[0][W - 1] = '┌', '┐'
    g.ch[H - 1][0], g.ch[H - 1][W - 1] = '└', '┘'
    return g


# ------------------------------------------------------------------ output ---
def render(g, color=True):
    """Grid -> a printable string, colour runs collapsed into one escape each."""
    out = []
    for y in range(H):
        if not color:
            out.append(''.join(g.ch[y]))
            continue
        line, cur = [], None
        for x in range(W):
            c = g.co[y][x] or FRAME
            if c != cur:
                line.append('\x1b[38;2;%d;%d;%dm' % c)
                cur = c
            line.append(g.ch[y][x])
        line.append('\x1b[0m')
        out.append(''.join(line))
    return '\n'.join(out)


def play(fps, loops, color):
    delay = 1.0 / fps
    total = None if loops is None else loops
    sys.stdout.write('\x1b[?25l')          # hide cursor
    n = 0
    try:
        while total is None or n < total:
            t0 = time.time()
            while True:
                T = time.time() - t0
                if T >= DURATION:
                    break
                sys.stdout.write('\x1b[H' + render(frame(T), color) + '\n')
                sys.stdout.flush()
                time.sleep(max(0.0, delay - (time.time() - t0 - T)))
            n += 1
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write('\x1b[?25h\x1b[0m\n')   # show cursor
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fps', type=float, default=30.0)
    ap.add_argument('--loops', type=int, default=None, help='default: forever')
    ap.add_argument('--no-color', action='store_true')
    ap.add_argument('--dump-frame', type=float, metavar='T',
                    help='print the frame at T seconds and exit')
    ap.add_argument('--dump-all', metavar='DIR',
                    help='write every frame at --fps as plain .txt files')
    a = ap.parse_args()
    color = not a.no_color

    if a.dump_frame is not None:
        print(render(frame(a.dump_frame % DURATION), color))
        return

    if a.dump_all:
        os.makedirs(a.dump_all, exist_ok=True)
        count = int(DURATION * a.fps)
        for i in range(count):
            txt = render(frame(i / a.fps), color=False)
            with open(os.path.join(a.dump_all, 'frame_%04d.txt' % i), 'w') as fh:
                fh.write(txt + '\n')
        print('wrote %d frames (%dx%d) to %s' % (count, W, H, a.dump_all))
        return

    cols, rows = shutil.get_terminal_size((W, H + 1))
    if cols < W or rows < H + 1:
        print('terminal is %dx%d; needs at least %dx%d' % (cols, rows, W, H + 1),
              file=sys.stderr)
    sys.stdout.write('\x1b[2J')
    play(a.fps, a.loops, color)


if __name__ == '__main__':
    main()
