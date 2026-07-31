# LCPS ParentVUE CLI

CLI tool for pulling grades and report cards from the LCPS ParentVUE portal.

## Project structure

| File | Purpose |
|------|---------|
| `parentvue.py` | Single-file CLI script. Contains `ParentVUEClient` (web session transport), command implementations, and `argparse` CLI. |
| `README.md` | User-facing usage docs, install instructions, examples. |

## Technical details

- **Language:** Python 3.8+. Single file, no package structure.
- **Dependencies:** `requests` (only external). Everything else is stdlib.
- **API:** Web scraping via authenticated ASP.NET session at `https://{district}/`. The SOAP API (`PXPCommunication.asmx`) was deprecated by Edupoint in July 2026 when the new ParentVUE mobile app launched. The web interface remains functional.
- **Auth:** ASP.NET form login to `PXP2_Login_Parent.aspx`. Credentials via `PARENTVUE_USER`/`PARENTVUE_PASS` env vars or interactive prompt.
- **Default district:** `portal.lcps.org` (Loudoun County Public Schools). Overridable with `--district`.

## Architecture

`ParentVUEClient` handles all ParentVUE interaction via the web interface:
- `_login()` authenticates by POSTing the ASP.NET login form and maintains session cookies.
- `get_child_list()` parses JSON child data embedded in the home page (`Home_PXP2.aspx`).
- `list_documents()` scrapes `PXP2_Documents.aspx?AGU={child_index}` and parses the dataSource JSON.
- `list_report_cards()` filters documents for types containing "Report Card".
- `download_document()` fetches PDFs via `PXP_ShowDocument.aspx` using a `docToken` URL.

Commands (`cmd_list_students`, `cmd_report_card`, etc.) are thin wrappers that get credentials, resolve the student, call `ParentVUEClient`, and format output.

`resolve_student()` handles the `--student` flag: matches by name substring or permanent ID from the child list.

## Conventions

- Keep it as a single file. No package, no setup.py, no pyproject.toml unless the project grows significantly.
- Credentials must never be hardcoded or logged. Use env vars or interactive prompt only.
- Report card PDFs are downloaded directly via authenticated session (docToken URLs).
- The `--student` flag does case-insensitive substring matching on the child's name, or exact match on permanent student ID.
- Quarter matching for report cards is fuzzy: accepts "Quarter 1", "Q1", "Qtr 1", "MP1", etc.
- The `grades` command was removed when the SOAP API was deprecated. It can be re-added if the web interface exposes gradebook data.

## Testing

No automated tests yet. Manual verification:

```bash
python3 parentvue.py list-students
python3 parentvue.py list-report-cards --student "FirstName"
python3 parentvue.py report-card --student "FirstName" --quarter 3 --output-dir ./reports
```

## API history

The Synergy SOAP API (`PXPCommunication.asmx`) was deprecated by Edupoint in July 2026 when the new ParentVUE mobile app replaced the old one. The SOAP endpoint returns `RT_ERROR` with code D5517. Web access was unaffected, so the CLI now uses web scraping.

Community references for the old SOAP API (no longer functional for many districts):
- https://github.com/StudentVue/docs -- SOAP method documentation
- https://github.com/aramshiva/student -- TypeScript implementation
- https://github.com/StudentVue/StudentVue.py -- Python library (pip package `studentvue`)
