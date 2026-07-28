# LCPS ParentVUE CLI

CLI tool for pulling grades and report cards from the LCPS ParentVUE portal via the Synergy SOAP API.

## Project structure

| File | Purpose |
|------|---------|
| `parentvue.py` | Single-file CLI script. Contains `SynergyClient` (SOAP transport), command implementations, and `argparse` CLI. |
| `README.md` | User-facing usage docs, install instructions, examples. |

## Technical details

- **Language:** Python 3.8+. Single file, no package structure.
- **Dependencies:** `requests` (only external). Everything else is stdlib.
- **API:** Synergy SOAP 1.2 at `https://{district}/Service/PXPCommunication.asmx`. Two SOAP actions: `ProcessWebServiceRequest` (grades, report cards, student info) and `ProcessWebServiceRequestMultiWeb` (child list).
- **Auth:** `<parent>true</parent>` in every SOAP envelope. Credentials via `PARENTVUE_USER`/`PARENTVUE_PASS` env vars or interactive prompt.
- **Default district:** `portal.lcps.org` (Loudoun County Public Schools). Overridable with `--district`.

## Architecture

`SynergyClient` handles all Synergy interaction:
- `_build_envelope()` constructs the SOAP XML with method name, params, and credentials.
- `_call()` sends the request, parses the SOAP response, extracts the inner XML result.
- Public methods (`get_child_list`, `get_gradebook`, `list_report_cards`, `get_report_card_pdf`) wrap specific SOAP method names.

Commands (`cmd_grades`, `cmd_report_card`, etc.) are thin wrappers that get credentials, resolve the student, call `SynergyClient`, and format output.

`resolve_student()` handles the `--student` flag: matches by name substring or permanent ID from the `ChildList` response.

## Conventions

- Keep it as a single file. No package, no setup.py, no pyproject.toml unless the project grows significantly.
- Credentials must never be hardcoded or logged. Use env vars or interactive prompt only.
- XML parsing uses `xml.etree.ElementTree` (stdlib). No lxml dependency.
- Report card PDFs come as base64 from the API; decode and write directly to disk.
- The `--student` flag does case-insensitive substring matching on the child's name, or exact match on permanent student ID.
- Quarter matching for report cards is fuzzy: accepts "Quarter 1", "Q1", "Qtr 1", "MP1", etc.

## Testing

No automated tests yet. Manual verification:

```bash
python3 parentvue.py list-students
python3 parentvue.py grades --student "FirstName"
python3 parentvue.py list-report-cards
python3 parentvue.py report-card --student "FirstName" --quarter 3 --output-dir ./reports
```

## API reference

The Synergy SOAP API is not officially documented. Community references:
- https://github.com/StudentVue/docs -- SOAP method documentation
- https://github.com/aramshiva/student -- TypeScript implementation this script is modeled after
- https://github.com/StudentVue/StudentVue.py -- Python library (pip package `studentvue`)
