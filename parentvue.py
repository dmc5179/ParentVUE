#!/usr/bin/env python3
"""CLI tool to pull grades and report cards from LCPS ParentVUE."""

import argparse
import getpass
import json
import os
import re
import sys
from html.parser import HTMLParser

import requests

DEFAULT_DISTRICT = "portal.lcps.org"


class _FormFieldParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden":
            name = attrs.get("name", "")
            value = attrs.get("value", "")
            if name:
                self.fields[name] = value


class ParentVUEClient:
    def __init__(self, username, password, district=DEFAULT_DISTRICT):
        self.username = username
        self.password = password
        self.base_url = f"https://{district}"
        self.session = requests.Session()
        self._logged_in = False

    def _login(self):
        if self._logged_in:
            return
        login_url = f"{self.base_url}/PXP2_Login_Parent.aspx"
        resp = self.session.get(login_url)
        resp.raise_for_status()

        parser = _FormFieldParser()
        parser.feed(resp.text)
        form_data = parser.fields.copy()
        form_data["ctl00$MainContent$username"] = self.username
        form_data["ctl00$MainContent$password"] = self.password
        form_data["ctl00$MainContent$Submit1"] = "Login"

        resp = self.session.post(
            login_url + "?regenerateSessionId=true",
            data=form_data,
            allow_redirects=True,
        )
        resp.raise_for_status()
        if "PXP2_Login" in resp.url:
            raise RuntimeError("Login failed. Check your username and password.")
        self._logged_in = True

    def get_child_list(self):
        self._login()
        resp = self.session.get(f"{self.base_url}/Home_PXP2.aspx")
        resp.raise_for_status()

        children = []
        for m in re.finditer(
            r'"agu"\s*:\s*"(\d+)".*?"name"\s*:\s*"([^"]*)".*?'
            r'"sisNumber"\s*:\s*"([^"]*)".*?"school"\s*:\s*"([^"]*)"',
            resp.text,
            re.DOTALL,
        ):
            children.append({
                "name": m.group(2),
                "id": m.group(1),
                "perm_id": m.group(3),
                "school": m.group(4),
            })
        return children

    def list_documents(self, agu="0"):
        self._login()
        resp = self.session.get(
            f"{self.base_url}/PXP2_Documents.aspx?AGU={agu}"
        )
        resp.raise_for_status()

        for m in re.finditer(r'"dataSource"\s*:\s*(\[.*?\])\s*[,}]', resp.text, re.DOTALL):
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            if not data or not isinstance(data[0], dict) or "DocumentCategory" not in data[0]:
                continue
            docs = []
            for doc in data:
                href_match = re.search(r'href="([^"]+)"', doc.get("DocumentTitle", ""))
                title_match = re.search(r'>([^<]+)<', doc.get("DocumentTitle", ""))
                docs.append({
                    "name": title_match.group(1) if title_match else "",
                    "date": doc.get("DocumentUploadDate", ""),
                    "doc_type": doc.get("DocumentCategory", ""),
                    "download_url": href_match.group(1) if href_match else "",
                })
            return docs
        return []

    def list_report_cards(self, agu="0"):
        docs = self.list_documents(agu)
        return [d for d in docs if "Report Card" in d["doc_type"]]

    def download_document(self, download_url):
        self._login()
        if download_url.startswith("/"):
            url = self.base_url + download_url
        elif download_url.startswith("http"):
            url = download_url
        else:
            url = f"{self.base_url}/{download_url}"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.content


def resolve_student(client, student_filter):
    children = client.get_child_list()
    if not children:
        print("No children found on this account.", file=sys.stderr)
        sys.exit(1)

    if student_filter:
        filt = student_filter.lower()
        matches = [
            c for c in children
            if filt in c["name"].lower() or filt == c["perm_id"].lower()
        ]
        if not matches:
            print(f"No student matching '{student_filter}'. Available:", file=sys.stderr)
            for c in children:
                print(f"  {c['name']} (ID: {c['perm_id']})", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(f"Multiple students match '{student_filter}':", file=sys.stderr)
            for c in matches:
                print(f"  {c['name']} (ID: {c['perm_id']})", file=sys.stderr)
            sys.exit(1)
        return matches[0]

    if len(children) == 1:
        return children[0]

    print("Multiple students on this account. Use --student to pick one:")
    for c in children:
        print(f"  {c['name']}  ID: {c['perm_id']}  School: {c['school']}")
    sys.exit(1)


def match_quarter(period_name, quarter):
    if quarter is None:
        return True
    q = str(quarter)
    name = period_name.lower()
    patterns = [
        f"quarter {q}", f"q{q}", f"qtr {q}", f"qtr{q}",
        f"period {q}", f"mp{q}", f"mp {q}",
        f"semester {q}", f"sem {q}", f"sem{q}",
    ]
    return any(p in name for p in patterns)


def match_year(date_str, year):
    if year is None:
        return True
    return str(year) in date_str


def get_credentials():
    username = os.environ.get("PARENTVUE_USER")
    password = os.environ.get("PARENTVUE_PASS")
    if not username:
        username = input("ParentVUE username: ")
    if not password:
        password = getpass.getpass("ParentVUE password: ")
    return username, password


def cmd_list_students(args):
    username, password = get_credentials()
    client = ParentVUEClient(username, password, args.district)

    children = client.get_child_list()
    if not children:
        print("No children found on this account.")
        return

    print(f"{'Name':<30} {'ID':<12} {'School'}")
    print("-" * 70)
    for c in children:
        print(f"{c['name']:<30} {c['perm_id']:<12} {c['school']}")


def cmd_list_report_cards(args):
    username, password = get_credentials()
    client = ParentVUEClient(username, password, args.district)

    student = resolve_student(client, args.student)
    print(f"Student: {student['name']}\n")

    cards = client.list_report_cards(agu=student["id"])
    if not cards:
        print("No report cards found.")
        return

    print(f"{'Report Card':<50} {'Date':<14} {'Type'}")
    print("-" * 80)
    for c in cards:
        print(f"{c['name']:<50} {c['date']:<14} {c['doc_type']}")


def cmd_report_card(args):
    username, password = get_credentials()
    client = ParentVUEClient(username, password, args.district)

    student = resolve_student(client, args.student)
    print(f"Student: {student['name']}")

    cards = client.list_report_cards(agu=student["id"])
    if not cards:
        print("No report cards found.", file=sys.stderr)
        sys.exit(1)

    matches = [
        c for c in cards
        if c["download_url"]
        and match_quarter(c["name"], args.quarter)
        and match_year(c["date"], args.year)
    ]

    if not matches:
        print("\nNo report cards match your criteria. Available:", file=sys.stderr)
        for c in cards:
            print(f"  {c['name']}  ({c['date']})", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or "."
    os.makedirs(output_dir, exist_ok=True)

    for c in matches:
        print(f"\nDownloading: {c['name']} ({c['date']})...")
        pdf_data = client.download_document(c["download_url"])

        safe_name = re.sub(r'[^\w\s-]', '', student["name"]).strip().replace(" ", "_")
        safe_period = re.sub(r'[^\w\s-]', '', c["name"]).strip().replace(" ", "_")
        filename = f"{safe_name}_{safe_period}_{c['date'].replace('/', '-')}.pdf"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "wb") as f:
            f.write(pdf_data)
        print(f"Saved: {filepath} ({len(pdf_data):,} bytes)")


def main():
    parser = argparse.ArgumentParser(
        description="Pull grades and report cards from LCPS ParentVUE",
        epilog=(
            "Credentials: set PARENTVUE_USER and PARENTVUE_PASS env vars, "
            "or enter them interactively."
        ),
    )
    parser.add_argument(
        "--district", default=DEFAULT_DISTRICT,
        help=f"Synergy district hostname (default: {DEFAULT_DISTRICT})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-students", help="List children on the account")

    p_list_rc = sub.add_parser("list-report-cards", help="List available report cards")
    p_list_rc.add_argument("--student", help="Student name (substring) or ID")

    p_rc = sub.add_parser("report-card", help="Download report card PDFs")
    p_rc.add_argument("--student", help="Student name (substring) or ID")
    p_rc.add_argument("--quarter", help="Quarter number (e.g., 1, 2, 3, 4)")
    p_rc.add_argument("--year", help="School year (matches against end date)")
    p_rc.add_argument("--output-dir", help="Directory to save PDFs (default: current)")

    args = parser.parse_args()

    commands = {
        "list-students": cmd_list_students,
        "list-report-cards": cmd_list_report_cards,
        "report-card": cmd_report_card,
    }
    try:
        commands[args.command](args)
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to {args.district}. Check your network.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 503:
            print(f"ParentVUE ({args.district}) is temporarily unavailable. Try again later.", file=sys.stderr)
        else:
            print(f"HTTP error from {args.district}: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
