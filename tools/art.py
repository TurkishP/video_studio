"""Find and download public-domain artworks (The Met, Art Institute of Chicago, Wikimedia Commons).

Usage:
  python -I tools/art.py search "<query>" [--source met|aic|commons] [-n 8] [--sheet out.jpg]
  python -I tools/art.py get <key> shorts/<slug>/assets/<name>.jpg

`search` prints one candidate per line ("key | title | artist | date"); --sheet tiles
their thumbnails left to right in the same order so you can look before choosing.
`get` downloads the work (max 3000 px, sharp enough for close-up shots), and appends a credit row to the short's
provenance.csv.
"""
import argparse
import csv
import datetime
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_PX = 3000
UA = {"User-Agent": "shorts-studio/1.0 (local video tool)", "AIC-User-Agent": "shorts-studio/1.0"}


def fetch(url, attempts=5):
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == attempts - 1:
                raise
            # Wikimedia rate-limits bursts; wait as asked (or back off) and retry.
            time.sleep(int(e.headers.get("Retry-After") or 5 * (attempt + 1)))


def get_json(url, **params):
    return json.loads(fetch(url + "?" + urllib.parse.urlencode(params)))


def met_object(oid):
    o = get_json(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
    if not (o.get("isPublicDomain") and o.get("primaryImage")):
        return None
    return {"key": f"met:{oid}", "title": o["title"], "artist": o.get("artistDisplayName") or "Unknown",
            "date": o.get("objectDate", ""), "url": o["objectURL"], "license": "Public domain (CC0)",
            "image": o["primaryImage"], "thumb": o["primaryImageSmall"]}


def aic_item(a):
    if not a.get("image_id"):
        return None
    iiif = f"https://www.artic.edu/iiif/2/{a['image_id']}/full"
    return {"key": f"aic:{a['id']}", "title": a["title"], "artist": a.get("artist_display", "Unknown").split("\n")[0],
            "date": a.get("date_display", ""), "url": f"https://www.artic.edu/artworks/{a['id']}",
            "license": "Public domain (CC0)", "image": f"{iiif}/1686,/0/default.jpg", "thumb": f"{iiif}/300,/0/default.jpg"}


AIC_FIELDS = "id,title,artist_display,date_display,image_id"


def visible_text(html):
    """Commons metadata is HTML with hidden machine-readable parts; keep what a reader sees."""
    html = re.sub(r'<div style="display: none;">.*?</div>', "", html, flags=re.S)
    return re.sub(r"<[^>]+>", "", html).strip()


def commons_items(width, **query):
    data = get_json("https://commons.wikimedia.org/w/api.php", action="query", format="json",
                    prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=width,
                    iiextmetadatafilter="LicenseShortName|Artist|DateTimeOriginal", **query)
    items = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = page["imageinfo"][0]
        meta = {k: v["value"] for k, v in info.get("extmetadata", {}).items()}
        lic = meta.get("LicenseShortName", "")
        if not lic.lower().startswith(("public domain", "pd", "cc0")):
            continue
        items.append({"key": f"commons:{page['title']}", "title": Path(page["title"][5:]).stem,
                      "artist": visible_text(meta.get("Artist", "Unknown")),
                      "date": visible_text(meta.get("DateTimeOriginal", "")), "url": info["descriptionurl"],
                      "license": lic, "image": info["thumburl"], "thumb": info["thumburl"]})
    return items


def search(query, source, n):
    if source == "met":
        # v1/search was retired on 2026-10-01; v1.1 is paginated.
        ids = get_json("https://collectionapi.metmuseum.org/public/collection/v1.1/search",
                       hasImages="true", q=query, limit=n * 3).get("objectIDs") or []
        found = []
        for oid in ids[: n * 3]:
            if len(found) == n:
                break
            item = met_object(oid)
            if item:
                found.append(item)
        return found
    if source == "aic":
        data = get_json("https://api.artic.edu/api/v1/artworks/search", q=query, limit=n * 2,
                        fields=AIC_FIELDS, **{"query[term][is_public_domain]": "true"})
        return [i for i in map(aic_item, data["data"]) if i][:n]
    return commons_items(300, generator="search", gsrsearch=f"{query} filetype:bitmap",
                         gsrnamespace=6, gsrlimit=n * 2)[:n]


def lookup(key):
    source, ident = key.split(":", 1)
    if source == "met":
        return met_object(ident)
    if source == "aic":
        a = get_json(f"https://api.artic.edu/api/v1/artworks/{ident}", fields=AIC_FIELDS)["data"]
        return aic_item(a)
    items = commons_items(MAX_PX, titles=ident)
    return items[0] if items else None


def shrink(src, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    f"scale='min({MAX_PX},iw)':'min({MAX_PX},ih)':force_original_aspect_ratio=decrease",
                    "-q:v", "2", str(dest)], check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # titles have dashes/accents; the Korean console is cp949
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--source", choices=["met", "aic", "commons"], default="aic")
    s.add_argument("-n", type=int, default=8)
    s.add_argument("--sheet")
    g = sub.add_parser("get")
    g.add_argument("key")
    g.add_argument("dest")
    args = p.parse_args()

    if args.cmd == "search":
        items = search(args.query, args.source, args.n)
        for i in items:
            print(f"{i['key']} | {i['title']} | {i['artist']} | {i['date']}")
        if args.sheet and items:
            with tempfile.TemporaryDirectory() as tmp:
                inputs, filters = [], []
                for k, item in enumerate(items):
                    path = Path(tmp) / f"{k}.jpg"
                    path.write_bytes(fetch(item["thumb"]))
                    inputs += ["-i", str(path)]
                    filters.append(f"[{k}]scale=240:300:force_original_aspect_ratio=decrease,"
                                   f"pad=240:300:(ow-iw)/2:(oh-ih)/2[v{k}]")
                stack = "".join(f"[v{k}]" for k in range(len(items)))
                graph = ";".join(filters) + (f";{stack}hstack={len(items)}" if len(items) > 1 else "")
                subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph,
                                "-frames:v", "1", args.sheet], check=True)
        return

    item = lookup(args.key)
    if not item:
        sys.exit(f"{args.key}: not found or not public domain")
    dest = Path(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw"
        raw.write_bytes(fetch(item["image"]))
        shrink(raw, dest)
    folder = dest.parent.parent
    log = folder / "provenance.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file", "source_url", "creator", "license", "retrieved"])
        w.writerow([dest.relative_to(folder).as_posix(), item["url"],
                    f"{item['artist']}, {item['title']} ({item['date']})".strip(), item["license"],
                    datetime.date.today().isoformat()])
    print(f"{dest}: {item['title']} — {item['artist']}")


main()
