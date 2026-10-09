# gg2zd: migrate Confluence articles (GG8-xxxxx) to Zendesk Guide

`gg2zd.py` reads knowledge articles from Confluence, converts them to Zendesk-ready HTML (original title and
code-block colors kept) and creates them in Zendesk Guide as **drafts**, one by one, with a status report
showing the new URL of each article.

- One Python file, standard library only. No Claude, no connectors.
- Nothing is sent to Zendesk without your approval (`[y/N]` question) and everything is a draft unless you say `--publish`.
- Works with one article or many (comma separated, or from a file).

---

## 1. Quick start

```bash
pip install pygments                 # optional, adds colors to code blocks
cp .env.example .env                 # then edit .env (section 3)
python3 gg2zd.py --list-zendesk-ids  # find your section ID / permission group ID
python3 gg2zd.py --test-connection   # everything green?
python3 gg2zd.py --zendesk-preview GG8-00002
python3 gg2zd.py --migrate-to-zendesk GG8-00002
```

## 2. Requirements and files

- Python 3.8 or newer (`python3 --version`), internet access to Atlassian and Zendesk.
- Accounts: Atlassian (read access to the articles) and Zendesk (agent with Guide permissions).

```
gg2zd/
├── gg2zd.py               the tool
├── template.html          your Zendesk article layout (you must edit it, section 3.5)
├── .env.example           configuration example (copy to .env)
├── articles.example.txt   example list of articles for --articles-file
├── .gitignore             keeps .env and output/ out of git
├── README.md              this file
└── tests/                 local tests with fake servers (no network, no tokens)
```

---

## 3. Configuration

### 3.1 Create `.env`
Copy `.env.example` to `.env` in the same folder as `gg2zd.py` (Windows: `copy .env.example .env`):

```
ATLASSIAN_SITE=https://mariadbcorp.atlassian.net
ATLASSIAN_EMAIL=your.name@mariadb.com
ATLASSIAN_API_TOKEN=paste-your-atlassian-token
CONFLUENCE_SPACE=~71202027e8c92a603646529ce56ebd66843566

ZENDESK_SUBDOMAIN=mariadb1781281616
ZENDESK_EMAIL=your.name@mariadb.com
ZENDESK_API_TOKEN=paste-your-zendesk-token
ZENDESK_SECTION_ID=48053197306253
ZENDESK_PERMISSION_GROUP_ID=paste-the-id
ZENDESK_USER_SEGMENT_ID=
ZENDESK_LOCALE=en-us
```

| Variable | Required | Meaning |
|---|---|---|
| `ATLASSIAN_SITE` | yes | Your Confluence Cloud site |
| `ATLASSIAN_EMAIL` / `ATLASSIAN_API_TOKEN` | yes | Atlassian login and API token (3.2) |
| `CONFLUENCE_SPACE` | no | Space key to search in (a personal space key starts with `~`). Empty = search everywhere |
| `ZENDESK_SUBDOMAIN` | yes | The part before `.zendesk.com` (`mariadb1781281616`) |
| `ZENDESK_EMAIL` / `ZENDESK_API_TOKEN` | yes | Zendesk agent email and API token (3.3) |
| `ZENDESK_SECTION_ID` | yes | Numeric ID of the Guide section where articles are created (3.4). The section decides the brand (`46604288989965`) |
| `ZENDESK_PERMISSION_GROUP_ID` | yes | Numeric ID of the permission group managing the articles (3.4) |
| `ZENDESK_USER_SEGMENT_ID` | no | Who can see the article. Empty = everyone |
| `ZENDESK_LOCALE` | no | Default `en-us` |

Rules: one `NAME=value` per line, no spaces around `=`, no quotes. Never share or commit `.env` (it holds your tokens).
Variables set in the terminal override `.env`.

### 3.2 Atlassian API token
https://id.atlassian.com/manage-profile/security/api-tokens, then **Create API token**.

### 3.3 Zendesk API token
Admin Center, then Apps and integrations, then APIs, then **Zendesk API**: enable **Token access** and **Add API token**.

### 3.4 Find the section ID and permission group ID
Fill the Zendesk email, token and subdomain in `.env`, then run:

```bash
python3 gg2zd.py --list-zendesk-ids
```

- It lists every section with its ID. Pick the section for your articles; for GridGain articles that is
  **MariaDB GridGain Section** (`48053197306253`). Do not take numbers from Guide admin URLs such as
  `/knowledge/lists/default/8/1`: they are not section IDs.
- It lists the permission groups. If your account is not allowed to read them (HTTP 403), the tool shows instead the
  permission group IDs used by existing articles; choose the one used in your section. If the section has no articles yet,
  create any draft by hand in it and run the command again.

### 3.5 Template
`template.html` is the layout of every article. The included one is only a placeholder.
1. In Zendesk open your template in the editor and switch to the **HTML / source** view.
2. Paste that HTML into `template.html`.
3. Put `{{TITLE}}` where the title goes and `{{BODY}}` where the converted Confluence content goes.

Use another template for one run with `--template other.html`.

---

## 4. Commands (choose one)

Articles are separated by commas. Each can be a GG ID (`GG8-00002`; `GG08-00002` also works), a full or partial
title (`"Cluster Defragmentation"`), or a Confluence page URL.

| Command | What it does |
|---|---|
| `--test-connection` | Checks the Atlassian login, Confluence space, Zendesk section, permission group and template. Sends nothing |
| `--list-zendesk-ids` | Lists Zendesk section IDs and permission group IDs for `.env` |
| `--read-from A,B,...` | Checks the articles can be read. Prints `A is OK`, `NOT FOUND`, `AMBIGUOUS` or `ERROR` for each |
| `--zendesk-preview A,B,...` | Builds the Zendesk-format HTML, saves it in `output/preview/` and opens it in the browser. Sends nothing |
| `--migrate-to-zendesk A,B,...` | Creates the articles in Zendesk one by one and prints a status report with the new URLs |

`--migrate-to-zendsk` (without the `e`) is accepted too. Run `python3 gg2zd.py --help` for the built-in help.

### 4.1 Options

| Option | Effect |
|---|---|
| `--articles-file FILE` | Read the articles from a text file (one per line or comma separated, `#` lines ignored). See `articles.example.txt` |
| `--limit N` | Process only the first N articles (good for test batches) |
| `--dry-run` | With `--migrate-to-zendesk`: do everything except sending; saves the payloads in `output/dryrun/` |
| `--yes`, `-y` | Skip the approval question (use only after checking the previews) |
| `--publish` | Publish live instead of creating drafts |
| `--allow-duplicates` | Do not skip titles that already exist in the section |
| `--template FILE` | Use another template file |
| `--out-dir DIR` | Output folder (default `./output`) |
| `--no-open` | Do not open the preview in the browser |
| `--no-inline-colors` | Keep only the code language, no inline syntax colors |
| `--keep-migration-note` | Keep the internal "Migrated from ... review queue" panel |

### 4.2 What `--migrate-to-zendesk` does
1. Reads and converts every article, writes the previews.
2. Asks `Create N articles in Zendesk as DRAFT? [y/N]`. Without an interactive terminal it refuses unless you pass `--yes`.
3. Checks the section for titles that already exist and **skips** them.
4. Creates the rest one by one as drafts. One failure never stops the others.
5. Prints a status report and saves it as `output/report-<time>.csv`:

```
=== STATUS REPORT ===
GG8-00002      CREATED (draft)      https://mariadb1781281616.zendesk.com/hc/en-us/articles/123-...
GG8-00003      FAILED               [HTTP 422 ...]
GG8-00018      SKIPPED              https://...   [an article with this title already exists in the section]
GG8-00500      NOT FOUND
```

---

## 5. Recommended workflow

```bash
python3 gg2zd.py --test-connection                                   # 1. settings OK?
python3 gg2zd.py --read-from GG8-00002,GG8-00003                     # 2. can I read them?
python3 gg2zd.py --zendesk-preview GG8-00002,GG8-00003               # 3. do they look right?
python3 gg2zd.py --migrate-to-zendesk GG8-00002,GG8-00003 --dry-run  # 4. rehearsal, sends nothing
python3 gg2zd.py --migrate-to-zendesk GG8-00002,GG8-00003            # 5. create drafts (answer y)
```
Then open the drafts in Zendesk, review them and publish from there. Try **one** article first, then a batch:
`python3 gg2zd.py --migrate-to-zendesk --articles-file articles.txt --limit 2`.

## 6. Output files (in `output/`)

| File | Content |
|---|---|
| `<GG-ID>.final.html` | The exact body sent to Zendesk |
| `<GG-ID>.title.txt` | The exact title |
| `preview/<GG-ID>-preview.html`, `preview/index.html` | Previews |
| `dryrun/<GG-ID>.json` | Payloads (with `--dry-run`) |
| `report-<time>.csv` | Status report of the migration |

## 7. What the conversion does

- The **title is kept exactly** as in Confluence.
- Removed: the `KB: ...` heading at the top, the internal "Migrated from ... review queue" panel (unless `--keep-migration-note`),
  and Confluence-internal attributes.
- **Code blocks keep their language** (shell, java, yaml...) and get syntax colors; blocks marked `none` (logs, error
  messages) stay plain.
- Info / note / warning / tip panels become quoted blocks; list items are cleaned up.
- **Not migrated** (listed in the preview notes and in the report): images and attachments, and Confluence macros without an equivalent.

## 8. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `Missing configuration: ...` | A value is missing in `.env`, or you ran the command from another folder |
| `HTTP 401` | Wrong email or token. For Zendesk, check that token access is enabled |
| `HTTP 403` from Atlassian | No permission to the space or page |
| `[FAIL]` or `403` on the permission group | Your account cannot read the group list through the API. Not an error by itself: use `--list-zendesk-ids` to take the ID from existing articles |
| `HTTP 404` / `RecordNotFound` from Zendesk | `ZENDESK_SECTION_ID` does not exist (for example `1`) or the locale is wrong. The message shows the value used. Run `--list-zendesk-ids` |
| `HTTP 422 invalid permission_group_id` | Wrong `ZENDESK_PERMISSION_GROUP_ID`. Use an ID used by existing articles in that section |
| `NOT FOUND` | Check the ID or title; set `CONFLUENCE_SPACE` correctly or leave it empty |
| `AMBIGUOUS` | More than one page matches. Use the full title or the page URL |
| `HTTP 429` | Rate limit. The tool waits and retries |
| Code has no colors | `pip install pygments`. If Zendesk strips styles, use `--no-inline-colors` |
| Article does not match your layout | `template.html` is still the placeholder, or lacks `{{TITLE}}` / `{{BODY}}` |
| "Refusing to create articles without approval" | Not an interactive terminal. Check the previews, then add `--yes` |
| Preview does not open | Use `--no-open` and open `output/preview/<GG-ID>-preview.html` by hand |

## 9. Exit codes
`0` everything succeeded, `1` at least one article failed, was not found or was skipped, `2` wrong usage.

## 10. Limits

- Tested against local fake servers; check the first real draft (layout, colors) before a big batch.
- Uses Confluence Cloud REST API v1 with a classic API token. A scoped token needs `read:content-details:confluence`,
  `read:space:confluence` and `search:confluence`.
- The template is applied as the HTML you paste into `template.html`. Section-by-section mapping, tags/labels and image upload are not included.
- Zendesk may sanitize HTML on save. Always review the draft.

## 11. Tests (optional)
```bash
python3 tests/run_tests.py
```
Runs the tool against fake Confluence and Zendesk servers on your own machine. No network or tokens needed.

## 12. Security
`.env` holds your tokens: never commit or share it (`.gitignore` already excludes it, and `output/`).
If a token leaks, revoke it and create a new one.
