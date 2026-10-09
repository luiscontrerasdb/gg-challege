#!/usr/bin/env python3
"""
gg2zd - Migrate Confluence knowledge articles (GG8-00002, ...) to Zendesk Guide.

  python gg2zd.py --read-from GG8-00002,GG8-00003
  python gg2zd.py --zendesk-preview GG8-00002,GG8-00003
  python gg2zd.py --migrate-to-zendesk GG8-00002,GG8-00003,GG8-00018

Articles can be given as GG IDs, full/partial titles, or Confluence page URLs, separated by commas.
Configuration: environment variables or a .env file (see .env.example). Only needs the Python standard
library; `pip install pygments` is optional (adds syntax colors to code blocks).
"""
import argparse, base64, csv, datetime as dt, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, webbrowser
from pathlib import Path

try:
    from pygments import highlight as _pyg_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
    HAVE_PYGMENTS = True
except ImportError:
    HAVE_PYGMENTS = False

HERE = Path(__file__).resolve().parent

# ----------------------------------------------------------------------------- config
def load_config():
    env = {}
    for p in (Path.cwd() / ".env", HERE / ".env"):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    env.update({k: v for k, v in os.environ.items() if k in KEYS})
    return env

KEYS = ["ATLASSIAN_SITE", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN", "CONFLUENCE_SPACE",
        "ZENDESK_SUBDOMAIN", "ZENDESK_BASE_URL", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN",
        "ZENDESK_SECTION_ID", "ZENDESK_PERMISSION_GROUP_ID", "ZENDESK_USER_SEGMENT_ID", "ZENDESK_LOCALE"]

def need(cfg, *names):
    missing = [n for n in names if not cfg.get(n)]
    if missing:
        sys.exit("Missing configuration: " + ", ".join(missing) + "  (set them in .env or as environment variables)")

# ----------------------------------------------------------------------------- http
def http(method, url, auth, body=None, retries=3):
    headers = {"Authorization": "Basic " + base64.b64encode(auth.encode()).decode(), "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(int(e.headers.get("Retry-After", "5"))); continue
            detail = e.read().decode(errors="replace")[:400]
            raise RuntimeError(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")

# ----------------------------------------------------------------------------- confluence
def conf_auth(cfg): return f"{cfg['ATLASSIAN_EMAIL']}:{cfg['ATLASSIAN_API_TOKEN']}"
def conf_base(cfg): return cfg["ATLASSIAN_SITE"].rstrip("/") + "/wiki"

def split_refs(tokens):
    """'GG8-1, GG8-2' or 'GG8-1 GG8-2' or 'Some title, Other title' -> list of references."""
    refs = []
    for piece in " ".join(tokens).split(","):
        piece = piece.strip()
        if not piece: continue
        ids = piece.split()
        if len(ids) > 1 and all(re.fullmatch(r"GG0*\d+-\d+", i, re.I) for i in ids): refs += ids
        else: refs.append(piece)
    return refs

def normalize_id(ref):
    m = re.fullmatch(r"GG0*(\d+)-(\d+)", ref.strip(), re.I)
    return f"GG{int(m.group(1))}-{m.group(2)}" if m else None

def slugify(title):
    m = re.match(r"(GG\d+-\d+)", title)
    return m.group(1) if m else re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:60].lower()

def cql_search(cfg, text, exact=False):
    t = text.replace("\\", "\\\\").replace('"', '\\"')
    cql = f'type = page AND title {"=" if exact else "~"} "{t}"'
    if cfg.get("CONFLUENCE_SPACE"): cql += f' AND space = "{cfg["CONFLUENCE_SPACE"]}"'
    url = f"{conf_base(cfg)}/rest/api/content/search?" + urllib.parse.urlencode({"cql": cql, "limit": 25})
    return http("GET", url, conf_auth(cfg)).get("results", [])

def resolve(cfg, ref):
    """-> dict(ref, status in OK|NOT FOUND|AMBIGUOUS|ERROR, page_id, title, matches, message)"""
    out = {"ref": ref, "status": "NOT FOUND", "page_id": None, "title": None, "matches": [], "message": ""}
    try:
        m = re.search(r"/pages/(\d+)", ref)
        if m:
            out.update(page_id=m.group(1), status="OK")
            out["title"] = http("GET", f"{conf_base(cfg)}/rest/api/content/{m.group(1)}", conf_auth(cfg))["title"]
            return out
        gid = normalize_id(ref)
        if gid:
            hits = [r for r in cql_search(cfg, gid)
                    if r["title"].upper().startswith(gid + ":") or r["title"].upper() == gid or r["title"].upper().startswith(gid + " ")]
        else:
            hits = [r for r in cql_search(cfg, ref, exact=True)] or \
                   [r for r in cql_search(cfg, ref) if ref.lower() in r["title"].lower()]
        out["matches"] = [h["title"] for h in hits]
        if len(hits) == 1:
            out.update(status="OK", page_id=hits[0]["id"], title=hits[0]["title"])
        elif len(hits) > 1:
            out.update(status="AMBIGUOUS", message="matches: " + " | ".join(out["matches"]))
    except Exception as e:
        out.update(status="ERROR", message=str(e))
    return out

def fetch_page(cfg, page_id):
    d = http("GET", f"{conf_base(cfg)}/rest/api/content/{page_id}?expand=body.storage,version", conf_auth(cfg))
    return {"id": d["id"], "title": d["title"], "storage": d["body"]["storage"]["value"],
            "version": d.get("version", {}).get("number"), "modified": d.get("version", {}).get("when")}

# ----------------------------------------------------------------------------- conversion
DROP_PANEL_PATTERNS = [r"Migrated from the GridGain Confluence review queue"]

def storage_to_html(s, title, warnings, keep_migration_note=False):
    def code(m):
        block = m.group(0)
        lang = re.search(r'<ac:parameter ac:name="language">([^<]*)</ac:parameter>', block)
        text = re.search(r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>", block, re.S)
        lang = (lang.group(1).strip().lower() if lang else "none") or "none"
        return f'<pre><code class="language-{lang}">{html.escape(text.group(1) if text else "", quote=False)}</code></pre>'
    s = re.sub(r'<ac:structured-macro\b[^>]*\bac:name="code"[^>]*>.*?</ac:structured-macro>', code, s, flags=re.S)

    labels = {"info": "Note", "note": "Note", "warning": "Warning", "tip": "Tip"}
    def panel(m):
        name, inner = m.group(1), m.group(2)
        if not keep_migration_note and any(re.search(p, inner) for p in DROP_PANEL_PATTERNS):
            warnings.append("Removed internal migration note panel"); return ""
        return f"<blockquote><p><strong>{labels[name]}:</strong></p>{inner}</blockquote>"
    s = re.sub(r'<ac:structured-macro\b[^>]*\bac:name="(info|note|warning|tip)"[^>]*>\s*(?:<ac:parameter[^>]*>.*?</ac:parameter>\s*)*<ac:rich-text-body>(.*?)</ac:rich-text-body>\s*</ac:structured-macro>',
               panel, s, flags=re.S)

    def img(m):
        warnings.append("Image/attachment not migrated: " + (re.search(r'ri:filename="([^"]*)"', m.group(0)) or [None, "(external)"])[1]); return ""
    s = re.sub(r"<ac:image\b.*?</ac:image>", img, s, flags=re.S)

    def link(m):
        b = re.search(r"<ac:(?:plain-text-)?link-body>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</ac:(?:plain-text-)?link-body>", m.group(0), re.S)
        t = re.search(r'ri:content-title="([^"]*)"', m.group(0))
        return b.group(1) if b else (html.escape(t.group(1)) if t else "")
    s = re.sub(r"<ac:link\b.*?</ac:link>", link, s, flags=re.S)

    def other_macro(m):
        warnings.append(f"Macro not supported, removed/unwrapped: {m.group(1)}"); return m.group(2) or ""
    s = re.sub(r'<ac:structured-macro\b[^>]*\bac:name="([^"]*)"[^>]*?(?:/>|>(?:<ac:parameter.*?</ac:parameter>)*(?:<ac:rich-text-body>(.*?)</ac:rich-text-body>)?.*?</ac:structured-macro>)',
               other_macro, s, flags=re.S)
    s = re.sub(r"</?(?:ac|ri):[^>]*>", "", s)                         # leftovers
    s = re.sub(r'\s(?:data-)?(?:local-id|macro-id|ac:[\w-]+)="[^"]*"', "", s)  # noisy attributes
    s = re.sub(r"<li([^>]*)>\s*<p>((?:(?!</p>).)*)</p>\s*</li>", r"<li\1>\2</li>", s, flags=re.S)  # <li><p>x</p></li>
    s = re.sub(r"^\s*<h1[^>]*>.*?</h1>", lambda m: "" if re.match(r"\s*<h1[^>]*>\s*(KB:|" + re.escape(title) + ")", m.group(0)) else m.group(0), s, count=1, flags=re.S)
    return s.strip()

# ----------------------------------------------------------------------------- code colors
BOX = "background:#f6f8fa;border:1px solid #e1e4e8;border-radius:6px;padding:12px;overflow-x:auto;font-size:13px;line-height:1.45"
ALIASES = {"shell": "bash", "sh": "bash", "console": "bash", "yml": "yaml", "js": "javascript"}

def guess_lang(code):
    t = code.strip()
    if re.match(r"(org\.|java\.|\[WARNING\]|\[INFO\]|\[ERROR\]|Caused by)", t): return "none"
    if re.search(r"^\s*(apiVersion|kind|metadata|spec|resources):", t, re.M): return "yaml"
    if re.search(r"\b(new \w+\(|public |import )", t) and ";" in t: return "java"
    if re.search(r"^\s*(\$ |#|control\.sh|kubectl|systemctl|grep|tail|rm |sudo|docker|cd )", t, re.M): return "shell"
    return "none"

def colorize(page_html, inline=True):
    def render(m):
        code = html.unescape(m.group(2))
        lm = re.search(r"language-([\w+-]+)", m.group(1))
        lang = lm.group(1) if lm else guess_lang(code)
        lines = code.strip("\n").split("\n")
        pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        code = "\n".join(l[pad:] for l in lines)
        body = html.escape(code, quote=False)
        if inline and HAVE_PYGMENTS and lang != "none":
            try:
                body = _pyg_highlight(code, get_lexer_by_name(ALIASES.get(lang, lang)),
                                      HtmlFormatter(noclasses=True, nowrap=True, style="default")).rstrip("\n")
            except ClassNotFound:
                pass
        style = f' style="{BOX}"' if inline else ""
        return f'<pre class="language-{lang}"{style}><code class="language-{lang}">{body}</code></pre>'
    return re.sub(r"<pre[^>]*>\s*<code([^>]*)>(.*?)</code>\s*</pre>", render, page_html, flags=re.S)

# ----------------------------------------------------------------------------- build
def build_article(cfg, args, ref):
    r = resolve(cfg, ref)
    if r["status"] != "OK": return {"ref": ref, "ok": False, "status": r["status"], "message": r["message"]}
    page = fetch_page(cfg, r["page_id"])
    warnings = []
    body = storage_to_html(page["storage"], page["title"], warnings, args.keep_migration_note)
    tpl_path = Path(args.template) if args.template else HERE / "template.html"
    tpl = re.sub(r"<!--.*?-->\s*", "", tpl_path.read_text(encoding="utf-8"), flags=re.S)
    final = colorize(tpl.replace("{{TITLE}}", html.escape(page["title"])).replace("{{BODY}}", body), inline=not args.no_inline_colors)
    blocks = len(re.findall(r"<pre", final))
    if blocks and not HAVE_PYGMENTS and not args.no_inline_colors:
        warnings.append("pygments not installed: code blocks keep their language class but have no inline colors (pip install pygments)")
    slug = slugify(page["title"])
    out = Path(args.out_dir); (out / "preview").mkdir(parents=True, exist_ok=True)
    (out / f"{slug}.title.txt").write_text(page["title"], encoding="utf-8")
    (out / f"{slug}.final.html").write_text(final, encoding="utf-8")
    prev = (f'<!doctype html><html><head><meta charset="utf-8"><title>PREVIEW - {html.escape(page["title"])}</title>'
            '<style>body{font-family:system-ui,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;line-height:1.55;color:#222}'
            '.banner{background:#fff3cd;border:1px solid #e0c36a;padding:10px 14px;border-radius:6px;font-size:14px;margin-bottom:20px}'
            '.warn{background:#fdecea;border:1px solid #e5a6a0;padding:8px 14px;border-radius:6px;font-size:13px;margin-bottom:20px}</style></head><body>'
            '<div class="banner"><b>PREVIEW ONLY</b> - nothing has been sent to Zendesk. '
            f'Source: Confluence page {page["id"]} (v{page["version"]}). Code blocks: {blocks}.</div>'
            + (('<div class="warn"><b>Notes:</b><ul>' + "".join(f"<li>{html.escape(w)}</li>" for w in warnings) + "</ul></div>") if warnings else "")
            + f'<h1>{html.escape(page["title"])}</h1>{final}</body></html>')
    ppath = out / "preview" / f"{slug}-preview.html"
    ppath.write_text(prev, encoding="utf-8")
    return {"ref": ref, "ok": True, "status": "OK", "title": page["title"], "slug": slug, "page_id": page["id"],
            "body": final, "preview": str(ppath), "warnings": warnings, "blocks": blocks}

# ----------------------------------------------------------------------------- zendesk
def zd_base(cfg): return cfg.get("ZENDESK_BASE_URL") or f"https://{cfg['ZENDESK_SUBDOMAIN']}.zendesk.com"
def zd_auth(cfg): return f"{cfg['ZENDESK_EMAIL']}/token:{cfg['ZENDESK_API_TOKEN']}"

def existing_titles(cfg):
    locale = cfg.get("ZENDESK_LOCALE", "en-us"); titles = {}
    url = f"{zd_base(cfg)}/api/v2/help_center/{locale}/sections/{cfg['ZENDESK_SECTION_ID']}/articles?per_page=100"
    while url:
        d = http("GET", url, zd_auth(cfg))
        for a in d.get("articles", []): titles[a["title"].strip().lower()] = a.get("html_url")
        url = d.get("next_page")
    return titles

def create_article(cfg, title, body, publish):
    locale = cfg.get("ZENDESK_LOCALE", "en-us")
    art = {"title": title, "body": body, "locale": locale, "draft": not publish,
           "permission_group_id": int(cfg["ZENDESK_PERMISSION_GROUP_ID"])}
    if cfg.get("ZENDESK_USER_SEGMENT_ID"): art["user_segment_id"] = int(cfg["ZENDESK_USER_SEGMENT_ID"])
    url = f"{zd_base(cfg)}/api/v2/help_center/{locale}/sections/{cfg['ZENDESK_SECTION_ID']}/articles"
    return http("POST", url, zd_auth(cfg), {"article": art, "notify_subscribers": False})["article"]

# ----------------------------------------------------------------------------- commands
def cmd_read(cfg, args, refs):
    need(cfg, "ATLASSIAN_SITE", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN")
    bad = 0
    for ref in refs:
        r = resolve(cfg, ref)
        if r["status"] == "OK":
            try: fetch_page(cfg, r["page_id"]); print(f"{ref} is OK  ->  {r['title']}")
            except Exception as e: bad += 1; print(f"{ref} is ERROR: {e}")
        else:
            bad += 1; print(f"{ref} is {r['status']}" + (f": {r['message']}" if r["message"] else ""))
    return 1 if bad else 0

def cmd_preview(cfg, args, refs):
    need(cfg, "ATLASSIAN_SITE", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN")
    built = []
    for ref in refs:
        a = build_article(cfg, args, ref); built.append(a)
        if a["ok"]:
            print(f"{ref}: preview -> {a['preview']}  ({a['blocks']} code blocks)")
            for w in a["warnings"]: print(f"    note: {w}")
        else: print(f"{ref}: {a['status']} {a['message']}")
    ok = [a for a in built if a["ok"]]
    if ok:
        target = Path(ok[0]["preview"])
        if len(ok) > 1:
            target = Path(args.out_dir) / "preview" / "index.html"
            target.write_text("<!doctype html><meta charset='utf-8'><title>Previews</title><h1>Previews</h1><ul>" + "".join(
                f"<li><a href='{Path(a['preview']).name}'>{html.escape(a['title'])}</a></li>" for a in ok) + "</ul>", encoding="utf-8")
        print(f"\nOpen: {target.resolve()}")
        if not args.no_open: webbrowser.open(target.resolve().as_uri())
    return 0 if len(ok) == len(built) else 1

def cmd_migrate(cfg, args, refs):
    need(cfg, "ATLASSIAN_SITE", "ATLASSIAN_EMAIL", "ATLASSIAN_API_TOKEN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN",
         "ZENDESK_SECTION_ID", "ZENDESK_PERMISSION_GROUP_ID")
    if not (cfg.get("ZENDESK_BASE_URL") or cfg.get("ZENDESK_SUBDOMAIN")): need(cfg, "ZENDESK_SUBDOMAIN")
    print("Step 1/3 - reading and building previews")
    built = [build_article(cfg, args, r) for r in refs]
    for a in built:
        print(f"  {a['ref']}: " + (f"ready ({a['preview']})" if a["ok"] else f"{a['status']} {a['message']}"))
    todo = [a for a in built if a["ok"]]
    if not todo: return 1
    print("\nStep 2/3 - approval (previews are in " + str(Path(args.out_dir) / "preview") + ")")
    if not args.yes:
        if not sys.stdin.isatty(): sys.exit("Refusing to create articles without approval. Re-run with --yes after checking the previews.")
        if input(f"Create {len(todo)} {'article' if len(todo)==1 else 'articles'} in Zendesk as {'PUBLISHED' if args.publish else 'DRAFT'}? [y/N] ").lower() != "y":
            print("Cancelled. Nothing was sent to Zendesk."); return 1
    print("\nStep 3/3 - creating in Zendesk")
    titles = {}
    if not args.allow_duplicates:
        try: titles = existing_titles(cfg)
        except Exception as e: print(f"  (could not check for duplicates: {e})")
    report = []
    for a in built:
        if not a["ok"]:
            report.append((a["ref"], "", a["status"], a["message"], "")); continue
        key = a["title"].strip().lower()
        if key in titles:
            report.append((a["ref"], a["title"], "SKIPPED", "an article with this title already exists in the section", titles[key] or "")); print(f"  {a['ref']}: skipped (duplicate)"); continue
        try:
            z = create_article(cfg, a["title"], a["body"], args.publish)
            note = "; ".join(a["warnings"])
            report.append((a["ref"], a["title"], "CREATED " + ("(published)" if not z["draft"] else "(draft)"), note, z["html_url"]))
            print(f"  {a['ref']}: created -> {z['html_url']}")
        except Exception as e:
            report.append((a["ref"], a["title"], "FAILED", str(e), "")); print(f"  {a['ref']}: FAILED {e}")
    rp = Path(args.out_dir) / f"report-{dt.datetime.now():%Y%m%d-%H%M%S}.csv"
    with open(rp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["reference", "title", "status", "notes", "zendesk_url"]); w.writerows(report)
    print("\n=== STATUS REPORT ===")
    for ref, title, status, note, url in report:
        print(f"{ref:<14} {status:<20} {url or ''}" + (f"   [{note}]" if note else ""))
    print(f"\nReport saved: {rp}")
    return 0 if all(r[2].startswith("CREATED") for r in report) else 1

def main():
    p = argparse.ArgumentParser(description="Migrate Confluence GG articles to Zendesk Guide.", formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python gg2zd.py --read-from GG8-00002,GG8-00003\n  python gg2zd.py --zendesk-preview GG8-00002\n  python gg2zd.py --migrate-to-zendesk GG8-00002,GG8-00003 --yes")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--read-from", nargs="+", metavar="ARTICLES", help="check that the articles can be read from Atlassian")
    g.add_argument("--zendesk-preview", nargs="+", metavar="ARTICLES", help="build the Zendesk-format HTML and open it in the browser")
    g.add_argument("--migrate-to-zendesk", "--migrate-to-zendsk", dest="migrate", nargs="+", metavar="ARTICLES",
                   help="create the articles in Zendesk one by one and print a status report with the new URLs")
    p.add_argument("--template", help="Zendesk template HTML with {{TITLE}} and {{BODY}} (default: template.html next to the script)")
    p.add_argument("--out-dir", default="output", help="where previews, bodies and reports are written (default: ./output)")
    p.add_argument("--publish", action="store_true", help="publish live instead of creating drafts")
    p.add_argument("--yes", "-y", action="store_true", help="skip the approval prompt (use only after reviewing previews)")
    p.add_argument("--allow-duplicates", action="store_true", help="do not skip titles that already exist in the Zendesk section")
    p.add_argument("--no-open", action="store_true", help="do not open the preview in the browser")
    p.add_argument("--no-inline-colors", action="store_true", help="keep code language classes only, without inline syntax colors")
    p.add_argument("--keep-migration-note", action="store_true", help="keep the internal 'Migrated from ... review queue' panel")
    args = p.parse_args()
    cfg = load_config()
    if args.read_from: return cmd_read(cfg, args, split_refs(args.read_from))
    if args.zendesk_preview: return cmd_preview(cfg, args, split_refs(args.zendesk_preview))
    return cmd_migrate(cfg, args, split_refs(args.migrate))

if __name__ == "__main__":
    sys.exit(main())
