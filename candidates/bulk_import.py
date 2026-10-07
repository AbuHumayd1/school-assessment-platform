"""Bounded candidate-file parsing and signed, tenant-bound previews. No accounts."""
import csv
import io
import uuid
import zipfile
from xml.etree import ElementTree as ET

from django.core import signing
from rest_framework.exceptions import ValidationError

from .serializers import CandidateSerializer

MAX_ROWS = 1000
MAX_BYTES = 2 * 1024 * 1024
SALT = "candidate-import-v1"
HEADERS = {"first_name", "last_name", "full_name", "candidate_name", "candidate_id", "email"}


def spreadsheet_rows(raw):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 10 * MAX_BYTES:
            raise ValueError("Spreadsheet is too large.")
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(item.itertext()) for item in root.findall("m:si", ns)]
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = book.findall("m:sheets/m:sheet", ns)
        if len(sheets) != 1:
            raise ValueError("Use a workbook with one worksheet.")
        relation_id = sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(item.get("Target") for item in relations if item.get("Id") == relation_id)
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        root = ET.fromstring(archive.read(path))
        rows = []
        for row in root.findall("m:sheetData/m:row", ns):
            values = {}
            for cell in row.findall("m:c", ns):
                if cell.find("m:f", ns) is not None:
                    raise ValueError("Replace spreadsheet formulas with plain values.")
                column = 0
                for letter in cell.get("r", ""):
                    if not letter.isalpha():
                        break
                    column = column * 26 + ord(letter.upper()) - 64
                if not 1 <= column <= 6:
                    raise ValueError("Use only the documented template columns.")
                value = cell.findtext("m:v", "", ns)
                if cell.get("t") == "s":
                    value = strings[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(cell.find("m:is", ns).itertext())
                elif cell.get("t") in {"e", "b"}:
                    raise ValueError("Use plain text candidate details.")
                values[column - 1] = value
            rows.append([values.get(index, "") for index in range(max(values, default=-1) + 1)])
            if len(rows) > MAX_ROWS + 1:
                raise ValueError("Import at most 1000 candidates at a time.")
        return rows


def parse_file(upload):
    if not upload or upload.size > MAX_BYTES:
        raise ValidationError({"file": "Choose a CSV/XLSX file up to 2 MB."})
    raw = upload.read(MAX_BYTES + 1)
    try:
        extension = upload.name.rsplit(".", 1)[-1].lower()
        if extension == "csv":
            rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True))
        elif extension == "xlsx":
            rows = spreadsheet_rows(raw)
        else:
            raise ValueError("Choose a CSV or XLSX file.")
        if not rows or len(rows) > MAX_ROWS + 1:
            raise ValueError("Include a header and at most 1000 candidate rows.")
        headers = [value.strip().lower().replace(" ", "_") for value in rows[0]]
        if len(set(headers)) != len(headers) or not set(headers) <= HEADERS:
            raise ValueError("Use unique documented template column names.")
        if not ({"first_name", "last_name"} <= set(headers) or {"full_name", "candidate_name"} & set(headers)):
            raise ValueError("Include first_name and last_name, or full_name/candidate_name.")
        result = []
        for number, values in enumerate(rows[1:], 2):
            if not any(value.strip() for value in values):
                continue
            if len(values) > len(headers):
                raise ValueError(f"Row {number} has more values than columns.")
            row = dict(zip(headers, [value.strip() for value in values] + [""] * (len(headers) - len(values))))
            name = row.get("full_name") or row.get("candidate_name") or ""
            parts = name.split(maxsplit=1)
            result.append({"row": number, "first_name": row.get("first_name") or (parts[0] if parts else ""),
                           "last_name": row.get("last_name") or (parts[1] if len(parts) > 1 else ""),
                           "candidate_id": row.get("candidate_id", ""), "email": row.get("email", "")})
        if not result:
            raise ValueError("The file has no candidate rows.")
        return result
    except (ValueError, KeyError, StopIteration, IndexError, AttributeError, UnicodeError, csv.Error, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValidationError({"file": f"Invalid candidate file: {exc}"})


def validate_rows(rows, institution, request, generate_ids=False):
    seen_ids, seen_rows, errors, valid = set(), set(), [], []
    for row in rows:
        fields = {key: row[key] for key in ("first_name", "last_name", "candidate_id", "email")}
        signature = tuple(fields.values())
        issues = {}
        if signature in seen_rows:
            issues["row"] = ["Duplicate candidate row."]
        seen_rows.add(signature)
        if fields["candidate_id"]:
            if fields["candidate_id"] in seen_ids:
                issues["candidate_id"] = ["Duplicate candidate ID in this file."]
            seen_ids.add(fields["candidate_id"])
        elif generate_ids:
            fields["candidate_id"] = "C-" + uuid.uuid4().hex.upper()
        serializer = CandidateSerializer(data=fields, context={"institution": institution, "request": request})
        if not serializer.is_valid():
            issues.update(serializer.errors)
        if issues:
            errors.append({"row": row["row"], "errors": issues})
        valid.append({"row": row["row"], **fields})
    return valid, errors


def sign_preview(rows, institution, user):
    return signing.dumps({"rows": rows, "institution": institution.pk, "actor": user.pk}, salt=SALT, compress=True)


def read_preview(token, institution, user):
    try:
        preview = signing.loads(token, salt=SALT, max_age=1800)
        if preview["institution"] != institution.pk or preview["actor"] != user.pk:
            raise signing.BadSignature()
        return preview["rows"]
    except (signing.BadSignature, TypeError, KeyError):
        raise ValidationError({"token": "Preview expired or invalid for this workspace/account. Upload again."})
