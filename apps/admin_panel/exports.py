"""Spreadsheet exports for the admin dashboard (Excel .xlsx and plain CSV)."""

import csv
from datetime import datetime
from io import BytesIO, StringIO

from django.http import HttpResponse
from django.utils import timezone

MEMBER_COLUMNS = [
    ("membership_no", "Membership no"),
    ("full_name", "Full name"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("gender", "Gender"),
    ("role", "Role"),
    ("location", "Location"),
    ("sub_location", "Sub-location"),
    ("occupation", "Occupation"),
    ("status", "Status"),
    ("verified", "Verified"),
    ("created_at", "Registered"),
]

CONTRIBUTION_COLUMNS = [
    ("created_at", "Date"),
    ("member__membership_no", "Membership no"),
    ("member__full_name", "Member"),
    ("amount", "Amount (KSh)"),
    ("method", "Method"),
    ("status", "Status"),
    ("reference", "Reference"),
    ("payment_date", "Payment date"),
]


def _row_value(obj, key):
    value = obj
    for part in key.split("__"):
        value = getattr(value, part, "")
        if value is None:
            return ""
        # get_status_display and friends are functools.partial objects until called.
        if callable(value):
            value = value()
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return value


def _filename(stem, extension):
    return f"{stem}-{timezone.localtime():%Y%m%d-%H%M}.{extension}"


def csv_response(rows, columns, stem):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_row_value(row, key) for key, _ in columns])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{_filename(stem, "csv")}"'
    return response


def xlsx_response(rows, columns, stem):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = stem[:28] or "Export"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="0B4D39")
    for index, (_, label) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=label)
        cell.font = header_font
        cell.fill = header_fill
    for row_index, row in enumerate(rows, start=2):
        for col_index, (key, _) in enumerate(columns, start=1):
            sheet.cell(row=row_index, column=col_index, value=_row_value(row, key))
    for index, (key, label) in enumerate(columns, start=1):
        widest = max([len(label)] + [len(str(_row_value(row, key))) for row in list(rows)[:200]])
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = min(widest + 2, 40)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{_filename(stem, "xlsx")}"'
    return response


def export_members(members, fmt="csv"):
    columns = [("get_" + key + "_display", label) if key == "status" else (key, label) for key, label in MEMBER_COLUMNS]
    rows = list(members)
    return csv_response(rows, columns, "kagan-members") if fmt == "csv" else xlsx_response(rows, columns, "kagan-members")


def export_contributions(contributions, fmt="csv"):
    columns = [
        ("get_" + key + "_display", label) if key in ("method", "status") else (key, label)
        for key, label in CONTRIBUTION_COLUMNS
    ]
    rows = list(contributions)
    return (
        csv_response(rows, columns, "kagan-contributions")
        if fmt == "csv"
        else xlsx_response(rows, columns, "kagan-contributions")
    )
