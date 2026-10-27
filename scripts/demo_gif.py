#!/usr/bin/env python3
"""Regenerate the README demo: docs/images/builder-lens.gif plus the "What you get" screenshots.

Renders the made-up builder in dark mode, captures one 2x screenshot per state (hover, flip,
scroll position) with headless Chrome, then stitches them with ffmpeg crossfades. Needs Google
Chrome and ffmpeg; uses only made-up data.

    python3 scripts/demo_gif.py [--theme dark|light] [--frames DIR] [--width 1000]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

GO = ("function go(el,off){el=typeof el==='string'?document.querySelector(el):el;"
      "var y=el.getBoundingClientRect().top+scrollY+(off||0);"
      "document.querySelector('.frame').style.transform='translateY(-'+y+'px)';}")
# Hover and flip states, forced with classes so a static screenshot can show them.
CSS = """<style>
.why.force [role=tooltip]{opacity:1}
.card.lift{z-index:100;transform:rotate(0) translateY(-12px) scale(1.03);box-shadow:0 30px 50px -18px var(--shadow)}
.hrow.tipon::after{content:attr(data-tip);position:absolute;left:34%;bottom:calc(100% + 4px);z-index:50;width:min(340px,70vw);
padding:8px 10px;background:var(--card);color:var(--ink);border:1px solid var(--hair);box-shadow:0 14px 34px -16px var(--shadow);
font-size:13px;line-height:1.45;white-space:normal}.hrow.tipon{background:var(--grid)}
.flip{transition:none!important}.toc{position:static}
</style>"""
# (frame name, seconds on screen, script that sets the state)
SEQ = [
    ("01-hero", 2.2, ""),
    ("02-why-hover", 2.4, "document.querySelector('.verdict .why').classList.add('force');"),
    ("03-card-lift", 0.9, "document.querySelectorAll('.card')[1].classList.add('lift');"),
    ("04-card-flip", 2.2, "document.querySelectorAll('.card')[1].classList.add('lift','flipped');"),
    ("05-narrative", 2.0, "go('#narrative',-24);"),
    ("06-decisions", 2.4, "go('#decisions',-24);var r=document.querySelectorAll('#decisions .hrow[data-tip]');"
                          "r[r.length-6].classList.add('tipon');"),
    ("07-strengths", 2.4, "go('#strengths',-24);document.querySelector('#strengths .why').classList.add('force');"),
    ("08-growth", 2.0, "go('#growth',-24);"),
    ("09-quadrant", 2.6, "go('#ai',-24);"),
    ("10-axes", 2.2, "go('#axes',-24);document.querySelector('#axes .hrow').classList.add('tipon');"),
    ("11-skill", 3.2, "go('#skill',-24);"),
]
FADE, FPS = 0.35, 12
STILLS = [("04-card-flip", "card-flip"), ("06-decisions", "decisions"), ("09-quadrant", "quadrant"), ("11-skill", "skill")]


def capture(work, frames, theme):
    subprocess.run([sys.executable, os.path.join(ROOT, "builder_lens.py"), "--demo", "--no-open", "--out", work],
                   check=True, stdout=subprocess.DEVNULL)
    with open(os.path.join(work, "report.html"), encoding="utf-8") as fh:
        src = fh.read()
    profile = os.path.join(work, "chrome-profile")
    for name, _, js in SEQ:
        page = os.path.join(work, name + ".html")
        script = f"<script>{GO}document.documentElement.dataset.theme='{theme}';{js}</script>"
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(src.replace("</head>", CSS + "</head>").replace("</body>", script + "</body>"))
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1440,900",
                        "--force-device-scale-factor=2", "--virtual-time-budget=1500", f"--user-data-dir={profile}",
                        f"--screenshot={os.path.join(frames, name + '.png')}", "file://" + page],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stitch(frames, out, width):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for name, d, _ in SEQ:
        cmd += ["-loop", "1", "-t", f"{d + FADE:.2f}", "-i", os.path.join(frames, name + ".png")]
    f = [f"[{i}:v]scale={width}:-2:flags=lanczos,fps={FPS},format=rgb24,setsar=1[s{i}]" for i in range(len(SEQ))]
    prev, t = "s0", 0.0
    for i in range(1, len(SEQ)):
        t += SEQ[i - 1][1]
        f.append(f"[{prev}][s{i}]xfade=transition=fade:duration={FADE}:offset={t:.2f}[x{i}]")
        prev = f"x{i}"
    f.append(f"[{prev}]split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
             "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    subprocess.run(cmd + ["-filter_complex", ";".join(f), "-loop", "0", out], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frames", help="keep the 2x PNG frames in this folder")
    ap.add_argument("--width", type=int, default=1000)
    ap.add_argument("--theme", choices=("dark", "light"), default="dark")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "docs", "images"))
    args = ap.parse_args()
    for tool in (CHROME, "ffmpeg"):
        if not shutil.which(tool) and not os.path.exists(tool):
            sys.exit(f"needs {tool}")
    out = os.path.join(args.out_dir, "builder-lens.gif")
    with tempfile.TemporaryDirectory(prefix="builder-lens-gif-") as work:
        frames = args.frames or os.path.join(work, "frames")
        os.makedirs(frames, exist_ok=True)
        capture(work, frames, args.theme)
        stitch(frames, out, args.width)
        # the README's "What you get" grid, from the same frames
        for frame, name in STILLS:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(frames, frame + ".png"),
                            "-vf", "scale=1600:-2:flags=lanczos", os.path.join(args.out_dir, name + ".png")], check=True)
    print(f"{out} ({os.path.getsize(out) / 1e6:.1f} MB, {sum(d for _, d, _ in SEQ):.0f}s) and "
          f"{len(STILLS)} screenshots, {args.theme} theme")


if __name__ == "__main__":
    main()
