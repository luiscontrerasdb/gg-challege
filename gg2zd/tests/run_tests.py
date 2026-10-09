"""End-to-end tests for gg2zd.py against local fake Confluence + Zendesk servers (no network needed).
Run:  python tests/run_tests.py
"""
import csv, glob, json, os, pathlib, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__)); import mock_servers

srv = mock_servers.start(); base = f"http://127.0.0.1:{srv.server_address[1]}"
SCRIPT = str(pathlib.Path(__file__).resolve().parent.parent / "gg2zd.py")
FULL = dict(ATLASSIAN_SITE=base, ATLASSIAN_EMAIL="a@b.c", ATLASSIAN_API_TOKEN="x", ZENDESK_BASE_URL=base, ZENDESK_EMAIL="a@b.c",
            ZENDESK_API_TOKEN="y", ZENDESK_SECTION_ID="1", ZENDESK_PERMISSION_GROUP_ID="2")
results = []

def run(args, env=None, stdin=subprocess.DEVNULL):
    out = tempfile.mkdtemp()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("ATLASSIAN_", "ZENDESK_", "CONFLUENCE_"))}
    e.update(FULL if env is None else env)
    r = subprocess.run([sys.executable, SCRIPT, *args, "--out-dir", out, "--no-open"], env=e, capture_output=True, text=True, cwd=out, stdin=stdin)
    return r, out, r.stdout + r.stderr

def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"\n      {detail}"))

# --- read-from: several articles, names/IDs, status per article
r, out, t = run(["--read-from", "GG8-00002, GG08-00003, GG8-00099, GG8-00500"])
check("read-from: OK article", "GG8-00002 is OK" in t, t)
check("read-from: leading zero GG08 accepted", "GG08-00003 is OK" in t, t)
check("read-from: ambiguous reported with matches", "GG8-00099 is AMBIGUOUS" in t and "Duplicate A" in t, t)
check("read-from: not found reported", "GG8-00500 is NOT FOUND" in t, t)
check("read-from: exit code 1 when something fails", r.returncode == 1)
r, out, t = run(["--read-from", "GG8-00002", "GG8-00003"])
check("read-from: space separated IDs, exit 0", t.count(" is OK") == 2 and r.returncode == 0, t)
r, out, t = run(["--read-from", "Another Article"])
check("read-from: by partial title", "is OK  ->  GG8-00020: Another Article" in t, t)

# --- articles file, dedupe, limit
f = pathlib.Path(tempfile.mkdtemp()) / "articles.txt"
f.write_text("# my batch\nGG8-00002\n\nGG8-00003, GG8-00020\ngg08-00002\n")
r, out, t = run(["--read-from", "GG8-00002", "--articles-file", str(f)])
check("articles-file: merged, comments ignored, repeats removed", t.count(" is OK") == 3, t)
r, out, t = run(["--read-from", "--articles-file", str(f), "--limit", "2"])
check("--limit processes only the first N", t.count(" is OK") == 2 and "GG8-00020" not in t, t)
r, out, t = run(["--read-from"])
check("no articles given -> clear error", r.returncode != 0 and "No articles given" in t, t)
r, out, t = run(["--read-from", "--articles-file", "/nonexistent.txt"])
check("missing articles-file -> clear error", r.returncode != 0 and "not found" in t, t)

# --- preview
r, out, t = run(["--zendesk-preview", "GG8-00002,GG8-00003"])
prev = pathlib.Path(out, "preview")
check("preview: one file per article + index", (prev / "GG8-00002-preview.html").exists() and (prev / "GG8-00003-preview.html").exists() and (prev / "index.html").exists(), t)
body = (pathlib.Path(out) / "GG8-00002.final.html").read_text()
check("preview: title file keeps the exact title", (pathlib.Path(out) / "GG8-00002.title.txt").read_text() == "GG8-00002: Cluster Unavailable During Scheduled Snapshots")
check("preview: KB heading removed", "KB:" not in body)
check("preview: code language kept", 'class="language-shell"' in body and 'class="language-none"' in body)
check("preview: code text escaped", "&lt;x&gt;" in body)
check("preview: li/p flattened", "<li>one</li>" in body)
try:
    import pygments; check("preview: inline syntax colors", "<span style=" in body)
except ImportError: print("SKIP  inline colors (pygments not installed)")
b3 = (pathlib.Path(out) / "GG8-00003.final.html").read_text()
check("preview: migration note removed", "Migrated from" not in b3 and "review queue" not in b3)
check("preview: warning panel -> blockquote", "<blockquote>" in b3 and "Warning:" in b3)
check("preview: image + macro warnings reported", "diagram.png" in t and "toc" in t, t)
r, out, t = run(["--zendesk-preview", "GG8-00002"])
check("preview: single article has no index", not pathlib.Path(out, "preview", "index.html").exists())

# --- migrate: approval gate
before = len(mock_servers.CREATED)
r, out, t = run(["--migrate-to-zendesk", "GG8-00002"])
check("migrate: refuses without approval (no tty)", r.returncode != 0 and "without approval" in t and len(mock_servers.CREATED) == before, t)

# --- migrate: dry run
r, out, t = run(["--migrate-to-zendesk", "GG8-00002,GG8-00018,GG8-00500", "--dry-run"])
check("dry-run: nothing sent", len(mock_servers.CREATED) == before, t)
check("dry-run: WOULD CREATE / WOULD SKIP / NOT FOUND", "WOULD CREATE (draft)" in t and "WOULD SKIP" in t and "NOT FOUND" in t, t)
pj = json.loads(pathlib.Path(out, "dryrun", "GG8-00002.json").read_text())
check("dry-run: payload saved (draft, section, permission group)", pj["article"]["draft"] is True and pj["section_id"] == "1" and pj["article"]["permission_group_id"] == 2, pj)
r, out, t = run(["--migrate-to-zendesk", "GG8-00002", "--dry-run"], env={k: v for k, v in FULL.items() if k.startswith("ATLASSIAN_")})
check("dry-run: works without Zendesk settings", r.returncode == 0 and "WOULD CREATE" in t, t)
r, out, t = run(["--read-from", "GG8-00002", "--dry-run"])
check("--dry-run only valid with migrate", r.returncode == 2, t)

# --- migrate: real run, one by one, mixed results
r, out, t = run(["--migrate-to-zendesk", "GG8-00002,GG8-00003,GG8-00018,GG8-00500", "--yes"])
check("migrate: created article gets URL", "CREATED (draft)" in t and "zendesk.com/hc/en-us/articles/" in t, t)
check("migrate: failure is reported and does not stop the run", "GG8-00003" in t and "FAILED" in t and "GG8-00018" in t, t)
check("migrate: duplicate skipped, missing reported", "SKIPPED" in t and "NOT FOUND" in t, t)
check("migrate: only the valid article was POSTed", len(mock_servers.CREATED) == before + 1, len(mock_servers.CREATED) - before)
posted = mock_servers.CREATED[-1]["article"]
check("migrate: posted as draft with exact title and permission group", posted["draft"] is True and posted["title"].startswith("GG8-00002:") and posted["permission_group_id"] == 2, posted)
check("migrate: exit 1 when anything failed", r.returncode == 1)
rows = list(csv.reader(open(glob.glob(f"{out}/report-*.csv")[0])))
check("migrate: CSV report with one row per article", len(rows) == 5 and rows[0][0] == "reference", rows)

# --- migrate: all good, publish
n = len(mock_servers.CREATED)
r, out, t = run(["--migrate-to-zendesk", "GG8-00002, GG8-00020", "--yes"])
check("migrate: several articles, all CREATED, exit 0", r.returncode == 0 and len(mock_servers.CREATED) == n + 2 and t.count("CREATED") >= 2, t)
r, out, t = run(["--migrate-to-zendesk", "GG8-00020", "--yes", "--publish"])
check("migrate --publish posts draft=false", mock_servers.CREATED[-1]["article"]["draft"] is False, t)

# --- test-connection
r, out, t = run(["--test-connection"])
check("test-connection: all OK", r.returncode == 0 and "[ OK ] Atlassian login" in t and "Knowledge Base" in t and "Support agents" in t and "All checks passed" in t, t)
r, out, t = run(["--test-connection"], env=dict(FULL, ZENDESK_API_TOKEN="badtoken"))
check("test-connection: bad Zendesk token detected", r.returncode == 1 and "[FAIL] Zendesk section" in t and "401" in t, t)
r, out, t = run(["--test-connection"], env={k: v for k, v in FULL.items() if k.startswith("ATLASSIAN_")})
check("test-connection: missing Zendesk settings listed", r.returncode == 1 and "missing ZENDESK_EMAIL" in t, t)
r, out, t = run(["--test-connection"], env={})
check("test-connection: nothing configured", r.returncode == 1 and "missing ATLASSIAN_SITE" in t, t)

# --- help
for flags in (["--help"], ["-h"]):
    r, out, t = run(flags)
    check(f"help: {flags[0]} shows the guide", r.returncode == 0 and "WHAT IT DOES" in t and "--migrate-to-zendesk" in t and "TYPICAL WORKFLOW" in t and "EXIT CODES" in t, t[:300])
r = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True, env=dict(os.environ))
check("help: no arguments shows the guide", r.returncode == 0 and "WHAT IT DOES" in r.stdout, r.stdout[:200] + r.stderr)
r, out, t = run(["--out-dir", "x"]) if False else run(["--limit", "2"])
check("help: option without a command -> clear error", r.returncode == 2 and "choose a command" in t, t)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
