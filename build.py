#!/usr/bin/env python3
"""The Daily Twenty — builds site/index.html from the RSS feeds in feeds.json.

Standard library only (no pip installs), so it runs anywhere Python 3.9+ exists.
Run locally:  python3 build.py        -> writes site/index.html and data/latest.json
"""
import concurrent.futures as cf
import datetime as dt
import html
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.entities import name2codepoint

ROOT = pathlib.Path(__file__).resolve().parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 DailyTwenty/1.0")
NOW = dt.datetime.now(dt.timezone.utc)


# ---------- fetching ----------
def fetch(url, limit=3_000_000, timeout=20):
    if not re.match(r"https?://", url):          # local file (used for testing)
        return pathlib.Path(url).read_bytes()
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
        "Accept-Language": "en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit)


# ---------- parsing ----------
_ENTITY = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)([A-Za-z][A-Za-z0-9]*;)?")

def _fix_entities(text):
    def rep(m):
        name = m.group(1)
        if name and name[:-1] in name2codepoint:
            return "&#%d;" % name2codepoint[name[:-1]]
        return "&amp;" + (name or "")
    return _ENTITY.sub(rep, text)

def _decode(raw):
    head = raw[:200].decode("ascii", "ignore")
    m = re.search(r'encoding=["\']([\w.-]+)["\']', head)
    enc = m.group(1) if m else "utf-8"
    try:
        text = raw.decode(enc, "replace")
    except LookupError:
        text = raw.decode("utf-8", "replace")
    text = text.lstrip("﻿ \r\n\t")
    text = re.sub(r"^<\?xml[^>]*\?>", "", text)
    return text

def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""

def _kids(el, name):
    return [c for c in el if _local(c.tag) == name]

def _text(el, *names):
    for n in names:
        for c in _kids(el, n):
            t = "".join(c.itertext()).strip()
            if t:
                return t
    return ""

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)

def strip_html(s, limit=230):
    s = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", s or "", flags=re.I)
    s = re.sub(r"</?(?:b|i|em|strong|a|span|u|small|sup|sub|abbr|cite|code)\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:!?])", r"\1", s)
    s = re.sub(r"\s*(Continue reading|Read more|The post .* appeared first on .*)\.*$", "", s, flags=re.I)
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"
    return s

def _img_from_html(s):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', s or "", re.I)
    return html.unescape(m.group(1)) if m else ""

def pick_image(item):
    best, best_w = "", -1
    for c in item.iter():
        name = _local(c.tag)
        if name in ("content", "thumbnail") and c.get("url"):
            typ = (c.get("type") or c.get("medium") or "image").lower()
            if "image" not in typ and name == "content":
                continue
            w = int(c.get("width") or (600 if name == "content" else 300))
            if w > best_w:
                best, best_w = c.get("url"), w
        elif name == "enclosure" and c.get("url") and "image" in (c.get("type") or "image"):
            if best_w < 500:
                best, best_w = c.get("url"), 500
    if not best:
        for n in ("encoded", "content", "description", "summary"):
            for c in _kids(item, n):
                best = _img_from_html("".join(c.itertext()) or (c.text or ""))
                if best:
                    break
            if best:
                break
    return upgrade_image(best)

def upgrade_image(url):
    if not url:
        return ""
    url = html.unescape(url.strip())
    if url.startswith("//"):
        url = "https:" + url
    url = re.sub(r"(ichef\.bbci\.co\.uk/(?:ace/standard|news))/\d+/", r"\1/800/", url)
    return url if url.startswith(("http://", "https://")) else ""

def is_google(url):
    return "news.google." in urllib.parse.urlsplit(url).netloc

def parse_feed(raw, source, google=False):
    root = ET.fromstring(_fix_entities(_decode(raw)))
    out = []
    items = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    for it in items:
        title = strip_html(_text(it, "title"), 300)
        link = ""
        for l in _kids(it, "link"):
            if l.get("href") and (l.get("rel") in (None, "alternate")):
                link = l.get("href"); break
            if (l.text or "").strip():
                link = l.text.strip(); break
        if not link:
            g = _kids(it, "guid")
            if g and (g[0].text or "").startswith("http"):
                link = g[0].text.strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        date = parse_date(_text(it, "pubdate", "published", "updated", "date", "issued"))
        summary = strip_html(_text(it, "description", "summary") or _text(it, "encoded", "content"))
        item = {
            "source": source, "title": title, "link": link.replace("http://", "https://", 1),
            "date": date.isoformat() if date else None, "summary": summary,
            "image": pick_image(it),
        }
        if google:
            # Google News titles end in " - Publisher"; the real outlet is also in <source>
            pub = _text(it, "source")
            if pub and title.endswith(" - " + pub):
                title = title[: -len(pub) - 3].strip()
            elif " - " in title:
                title, tail = title.rsplit(" - ", 1)
                pub = pub or tail.strip()
            item.update(title=title, source=pub or "Google News", summary="Via Google News.",
                        image="", via="google")
        out.append(item)
    return out


# ---------- selection ----------
def norm_link(u):
    p = urllib.parse.urlsplit(u)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(("utm_", "traffic_source", "cmp", "ref"))]
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urllib.parse.urlencode(q), ""))

def norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:70]

def pub_key(name):
    name = re.sub(r"\b(the|news|online|english)\b", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)

def same_outlet(a, b):
    a, b = pub_key(a), pub_key(b)
    return len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a))

def select(items, n, per_source, seen, max_google=3, direct=()):
    fresh = []
    for hours in (36, 96, 24 * 30):
        fresh = [i for i in items if i["date"] and (NOW - dt.datetime.fromisoformat(i["date"])).total_seconds() < hours * 3600]
        if len(fresh) >= n:
            break
    if len(fresh) < n:
        fresh += [i for i in items if not i["date"]]
    fresh.sort(key=lambda i: i["date"] or "", reverse=True)
    by_source, google_used = {}, 0
    for i in fresh:
        k1, k2 = norm_link(i["link"]), norm_title(i["title"])
        if k1 in seen or k2 in seen:
            continue
        if i.get("via") == "google":
            # prefer the outlet's own feed (it has photos); keep Google to a few extra outlets
            if google_used >= max_google or any(same_outlet(i["source"], d) for d in direct):
                continue
        by_source.setdefault(i["source"], [])
        if len(by_source[i["source"]]) < per_source:
            by_source[i["source"]].append(i)
            seen.update((k1, k2))
            google_used += i.get("via") == "google"
    # round-robin so each row opens with a mix of newsrooms, newest first within each
    picked, queues = [], sorted(by_source.values(), key=lambda q: q[0]["date"] or "", reverse=True)
    while queues and len(picked) < n:
        for q in list(queues):
            if q:
                picked.append(q.pop(0))
                if len(picked) >= n:
                    break
            if not q:
                queues.remove(q)
    # stories with the outlet's own photo lead the row; Google News extras follow
    return [i for i in picked if i.get("via") != "google"] + [i for i in picked if i.get("via") == "google"]


def og_image(url):
    try:
        page = fetch(url, limit=400_000, timeout=10).decode("utf-8", "ignore")
    except Exception:
        return ""
    for pat in (r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, page, re.I)
        if m:
            return upgrade_image(urllib.parse.urljoin(url, html.unescape(m.group(1))))
    return ""


def read_schedule():
    """UTC [hour, minute] pairs from the workflow's cron lines, so the page can say when the next edition is due."""
    wf = next(ROOT.glob(".github/workflows/*.yml"), None) or next(ROOT.parent.glob(".github/workflows/*.yml"), None)
    if not wf:
        return []
    def expand(field, top):
        out = set()
        for part in field.split(","):
            if part == "*":
                out.update(range(top))
            elif part.startswith("*/"):
                out.update(range(0, top, int(part[2:])))
            elif "-" in part:
                a, b = map(int, part.split("-")); out.update(range(a, b + 1))
            else:
                out.add(int(part))
        return out
    times = set()
    for m in re.finditer(r'cron:\s*["\']([^"\']+)["\']', wf.read_text(encoding="utf-8")):
        f = m.group(1).split()
        if len(f) == 5 and f[2:] == ["*", "*", "*"]:
            try:
                times.update((h, mi) for h in expand(f[1], 24) for mi in expand(f[0], 60))
            except ValueError:
                pass
    return sorted([list(t) for t in times])


def main():
    cfg = json.loads((ROOT / os.environ.get("FEEDS_FILE", "feeds.json")).read_text(encoding="utf-8"))
    n, per_source = cfg.get("per_section", 12), cfg.get("max_per_source", 4)
    max_google = cfg.get("max_google_per_section", 3)
    direct = {s["id"]: [f["source"] for f in s["feeds"] if not is_google(f["url"])] for s in cfg["sections"]}
    jobs = [(s["id"], f) for s in cfg["sections"] for f in s["feeds"]]

    def load(job):
        sid, f = job
        try:
            return sid, f, parse_feed(fetch(f["url"]), f["source"], is_google(f["url"])), None
        except Exception as e:  # one broken feed never stops the edition
            return sid, f, [], f"{type(e).__name__}: {e}"[:160]

    raw = {s["id"]: [] for s in cfg["sections"]}
    report = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for sid, f, items, err in ex.map(load, jobs):
            raw[sid] += items
            report.append((f["source"], sid, len(items), err))

    for src, sid, count, err in sorted(report, key=lambda r: (r[1], r[0])):
        print(f"  {'OK ' if count else 'ERR'} {sid:9} {src:22} {count:3} items" + (f"   ({err})" if err else ""))

    seen, stories = set(), []
    # local sections claim their stories first, so a Malaysia story isn't used up by Business
    ids = [s["id"] for s in cfg["sections"]]
    order = [i for i in ("my", "sg") if i in ids] + [i for i in ids if i not in ("my", "sg")]
    for sid in order:
        for i in select(raw[sid], n, per_source, seen, max_google, direct[sid]):
            i["cat"] = sid
            stories.append(i)

    missing = [s for s in stories if not s["image"] and s.get("via") != "google"]
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for s, img in zip(missing, ex.map(lambda s: og_image(s["link"]), missing)):
            s["image"] = img

    if len(stories) < 6:
        sys.exit(f"Only {len(stories)} stories found — keeping yesterday's page instead of publishing an empty one.")

    sections = [{"id": s["id"], "name": s["name"]} for s in cfg["sections"]]
    payload = {
        "compiled": NOW.isoformat(),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "schedule": read_schedule(),
        "sections": sections,
        "stories": stories,
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    page = (ROOT / "template.html").read_text(encoding="utf-8").replace("__DATA__", blob)
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "index.html").write_text(page, encoding="utf-8")
    # tiny file the page's refresh button checks to see whether a newer edition exists
    (ROOT / "site" / "edition.json").write_text(json.dumps({"compiled": payload["compiled"], "stories": len(stories)}), encoding="utf-8")
    if (ROOT / "icons").is_dir():   # home screen and browser tab icons
        shutil.copytree(ROOT / "icons", ROOT / "site" / "icons", dirs_exist_ok=True)
    with_img = sum(1 for s in stories if s["image"])
    via_g = sum(1 for s in stories if s.get("via") == "google")
    print(f"Built site/index.html — {len(stories)} stories, {with_img} with photos, {via_g} via Google News.")


if __name__ == "__main__":
    main()
