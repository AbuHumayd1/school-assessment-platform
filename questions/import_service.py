import csv
import io
import json

from django.db import IntegrityError, transaction
from rest_framework import serializers

from audit.models import AuditEvent
from audit.services import record_event
from subjects.models import Subject
from .models import Question, Topic
from .serializers import QuestionSerializer

REQUIRED_HEADERS = {
    "question_text", "question_type", "difficulty", "marks", "subject_code",
    "options", "correct_options",
}
OPTIONAL_HEADERS = {"topic_name", "explanation", "learning_objective"}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_DATA_ROWS = 5000


class _CachedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Resolve the subject/topic maps preloaded for this import without per-row queries."""

    def __init__(self, *, objects_by_id, **kwargs):
        self.objects_by_id = objects_by_id
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        pk = self.pk_field.to_internal_value(data) if self.pk_field else data
        instance = self.objects_by_id.get(pk)
        if instance is None:
            self.fail("does_not_exist", pk_value=data)
        return instance


def _summary(total_rows, errors, imported_rows=0):
    return {
        "total_rows": total_rows,
        "imported_rows": imported_rows,
        "failed_rows": len(errors),
        "errors": errors,
    }


def _audit_import(*, institution, actor, summary, outcome):
    record_event(
        institution=institution,
        actor=actor,
        event_type=AuditEvent.Type.QUESTION_IMPORT,
        resource=institution,
        metadata={
            "outcome": outcome,
            "total_rows": summary["total_rows"],
            "imported_rows": summary["imported_rows"],
            "failed_rows": summary["failed_rows"],
        },
    )


def _file_error(message):
    return {"row": 1, "errors": {"file": [message]}}


def _parse_json_array(value, *, column, row_errors):
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        row_errors[column] = ["Use a valid JSON array in this CSV cell."]
        return None
    if not isinstance(parsed, list):
        row_errors[column] = ["This CSV cell must contain a JSON array."]
        return None
    return parsed


def _build_question_payload(row, subject, topic, row_errors):
    options = _parse_json_array(row.get("options", ""), column="options", row_errors=row_errors)
    correct_positions = _parse_json_array(
        row.get("correct_options", ""), column="correct_options", row_errors=row_errors,
    )
    if options is None or correct_positions is None:
        return None
    if any(not isinstance(option, str) or not option.strip() for option in options):
        row_errors["options"] = ["Each option must be a non-empty string."]
        return None
    if any(not isinstance(position, int) or isinstance(position, bool) for position in correct_positions):
        row_errors["correct_options"] = ["Correct option positions must be one-based integers."]
        return None
    if len(correct_positions) != len(set(correct_positions)):
        row_errors["correct_options"] = ["Correct option positions must not be repeated."]
        return None
    if any(position < 1 or position > len(options) for position in correct_positions):
        row_errors["correct_options"] = ["Each correct option position must refer to an option in this row."]
        return None

    return {
        "text": row.get("question_text", ""),
        "question_type": row.get("question_type", "").strip(),
        "difficulty": row.get("difficulty", "").strip(),
        "marks": row.get("marks", "").strip(),
        "subject": subject.pk,
        "topic": topic.pk if topic else None,
        "explanation": row.get("explanation") or "",
        "learning_objective": row.get("learning_objective") or "",
        "options": [
            {
                "text": option.strip(),
                "is_correct": index + 1 in correct_positions,
                "order": index + 1,
            }
            for index, option in enumerate(options)
        ],
    }


def import_questions_csv(upload, *, institution, actor):
    """Validate a complete CSV before writing any questions; successful writes are atomic."""
    if upload is None:
        summary = _summary(0, [_file_error("Upload a CSV file in the 'file' field.")])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary

    if getattr(upload, "size", 0) > MAX_FILE_BYTES:
        summary = _summary(0, [_file_error("CSV files must be 5 MiB or smaller.")])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary

    try:
        contents = upload.read()
        if isinstance(contents, bytes):
            if len(contents) > MAX_FILE_BYTES:
                summary = _summary(0, [_file_error("CSV files must be 5 MiB or smaller.")])
                _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
                return summary
            text = contents.decode("utf-8-sig")
        else:
            text = str(contents)
    except (UnicodeDecodeError, OSError):
        summary = _summary(0, [_file_error("The upload must be a UTF-8 CSV file.")])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary

    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    try:
        fieldnames = reader.fieldnames
    except csv.Error:
        fieldnames = None
    if not fieldnames:
        summary = _summary(0, [_file_error("The CSV must include a header row.")])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary

    headers = [header.strip() if header else "" for header in reader.fieldnames]
    reader.fieldnames = headers
    if len(headers) != len(set(headers)):
        summary = _summary(0, [_file_error("CSV column names must be unique.")])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary
    missing = REQUIRED_HEADERS - set(headers)
    unknown = set(headers) - REQUIRED_HEADERS - OPTIONAL_HEADERS
    if missing or unknown:
        details = []
        if missing:
            details.append("Missing required columns: " + ", ".join(sorted(missing)) + ".")
        if unknown:
            details.append("Unsupported columns: " + ", ".join(sorted(unknown)) + ".")
        summary = _summary(0, [_file_error(" ".join(details))])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary

    subjects_by_code = {}
    for subject in Subject.objects.filter(institution=institution).only("id", "code", "institution_id"):
        subjects_by_code.setdefault(subject.code.casefold(), []).append(subject)
    topics_by_subject_name = {}
    for topic in Topic.objects.filter(institution=institution).only("id", "institution_id", "subject_id", "name"):
        topics_by_subject_name.setdefault((topic.subject_id, topic.name.casefold()), []).append(topic)
    subjects_by_id = {subject.pk: subject for matches in subjects_by_code.values() for subject in matches}
    topics_by_id = {topic.pk: topic for matches in topics_by_subject_name.values() for topic in matches}

    pending = []
    errors = []
    total_rows = 0
    try:
        for row_number, row in enumerate(reader, start=2):
            if row is None or all(value is None or not str(value).strip() for value in row.values()):
                continue
            total_rows += 1
            if total_rows > MAX_DATA_ROWS:
                errors.append({"row": row_number, "errors": {"file": [f"CSV files may contain at most {MAX_DATA_ROWS} data rows."]}})
                break

            row_errors = {}
            if None in row:
                row_errors["file"] = ["This row has more values than the header defines."]
            row = {key: value or "" for key, value in row.items() if key is not None}
            for required in REQUIRED_HEADERS:
                if not row.get(required, "").strip():
                    row_errors[required] = ["This field is required."]

            subject = None
            subject_code = row.get("subject_code", "").strip().casefold()
            if subject_code:
                matches = subjects_by_code.get(subject_code, [])
                if len(matches) == 1:
                    subject = matches[0]
                elif not matches:
                    row_errors["subject_code"] = ["No subject with this code exists in the selected institution."]
                else:
                    row_errors["subject_code"] = ["This subject code is ambiguous in the selected institution."]

            topic = None
            topic_name = row.get("topic_name", "").strip()
            if topic_name and subject:
                matches = topics_by_subject_name.get((subject.pk, topic_name.casefold()), [])
                if len(matches) == 1:
                    topic = matches[0]
                elif not matches:
                    row_errors["topic_name"] = ["No topic with this name exists for the selected subject in this institution."]
                else:
                    row_errors["topic_name"] = ["This topic name is ambiguous for the selected subject."]

            payload = None
            if subject and not any(key in row_errors for key in ("options", "correct_options")):
                payload = _build_question_payload(row, subject, topic, row_errors)
            if row_errors:
                errors.append({"row": row_number, "errors": row_errors})
                continue

            serializer = QuestionSerializer(
                data=payload,
                context={"institution": institution, "request": _RequestActor(actor)},
            )
            serializer.fields["subject"] = _CachedPrimaryKeyRelatedField(
                queryset=Subject.objects.none(), objects_by_id=subjects_by_id,
            )
            serializer.fields["topic"] = _CachedPrimaryKeyRelatedField(
                queryset=Topic.objects.none(), objects_by_id=topics_by_id,
                required=False, allow_null=True,
            )
            if not serializer.is_valid():
                errors.append({"row": row_number, "errors": serializer.errors})
            else:
                pending.append((row_number, serializer))
    except csv.Error:
        errors.append({"row": reader.line_num or 1, "errors": {"file": ["The CSV syntax is malformed."]}})

    if total_rows == 0 and not errors:
        errors.append(_file_error("The CSV contains no question rows."))
    if errors:
        summary = _summary(total_rows, errors)
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary

    current_row = None
    try:
        with transaction.atomic():
            for current_row, serializer in pending:
                serializer.save()
            summary = _summary(total_rows, [], imported_rows=len(pending))
            _audit_import(institution=institution, actor=actor, summary=summary, outcome="imported")
    except IntegrityError:
        summary = _summary(total_rows, [{
            "row": current_row,
            "errors": {"database": ["The import could not be committed; no questions were created."]},
        }])
        _audit_import(institution=institution, actor=actor, summary=summary, outcome="rejected")
        return summary
    return summary


class _RequestActor:
    """Minimal request context consumed by QuestionSerializer for its server-set creator."""

    def __init__(self, user):
        self.user = user
