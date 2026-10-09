"""Local fake Confluence + Zendesk used to test gg2zd.py without network access."""
import json, re, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

CODE = ('<ac:structured-macro ac:name="code" ac:schema-version="1"><ac:parameter ac:name="language">{}</ac:parameter>'
        '<ac:plain-text-body><![CDATA[{}]]></ac:plain-text-body></ac:structured-macro>')
PAGES = {
 "101": ("GG8-00002: Cluster Unavailable During Scheduled Snapshots", "<h1>KB: Cluster Unavailable</h1><p><strong>Article ID:</strong> GG8-KB-00002</p><h2>Problem</h2><p>Clients fail.</p>"
         + CODE.format("shell", "# list\ncontrol.sh --snapshot scheduler list") + "<ul><li><p>one</p></li><li><p>two</p></li></ul>"
         + CODE.format("none", "Security context is not ready <x>")),
 "102": ("GG8-00003: Baseline Incompatibility", '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Migrated from the GridGain Confluence review queue. See the original page.</p></ac:rich-text-body></ac:structured-macro>'
         '<h1>KB: Baseline</h1><h2>Solution</h2><ol><li><p>Stop the node</p></li><li><p>Start it</p></li></ol>'
         '<ac:structured-macro ac:name="warning"><ac:rich-text-body><p>Back up first.</p></ac:rich-text-body></ac:structured-macro>'
         '<ac:image><ri:attachment ri:filename="diagram.png" /></ac:image>' + CODE.format("java", 'cfg.setBaselineAutoAdjustEnabled(false);\nint x = 1;')
         + '<ac:structured-macro ac:name="toc" />'),
 "103": ("GG8-00099: Duplicate A", "<p>a</p>"), "104": ("GG8-00099: Duplicate B", "<p>b</p>"),
 "105": ("GG8-00018: Cluster Defragmentation", "<p>d</p>"),
}
CREATED = []
EXISTING = [{"title": "GG8-00018: Cluster Defragmentation", "html_url": "http://zd/hc/articles/1-old"}]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, code=200):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path.endswith("/rest/api/content/search"):
            cql = q["cql"][0]; t = re.search(r'title [=~] "([^"]*)"', cql).group(1); exact = bool(re.search(r"title = ", cql))
            res = [{"id": i, "title": ti} for i, (ti, _) in PAGES.items() if (ti == t if exact else t.lower() in ti.lower())]
            return self._send({"results": res})
        m = re.search(r"/rest/api/content/(\d+)", u.path)
        if m and m.group(1) in PAGES:
            ti, body = PAGES[m.group(1)]
            return self._send({"id": m.group(1), "title": ti, "body": {"storage": {"value": body}}, "version": {"number": 3, "when": "2026-09-24"}})
        if "/sections/" in u.path and u.path.endswith("/articles"): return self._send({"articles": EXISTING, "next_page": None})
        self._send({"error": "not found"}, 404)
    def do_POST(self):
        n = int(self.headers["Content-Length"]); d = json.loads(self.rfile.read(n))
        if d["article"]["title"].startswith("GG8-00003"):  # simulate a Zendesk failure
            return self._send({"error": "RecordInvalid"}, 422)
        CREATED.append(d); i = 900 + len(CREATED)
        a = dict(d["article"], id=i, html_url=f"https://mariadb.zendesk.com/hc/en-us/articles/{i}-new")
        self._send({"article": a}, 201)

def start(port=0):
    s = HTTPServer(("127.0.0.1", port), H); threading.Thread(target=s.serve_forever, daemon=True).start(); return s
