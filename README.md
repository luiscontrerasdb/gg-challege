# gg2zd — Migrate Confluence articles (GG8-xxxxx) to Zendesk Guide

`gg2zd.py` reads knowledge articles from Confluence, converts them to Zendesk-ready HTML (keeping the
original title and the code-block colors) and creates them in Zendesk Guide as **drafts**, one by one,
with a status report at the end.

It is a single Python script. No Claude, no connectors. It talks directly to the Confluence and Zendesk APIs.

---

## 1. Requirements

- Python 3.8 or newer (`python --version`)
- Optional but recommended: `pygments`, which adds syntax colors to code blocks

```bash
pip install pygments
```

## 2. Files

```
gg2zd/
├── gg2zd.py          the tool
├── template.html     your Zendesk article layout  (you must edit this)
├── .env.example      configuration example        (copy it to .env)
├── README.md         this file
└── tests/            local tests with fake servers (no network needed)
```

## 3. Configuration

### 3.1 Create your `.env`

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Open `.env` and fill in the values:

| Variable | Required | What it is |
|---|---|---|
| `ATLASSIAN_SITE` | yes | `https://mariadbcorp.atlassian.net` |
| `ATLASSIAN_EMAIL` | yes | Your Atlassian account email |
| `ATLASSIAN_API_TOKEN` | yes | Atlassian API token (see 3.2) |
| `CONFLUENCE_SPACE` | no | Space key to search in. Your personal space key starts with `~`. Leave empty to search everywhere |
| `ZENDESK_SUBDOMAIN` | yes | `mariadb` |
| `ZENDESK_EMAIL` | yes | Your Zendesk agent email |
| `ZENDESK_API_TOKEN` | yes | Zendesk API token (see 3.3) |
| `ZENDESK_SECTION_ID` | yes | Numeric ID of the Guide section where articles are created (see 3.4) |
| `ZENDESK_PERMISSION_GROUP_ID` | yes | Numeric ID of the permission group that manages the articles (see 3.5) |
| `ZENDESK_USER_SEGMENT_ID` | no | Who can see the article. Empty = everyone |
| `ZENDESK_LOCALE` | no | Default `en-us` |

> Never share or commit `.env`. It contains your tokens.
> Variables set in the terminal override the ones in `.env`.

### 3.2 Atlassian API token
1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. **Create API token**, copy it, and paste it as `ATLASSIAN_API_TOKEN`.

### 3.3 Zendesk API token
1. Zendesk **Admin Center → Apps and integrations → APIs → Zendesk API**.
2. Enable **Token access**, then **Add API token**, copy it, and paste it as `ZENDESK_API_TOKEN`.

### 3.4 Find the section ID
Your articles go into one Guide section. The section also decides the brand (`20641285140365`), so pick a
section that belongs to that brand. List the sections with:

```bash
curl -u "you@mariadb.com/token:YOUR_ZENDESK_TOKEN" \
  "https://mariadb.zendesk.com/api/v2/help_center/en-us/sections.json?per_page=100"
```
Look for the section name and copy its `"id"`. (The number also appears in the section's URL in Guide admin.)

### 3.5 Find the permission group ID
```bash
curl -u "you@mariadb.com/token:YOUR_ZENDESK_TOKEN" \
  "https://mariadb.zendesk.com/api/v2/guide/permission_groups.json"
```
Copy the `"id"` of the group that should manage the migrated articles.

### 3.6 Set up the template
`template.html` defines how the article looks in Zendesk. The one included is only a **placeholder**.

1. In Zendesk, open your template in the editor and switch to the **HTML / source** view.
2. Copy the HTML into `template.html`, replacing its contents.
3. Put `{{TITLE}}` where the article title goes and `{{BODY}}` where the converted Confluence content goes.

You can use another template file for one run with `--template other.html`.

---

## 4. Usage

Articles are separated by commas. Each one can be:

- a GG ID: `GG8-00002` (`GG08-00002` also works)
- a full title or a part of it: `"Cluster Defragmentation"`
- a Confluence page URL

### 4.1 Check that the articles can be read

```bash
python gg2zd.py --read-from GG8-00002,GG8-00003
```
```
GG8-00002 is OK  ->  GG8-00002: Cluster Unavailable During Scheduled Snapshots with Heavy Query Load
GG8-00003 is OK  ->  GG8-00003: BaselineTopology Incompatibility Error When Node Rejoins Cluster
```
Other results: `NOT FOUND`, `AMBIGUOUS` (more than one page matches; the matches are listed), `ERROR`.

### 4.2 Preview in Zendesk format

```bash
python gg2zd.py --zendesk-preview GG8-00002,GG8-00003
```
Creates one HTML preview per article in `output/preview/` (plus an `index.html` when there are several)
and opens it in your browser. **Nothing is sent to Zendesk.** Notes about removed or unsupported content
are shown at the top of each preview and in the terminal. Use `--no-open` to skip opening the browser.

### 4.3 Migrate

```bash
python gg2zd.py --migrate-to-zendesk GG8-00002,GG8-00003,GG8-00018
```
1. Reads and converts every article and writes the previews.
2. Asks for approval: `Create 3 articles in Zendesk as DRAFT? [y/N]`.
3. Creates the articles one by one, as **drafts**.
4. Prints a status report and saves it to `output/report-<date-time>.csv`:

```
=== STATUS REPORT ===
GG8-00002      CREATED (draft)      https://mariadb.zendesk.com/hc/en-us/articles/123-...
GG8-00003      FAILED                  [HTTP 422 ...]
GG8-00018      SKIPPED              https://mariadb.zendesk.com/hc/en-us/articles/45-...   [an article with this title already exists in the section]
GG8-00500      NOT FOUND
```
A failure on one article does not stop the others. The exit code is 0 only when everything succeeded.

### 4.4 Options

| Option | Effect |
|---|---|
| `--yes`, `-y` | Skip the approval question (only use after checking the previews) |
| `--publish` | Publish live instead of creating drafts |
| `--allow-duplicates` | Do not skip titles that already exist in the section |
| `--template FILE` | Use another template file |
| `--out-dir DIR` | Output folder (default `./output`) |
| `--no-open` | Do not open the preview in the browser |
| `--no-inline-colors` | Keep the code language only, no inline syntax colors |
| `--keep-migration-note` | Keep the "Migrated from the GridGain Confluence review queue" panel |

### 4.5 Recommended workflow

```bash
python gg2zd.py --read-from GG8-00002,GG8-00003     # 1. can I read them?
python gg2zd.py --zendesk-preview GG8-00002,GG8-00003   # 2. do they look right?
python gg2zd.py --migrate-to-zendesk GG8-00002,GG8-00003 # 3. create drafts, say y
```
Then open the drafts in Zendesk, review them, and publish from there.
Start with **one** article the first time to confirm the template and the colors look right.

---

## 5. What the conversion does

- The **title is kept exactly** as in Confluence.
- Removed: the `KB: …` heading at the top of the page, the internal "Migrated from…" panel, and Confluence-internal attributes.
- **Code blocks keep their language** (shell, java, yaml…) and get syntax colors. Blocks marked `none` (logs, error messages) stay plain.
- Info / note / warning / tip panels become quoted blocks (`Note:`, `Warning:`…); list items are cleaned up.
- **Not migrated**, but listed in the preview notes and the report: images and attachments, and Confluence macros that have no equivalent (for example table of contents).

Output files per article, in `output/`: `<GG-ID>.final.html` (the exact body sent to Zendesk),
`<GG-ID>.title.txt`, and `preview/<GG-ID>-preview.html`.

---

## 6. Troubleshooting

| Problem | Cause / fix |
|---|---|
| `Missing configuration: …` | A required value is missing in `.env`. Run the command from the folder that contains `.env` |
| `HTTP 401` from Atlassian or Zendesk | Wrong email or token. For Zendesk, check that token access is enabled |
| `HTTP 403` | Your account lacks permission (space access in Confluence, or Guide admin rights in Zendesk) |
| `NOT FOUND` | Check the ID/title. Set `CONFLUENCE_SPACE` correctly or leave it empty |
| `AMBIGUOUS` | More than one page matches. Use the full title or the page URL |
| `HTTP 422` from Zendesk | Usually a wrong `ZENDESK_PERMISSION_GROUP_ID` or `ZENDESK_SECTION_ID`, or `ZENDESK_USER_SEGMENT_ID` |
| `HTTP 429` | Rate limit. The tool waits and retries automatically |
| Code blocks have no colors | `pip install pygments`. If Zendesk strips the styles when saving, use `--no-inline-colors` |
| Article looks different from the template | `template.html` is still the placeholder, or lacks `{{TITLE}}` / `{{BODY}}` |
| "Refusing to create articles without approval" | The tool was run without an interactive terminal. Add `--yes` after reviewing the previews |

## 7. Limits

- Tested only against local fake servers, not your live Atlassian and Zendesk. Check the first real draft before a big batch.
- Uses Confluence Cloud REST API v1 with a classic API token. If your token is scoped, it needs the
  `read:content-details:confluence` and `search:confluence` scopes.
- The Zendesk template is applied as the HTML you paste into `template.html`. Section-by-section mapping,
  tags/labels and image upload are not included.

## 8. Run the tests (optional)

```bash
python tests/run_tests.py
```
Runs the tool against fake Confluence and Zendesk servers on your own machine. No network or tokens needed.
