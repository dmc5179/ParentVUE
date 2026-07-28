# LCPS ParentVUE CLI

Command-line tool to pull grades and report cards from the Loudoun County Public Schools ParentVUE portal (`portal.lcps.org`).

Uses the Synergy SOAP API (the same API the official ParentVUE mobile app uses) to fetch gradebook data and download report card PDFs.

## Prerequisites

- Python 3.8+
- A ParentVUE account at [portal.lcps.org](https://portal.lcps.org)

## Install dependencies

The only external dependency is `requests`:

```bash
pip install requests
```

All other imports (`argparse`, `xml.etree.ElementTree`, `base64`, `getpass`, etc.) are Python standard library.

## Authentication

The script needs your ParentVUE username and password. Two options:

### Option 1: Environment variables (recommended)

Set `PARENTVUE_USER` and `PARENTVUE_PASS` before running. This keeps credentials out of your shell history.

```bash
# Bash / Zsh
export PARENTVUE_USER="your_username"
export PARENTVUE_PASS="your_password"

# Or inline for a single command
PARENTVUE_USER="your_username" PARENTVUE_PASS="your_password" python3 parentvue.py list-students
```

To persist across sessions, add the exports to `~/.bashrc` or `~/.zshrc`, or use a `.env` file with a tool like `direnv`.

### Option 2: Interactive prompt

If the environment variables are not set, the script prompts for them at runtime. The password input is masked.

```
$ python3 parentvue.py list-students
ParentVUE username: your_username
ParentVUE password:
```

You can also mix the two -- set just `PARENTVUE_USER` in your environment and let the script prompt for the password each time.

## Usage

```
python3 parentvue.py [--district HOSTNAME] <command> [options]
```

### Global options

| Flag | Default | Description |
|------|---------|-------------|
| `--district HOSTNAME` | `portal.lcps.org` | Synergy district hostname. Override if your district uses a different URL. |

### Commands

#### `list-students` -- List children on the account

```bash
python3 parentvue.py list-students
```

Output:

```
Name                           ID           Grade    School
--------------------------------------------------------------------------------
Clark, Jane                    123456       5        Cool Springs Elementary
Clark, John                    123457       8        Belmont Ridge Middle
```

#### `grades` -- Show current grades

```bash
python3 parentvue.py grades [--student NAME_OR_ID] [--quarter N] [--year YYYY]
```

| Flag | Description |
|------|-------------|
| `--student` | Student name (case-insensitive substring match) or permanent student ID. Required if multiple children are on the account. |
| `--quarter` | Reporting period index (0-based, as listed in the output). Omit to show the current/default period. |
| `--year` | Filter by school year (matched against the reporting period end date). |

Examples:

```bash
# Current grades for a specific child
python3 parentvue.py grades --student "Jane"

# Grades for quarter 2
python3 parentvue.py grades --student "Jane" --quarter 2

# Match by student ID instead of name
python3 parentvue.py grades --student 123456

# If you have only one child, --student is optional
python3 parentvue.py grades
```

#### `list-report-cards` -- List available report cards

```bash
python3 parentvue.py list-report-cards [--student NAME_OR_ID]
```

Shows all reporting periods and whether a report card PDF is available for download.

```
Period                         End Date       Available
------------------------------------------------------------
Quarter 1                      11/03/2025     Yes
Quarter 2                      01/24/2026     Yes
Quarter 3                      03/27/2026     Yes
Quarter 4                      06/12/2026     No
```

#### `report-card` -- Download report card PDFs

```bash
python3 parentvue.py report-card [--student NAME_OR_ID] [--quarter N] [--year YYYY] [--output-dir DIR]
```

| Flag | Description |
|------|-------------|
| `--student` | Student name (substring) or permanent ID. |
| `--quarter` | Quarter number (1, 2, 3, or 4). Matches period names like "Quarter 1", "Q1", "Qtr 1", etc. Omit to download all available report cards. |
| `--year` | Filter by year in the period end date (e.g., `2025`, `2026`). |
| `--output-dir` | Directory to save PDFs. Created if it doesn't exist. Defaults to the current directory. |

Examples:

```bash
# Download Q3 report card for Jane
python3 parentvue.py report-card --student "Jane" --quarter 3

# Download all available report cards for the 2025-2026 school year
python3 parentvue.py report-card --student "Jane" --year 2026 --output-dir ./reports

# Download every available report card for every matching period
python3 parentvue.py report-card --student "Jane" --output-dir ./reports
```

PDFs are saved with the naming pattern `{Student_Name}_{Period}_{End_Date}.pdf`, for example:

```
Clark_Jane_Quarter_3_03-27-2026.pdf
```

## Non-LCPS districts

The script defaults to `portal.lcps.org` but works with any district running Synergy/ParentVUE. Pass `--district` to override:

```bash
python3 parentvue.py --district sis.fcps.edu grades --student "Jane"
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Could not connect to portal.lcps.org` | Check your internet connection. The portal must be reachable over HTTPS. |
| `SOAP call ChildList failed` | Verify your username and password are correct. The same credentials you use on the ParentVUE website or app. |
| `No report cards match your criteria` | Run `list-report-cards` first to see what's available. Not all quarters may have PDFs generated yet. |
| `No children found on this account` | Confirm your account is a parent account (not a student account). |

## How it works

The official ParentVUE mobile app communicates with Synergy servers using a SOAP 1.2 API over HTTPS. This script makes the same SOAP calls directly:

- **Authentication:** Username and password are sent in every SOAP request envelope with `<parent>true</parent>` to indicate a parent account.
- **Child list:** Uses `ProcessWebServiceRequestMultiWeb` with the `ChildList` method.
- **Grades:** Calls the `Gradebook` method with an optional `ReportPeriod` parameter.
- **Report cards:** Calls `GetReportCardInitialData` to list available periods, then `GetReportCardDocumentData` to fetch the PDF as base64-encoded data.

The API is not officially documented by Edupoint. It was reverse-engineered by the open-source community. See:

- [StudentVue SOAP API Docs](https://github.com/StudentVue/docs)
- [aramshiva/student](https://github.com/aramshiva/student) (TypeScript/Next.js implementation)
- [StudentVue.py](https://github.com/StudentVue/StudentVue.py) (Python library)
