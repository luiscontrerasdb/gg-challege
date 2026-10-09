import os, subprocess, sys, tempfile, pathlib
sys.path.insert(0, os.path.dirname(__file__)); import mock_servers
srv = mock_servers.start(); base = f"http://127.0.0.1:{srv.server_address[1]}"
env = dict(os.environ, ATLASSIAN_SITE=base, ATLASSIAN_EMAIL="a@b.c", ATLASSIAN_API_TOKEN="x", ZENDESK_BASE_URL=base,
           ZENDESK_EMAIL="a@b.c", ZENDESK_API_TOKEN="y", ZENDESK_SECTION_ID="1", ZENDESK_PERMISSION_GROUP_ID="2")
script = str(pathlib.Path(__file__).resolve().parent.parent / "gg2zd.py"); out = tempfile.mkdtemp()
def run(*a):
    r = subprocess.run([sys.executable, script, *a, "--out-dir", out, "--no-open"], env=env, capture_output=True, text=True, cwd=out)
    print("$ gg2zd", " ".join(a)); print(r.stdout + r.stderr); return r
run("--read-from", "GG8-00002, GG08-00003, GG8-00099, GG8-00500, GG8-00018")
run("--zendesk-preview", "GG8-00002,GG8-00003")
run("--migrate-to-zendsk", "GG8-00002,GG8-00003,GG8-00018,GG8-00500", "--yes")
print("created payloads:", [(c["article"]["title"], c["article"]["draft"]) for c in mock_servers.CREATED])
print(open(f"{out}/GG8-00003.final.html").read()[:1500])
