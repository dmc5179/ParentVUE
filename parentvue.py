#!/usr/bin/env python3
"""CLI tool to pull grades and report cards from LCPS ParentVUE (Synergy SOAP API)."""

import argparse
import base64
import getpass
import html
import os
import re
import sys
import xml.etree.ElementTree as ET

import requests

DEFAULT_DISTRICT = "portal.lcps.org"


class SynergyClient:
    def __init__(self, username, password, district=DEFAULT_DISTRICT):
        self.username = username
        self.password = password
        self.endpoint = f"https://{district}/Service/PXPCommunication.asmx"
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "text/xml; charset=utf-8"})

    def _escape(self, text):
        return html.escape(str(text))

    def _build_envelope(self, method, params_xml="<Parms/>", multi_web=False):
        action = (
            "ProcessWebServiceRequestMultiWeb" if multi_web
            else "ProcessWebServiceRequest"
        )
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <{action} xmlns="http://edupoint.com/webservices/">
      <userID>{self._escape(self.username)}</userID>
      <password>{self._escape(self.password)}</password>
      <skipLoginLog>true</skipLoginLog>
      <parent>true</parent>
      <webServiceHandleName>PXPWebServices</webServiceHandleName>
      <methodName>{method}</methodName>
      <paramStr>{self._escape(params_xml)}</paramStr>
    </{action}>
  </soap12:Body>
</soap12:Envelope>"""

    def _call(self, method, params_xml="<Parms/>", multi_web=False):
        envelope = self._build_envelope(method, params_xml, multi_web)
        resp = self.session.post(self.endpoint, data=envelope.encode("utf-8"))
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns = {
            "soap": "http://www.w3.org/2003/05/soap-envelope",
            "ws": "http://edupoint.com/webservices/",
        }
        action = (
            "ProcessWebServiceRequestMultiWeb" if multi_web
            else "ProcessWebServiceRequest"
        )
        result_tag = f"ws:{action}Result"
        result_el = root.find(f".//soap:Body/ws:{action}/{result_tag}", ns)

        if result_el is None or not result_el.text:
            fault = root.find(".//soap:Body/soap:Fault/soap:Reason/soap:Text", ns)
            msg = fault.text if fault is not None else resp.text[:500]
            raise RuntimeError(f"SOAP call {method} failed: {msg}")

        return ET.fromstring(result_el.text)

    def get_child_list(self):
        xml = self._call(
            "ChildList",
            '<Parms><ChildIntID>0</ChildIntID></Parms>',
            multi_web=True,
        )
        children = []
        for child in xml.iter("Child"):
            children.append({
                "name": child.get("ChildName", ""),
                "id": child.get("AccessGU", ""),
                "perm_id": child.get("ChildPermID", ""),
                "grade": child.get("Grade", ""),
                "school": child.get("OrganizationName", ""),
            })
        if not children and xml.tag == "Child":
            children.append({
                "name": xml.get("ChildName", ""),
                "id": xml.get("AccessGU", ""),
                "perm_id": xml.get("ChildPermID", ""),
                "grade": xml.get("Grade", ""),
                "school": xml.get("OrganizationName", ""),
            })
        return children

    def get_gradebook(self, report_period=None):
        if report_period is not None:
            params = f"<Parms><ReportPeriod>{int(report_period)}</ReportPeriod></Parms>"
        else:
            params = "<Parms/>"
        return self._call("Gradebook", params)

    def get_student_info(self):
        return self._call("StudentInfo")

    def list_report_cards(self):
        xml = self._call("GetReportCardInitialData")
        periods = []
        for rp in xml.iter("ReportingPeriod"):
            periods.append({
                "name": rp.get("ReportingPeriodName", ""),
                "end_date": rp.get("EndDate", ""),
                "document_gu": rp.get("DocumentGU", ""),
                "gu": rp.get("ReportingPeriodGU", ""),
            })
        return periods

    def get_report_card_pdf(self, document_gu):
        params = f"<Parms><DocumentGU>{self._escape(document_gu)}</DocumentGU></Parms>"
        xml = self._call("GetReportCardDocumentData", params)
        b64 = None
        for el in xml.iter():
            if el.tag == "Base64Code" and el.text:
                b64 = el.text
                break
            if el.get("Base64Code"):
                b64 = el.get("Base64Code")
                break
        if not b64:
            doc_data = xml.find(".//DocumentData")
            if doc_data is not None and doc_data.text:
                b64 = doc_data.text
        if not b64:
            raise RuntimeError("No PDF data returned for this report card")
        return base64.b64decode(b64)


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
        print(f"  {c['name']}  ID: {c['perm_id']}  Grade: {c['grade']}  School: {c['school']}")
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


def match_year(end_date, year):
    if year is None:
        return True
    return str(year) in end_date


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
    client = SynergyClient(username, password, args.district)

    children = client.get_child_list()
    if not children:
        print("No children found on this account.")
        return

    print(f"{'Name':<30} {'ID':<12} {'Grade':<8} {'School'}")
    print("-" * 80)
    for c in children:
        print(f"{c['name']:<30} {c['perm_id']:<12} {c['grade']:<8} {c['school']}")


def cmd_grades(args):
    username, password = get_credentials()
    client = SynergyClient(username, password, args.district)

    _student = resolve_student(client, args.student)
    print(f"Student: {_student['name']}\n")

    gb = client.get_gradebook(args.quarter)

    courses_el = gb.find(".//Courses")
    if courses_el is None:
        print("No gradebook data returned.")
        return

    reporting_period = gb.find(".//ReportingPeriod")
    if reporting_period is not None:
        rp_name = reporting_period.get("GradePeriod", "")
        start = reporting_period.get("StartDate", "")
        end = reporting_period.get("EndDate", "")
        print(f"Period: {rp_name}  ({start} - {end})\n")

    rp_list = gb.findall(".//ReportPeriod")
    if rp_list:
        print("Available reporting periods:")
        for rp in rp_list:
            idx = rp.get("Index", "")
            name = rp.get("GradePeriod", "")
            start = rp.get("StartDate", "")
            end = rp.get("EndDate", "")
            print(f"  [{idx}] {name}  ({start} - {end})")
        print()

    print(f"{'Course':<40} {'Period':<6} {'Grade':<8} {'Score'}")
    print("-" * 70)
    for course in courses_el.findall("Course"):
        name = course.get("Title", "")
        period = course.get("Period", "")
        marks = course.find("Marks")
        if marks is None:
            print(f"{name:<40} {period:<6} {'N/A':<8}")
            continue
        for mark in marks.findall("Mark"):
            letter = mark.get("CalculatedScoreString", "")
            raw = mark.get("CalculatedScoreRaw", "")
            mark_name = mark.get("MarkName", "")
            label = f"{name} ({mark_name})" if mark_name else name
            print(f"{label:<40} {period:<6} {letter:<8} {raw}")

    print()
    print("Tip: use --quarter N to select a specific reporting period index.")


def cmd_list_report_cards(args):
    username, password = get_credentials()
    client = SynergyClient(username, password, args.district)

    if args.student:
        _student = resolve_student(client, args.student)
        print(f"Student: {_student['name']}\n")

    periods = client.list_report_cards()
    if not periods:
        print("No report cards found.")
        return

    print(f"{'Period':<30} {'End Date':<14} {'Available'}")
    print("-" * 60)
    for p in periods:
        available = "Yes" if p["document_gu"] else "No"
        print(f"{p['name']:<30} {p['end_date']:<14} {available}")


def cmd_report_card(args):
    username, password = get_credentials()
    client = SynergyClient(username, password, args.district)

    _student = resolve_student(client, args.student)
    print(f"Student: {_student['name']}")

    periods = client.list_report_cards()
    if not periods:
        print("No report cards found.", file=sys.stderr)
        sys.exit(1)

    matches = [
        p for p in periods
        if p["document_gu"]
        and match_quarter(p["name"], args.quarter)
        and match_year(p["end_date"], args.year)
    ]

    if not matches:
        print("\nNo report cards match your criteria. Available:", file=sys.stderr)
        for p in periods:
            avail = "Ready" if p["document_gu"] else "Not available"
            print(f"  {p['name']}  (ends {p['end_date']})  [{avail}]", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or "."
    os.makedirs(output_dir, exist_ok=True)

    for p in matches:
        print(f"\nDownloading: {p['name']} (ends {p['end_date']})...")
        pdf_data = client.get_report_card_pdf(p["document_gu"])

        safe_name = re.sub(r'[^\w\s-]', '', _student["name"]).strip().replace(" ", "_")
        safe_period = re.sub(r'[^\w\s-]', '', p["name"]).strip().replace(" ", "_")
        filename = f"{safe_name}_{safe_period}_{p['end_date'].replace('/', '-')}.pdf"
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

    p_grades = sub.add_parser("grades", help="Show current grades")
    p_grades.add_argument("--student", help="Student name (substring) or ID")
    p_grades.add_argument("--quarter", type=int, help="Reporting period index (0-based)")
    p_grades.add_argument("--year", help="School year (matches against end date)")

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
        "grades": cmd_grades,
        "list-report-cards": cmd_list_report_cards,
        "report-card": cmd_report_card,
    }
    try:
        commands[args.command](args)
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to {args.district}. Check your network.", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
