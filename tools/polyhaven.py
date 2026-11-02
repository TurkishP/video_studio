"""Find and download CC0 3D models and HDRIs from Poly Haven for Blender scenes.

Usage:
  python -I tools/polyhaven.py search "<words>" [--type models|hdris] [-n 8] [--sheet out.jpg]
  python -I tools/polyhaven.py get <id> [--res 2k] [--log shorts/<slug>]

Assets land in tools/blender-assets/<id>/ and are shared by every video; scene
scripts load them with lib.model("<id>") and lib.hdri("<id>"). Models come as
.blend files, so their glass, alpha and metal materials survive intact. --log
appends a credit row to that video's provenance.csv. Poly Haven's API terms ask
every request to name the tool, hence the User-Agent.
"""
import argparse
import csv
import datetime
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com"
UA = {"User-Agent": "shorts-studio/1.0 (local video tool)"}
ASSETS = Path(__file__).parent / "blender-assets"


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def get_json(path):
    return json.loads(fetch(API + path))


def download(url, dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fetch(url))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--type", choices=["models", "hdris"], default="models")
    s.add_argument("-n", type=int, default=8)
    s.add_argument("--sheet")
    g = sub.add_parser("get")
    g.add_argument("id")
    g.add_argument("--res", default="2k")
    g.add_argument("--log")
    args = p.parse_args()

    if args.cmd == "search":
        words = args.query.lower().split()
        hits = []
        for key, a in get_json(f"/assets?t={args.type}").items():
            text = " ".join([key, a["name"], *a.get("tags", []), *a.get("categories", [])]).lower()
            score = sum(w in text for w in words)
            if score:
                hits.append((score, a.get("download_count", 0), key, a))
        hits.sort(key=lambda h: (-h[0], -h[1]))
        hits = hits[: args.n]
        for _, _, key, a in hits:
            print(f"{key} | {a['name']} | {', '.join(a.get('categories', []))}")
        if args.sheet and hits:
            with tempfile.TemporaryDirectory() as tmp:
                inputs, filters = [], []
                for k, (_, _, key, _) in enumerate(hits):
                    path = Path(tmp) / f"{k}.png"
                    path.write_bytes(fetch(f"https://cdn.polyhaven.com/asset_img/thumbs/{key}.png?width=256"))
                    inputs += ["-i", str(path)]
                    filters.append(f"[{k}]scale=256:256:force_original_aspect_ratio=decrease,"
                                   f"pad=256:256:(ow-iw)/2:(oh-ih)/2:color=gray[v{k}]")
                stack = "".join(f"[v{k}]" for k in range(len(hits)))
                graph = ";".join(filters) + (f";{stack}hstack={len(hits)}" if len(hits) > 1 else "")
                subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph,
                                "-frames:v", "1", args.sheet], check=True)
        return

    files = get_json(f"/files/{args.id}")
    info = get_json(f"/info/{args.id}")
    folder = ASSETS / args.id
    if "hdri" in files:
        item = files["hdri"][args.res]["hdr"]
        dest = folder / f"{args.id}_{args.res}.hdr"
        download(item["url"], dest)
    else:
        item = files["blend"][args.res]["blend"]
        dest = folder / f"{args.id}_{args.res}.blend"
        download(item["url"], dest)
        for rel, extra in item.get("include", {}).items():
            download(extra["url"], folder / rel)
    print(f"{dest}: {info['name']} by {', '.join(info.get('authors', {}))}")

    if args.log:
        log = Path(args.log) / "provenance.csv"
        new = not log.exists()
        with log.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["file", "source_url", "creator", "license", "retrieved"])
            w.writerow([f"3D: {args.id}", f"https://polyhaven.com/a/{args.id}",
                        f"{', '.join(info.get('authors', {}))}, {info['name']} (Poly Haven)", "CC0",
                        datetime.date.today().isoformat()])


main()
