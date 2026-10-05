"""Bounded tabular key readers and conservative, session-only answer matching.

No file is executed, stored, or used to create Question records here.
"""
import copy
import csv
import hashlib
import io
import posixpath
import re
import unicodedata
import zipfile
import zlib
from collections import Counter, defaultdict
from xml.etree import ElementTree as ET

from rest_framework.exceptions import ValidationError

from .docx_parser import KEY, NS, Numbering, W, xml

MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_COLUMNS = 16
MAX_CELL = 1000
BLOCKING_STATES = {'unmatched', 'ambiguous', 'invalid_answer', 'conflict'}
ENTRY = re.compile(r'^\s*(?:question\s*|q\s*)?(\d+)\s*(?:[.):\-–—·•]\s*|\s+)(\S.*)$', re.I)
NUMBER = re.compile(r'^\s*(?:question\s*|q\s*)?(\d+)(?:\.0)?[.):]?\s*$', re.I)
ALIASES = {
    'number': {'question', 'questionno', 'questionnumber', 'no', 'number', 'qno'},
    'answer': {'answer', 'correctanswer', 'key', 'correctoption', 'correctoptions', 'answers'},
    'section': {'section', 'part', 'category', 'sectiontitle', 'sectionname'},
    'section_id': {'sectionid', 'sourcesectionid'},
    'mapping_token': {'questionid', 'previewquestionid', 'mappingtoken'},
}


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def section_name(value):
    value = normalized(value)
    value = re.sub(r'^(?:section\s*:|\d+\.0\s+)', '', value).strip()
    return ' '.join(''.join(' ' if unicodedata.category(c).startswith('P') else c for c in value).split())


def question_number(value):
    match = NUMBER.fullmatch(str(value))
    return int(match[1]) if match and 0 < int(match[1]) <= 1000000 else None


def heading(value, known_sections=()):
    value = str(value).strip()
    if re.match(r'^(?:section\s*:|\d+\.0\s+)', value, re.I):
        if len(value) > 500:
            raise ValueError('Section heading limit')
        return value
    if value and section_name(value) in {section_name(s) for s in known_sections}:
        return value[:500]
    return None


def entry(number, answer, section='', section_id='', location=''):
    item = {'question_number': question_number(number), 'raw_question_number': str(number)[:100], 'answer': str(answer).strip()[:MAX_CELL],
            'section': str(section).strip()[:500], 'section_id': str(section_id).strip()[:100],
            'location': str(location)[:100]}
    if item['question_number'] is None:
        item['diagnostic'] = 'A valid source question number is required.'
    if len(str(section).strip()) > 500 or len(str(section_id).strip()) > 100:
        item['diagnostic'] = 'The source section identifier exceeds the limit.'
    return item


def archive_parts(data, kind):
    archive = zipfile.ZipFile(io.BytesIO(data))
    try:
        infos = archive.infolist()
        if len(infos) > 1000 or sum(i.file_size for i in infos) > 20 * 1024 * 1024:
            raise ValueError('Archive limits')
        names = set()
        for item in infos:
            path = item.filename
            if path in names or '\\' in path or ':' in path or path.startswith('/') or '..' in path.split('/') or item.flag_bits & 1:
                raise ValueError('Archive path')
            if re.search(r'(vbaproject|\.bin$|\.exe$|\.dll$|\.js$)', path, re.I):
                raise ValueError('Executable part')
            names.add(path)
        if '[Content_Types].xml' not in names or '_rels/.rels' not in names:
            raise ValueError('Package structure')
        types = xml(archive.read('[Content_Types].xml'))
        main = '/word/document.xml' if kind == 'docx' else '/xl/workbook.xml'
        expected = ('application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
                    if kind == 'docx' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
        if not any(e.get('PartName') == main and e.get('ContentType') == expected for e in types):
            raise ValueError('Package type')
        for name in names:
            if name.endswith('.rels'):
                relationships = xml(archive.read(name))
                if any(r.get('TargetMode') == 'External' for r in relationships):
                    raise ValueError('External relationship')
        if archive.testzip() is not None:
            raise ValueError('Archive CRC')
        return archive
    except Exception:
        archive.close()
        raise


def table_entries(rows, columns=None, known_sections=()):
    rows = [row for row in rows if any(str(v).strip() for v in row)]
    if not rows:
        return []
    if len(rows) > MAX_ENTRIES + 1 or any(len(row) > MAX_COLUMNS or any(len(str(v)) > MAX_CELL for v in row) for row in rows):
        raise ValidationError({'file': 'The answer key exceeds the row, column or cell limits.'})
    headers = [re.sub(r'[^\w]', '', normalized(v)).replace('_', '') for v in rows[0]]
    recognized = {key: [i for i, h in enumerate(headers) if h in aliases] for key, aliases in ALIASES.items()}
    if columns is not None:
        if not isinstance(columns, dict) or set(columns) - set(ALIASES) or ('answer' not in columns or not {'number','mapping_token'} & set(columns)):
            raise ValidationError({'columns': 'Map Question Number and Answer, with an optional Section.'})
        if any(type(v) is not int or v < 0 or v >= len(headers) for v in columns.values()) or len(set(columns.values())) != len(columns):
            raise ValidationError({'columns': 'Use distinct valid column indexes.'})
        mapping = columns
        # Explicit mapping is a header-row mapping; no guessed header omission.
        rows = rows[1:]
    elif len(recognized['answer']) == 1 and (len(recognized['number']) == 1 or len(recognized['mapping_token']) == 1) and all(len(v) <= 1 for v in recognized.values()):
        mapping = {key: indexes[0] for key, indexes in recognized.items() if indexes}
        rows = rows[1:]
    elif question_number(rows[0][0]) and len(rows[0]) == 2:
        mapping = {'number': 0, 'answer': 1}
    else:
        raise ValidationError({'detail': 'Select the answer-key columns.', 'columns': [str(v)[:100] for v in rows[0]]})
    result, current_section = [], ''
    for index, row in enumerate(rows, 1):
        populated = [str(v).strip() for v in row if str(v).strip()]
        title = heading(populated[0], known_sections) if len(populated) == 1 else None
        if title:
            current_section = title
            continue
        def cell(key, default=''):
            position = mapping.get(key)
            return row[position] if position is not None and position < len(row) else default
        item = entry(cell('number'), cell('answer'), cell('section', current_section), cell('section_id'), f'row {index}')
        item['mapping_token'] = str(cell('mapping_token')).strip()[:100]
        if item['mapping_token'] and item.get('diagnostic') == 'A valid source question number is required.':
            item.pop('diagnostic', None)
        if len(row) > len(headers):
            item['diagnostic'] = 'Extra columns require review; quote comma-separated answers in CSV.'
        result.append(item)
    return result


def docx_entries(archive, known_sections=(), columns=None):
    root = xml(archive.read('word/document.xml'))
    body = root.find('w:body', NS)
    if body is None or len(list(body.iter())) > 100000:
        raise ValueError('Document structure')
    if any(e.tag.split('}')[-1] in {'object', 'altChunk', 'instrText', 'fldChar', 'drawing', 'pict', 'oMath'} for e in body.iter()):
        raise ValueError('Unsupported key object')
    numbering = Numbering(xml(archive.read('word/numbering.xml')) if 'word/numbering.xml' in archive.namelist() else None)
    result, section = [], ''
    for order, element in enumerate(body, 1):
        if element.tag == W + 'tbl':
            rows = [[''.join(t.text or '' for t in cell.iter(W + 't')) for cell in row.findall('w:tc', NS)] for row in element.findall('w:tr', NS)]
            items = table_entries(rows, columns, known_sections)
            for item in items:
                item['section'] = item['section'] or section
                item['location'] = f'table {order}: {item["location"]}'
            result.extend(items)
        elif element.tag == W + 'p':
            text = ''.join(e.text or '' for e in element.iter(W + 't')).strip()
            if not text:
                continue
            if len(text) > MAX_CELL:
                raise ValueError('Paragraph limit')
            key_heading = KEY.fullmatch(text)
            if key_heading:
                if key_heading[1]: section = key_heading[1].strip()
                continue
            fmt, number = numbering.marker(element)
            match = ENTRY.fullmatch(text)
            title = heading(text, known_sections)
            style = element.find('w:pPr/w:pStyle', NS)
            if title or style is not None and re.match(r'^heading[1-6]$', style.get(W+'val', ''), re.I):
                if len(text) > 500:
                    raise ValueError('Section heading limit')
                section = title or text
            elif match:
                result.append(entry(match[1], match[2], section, location=f'paragraph {order}'))
            elif fmt == 'decimal':
                result.append(entry(number, text, section, location=f'paragraph {order}'))
            else:
                result.append({**entry('', text, section, location=f'paragraph {order}'), 'diagnostic': 'Unrecognized answer-key paragraph.'})
        if len(result) > MAX_ENTRIES:
            raise ValueError('Entry limit')
    return result


def xlsx_entries(archive, sheet=None, columns=None, known_sections=()):
    x = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    workbook = xml(archive.read('xl/workbook.xml'))
    definitions = workbook.find(x+'sheets')
    if definitions is None or not 1 <= len(definitions) <= 20:
        raise ValueError('Worksheet limit')
    rels = {e.get('Id'): posixpath.normpath(posixpath.join('xl', e.get('Target', '').lstrip('/'))) if not e.get('Target', '').startswith('/') else e.get('Target').lstrip('/')
            for e in xml(archive.read('xl/_rels/workbook.xml.rels'))}
    strings = []
    if 'xl/sharedStrings.xml' in archive.namelist():
        shared = xml(archive.read('xl/sharedStrings.xml'))
        if len(shared) > MAX_ENTRIES * MAX_COLUMNS:
            raise ValueError('Shared strings limit')
        for item in shared:
            value = ''.join(e.text or '' for e in item.iter(x+'t'))
            if len(value) > MAX_CELL:
                raise ValueError('Cell limit')
            strings.append(value)
    populated = {}
    for definition in definitions:
        target = rels.get(definition.get(r+'id'), '')
        if not target.startswith('xl/worksheets/') or target not in archive.namelist():
            raise ValueError('Worksheet relationship')
        root = xml(archive.read(target))
        if any(e.tag == x+'f' for e in root.iter()):
            raise ValidationError({'file': 'Formula cells are not supported in answer keys.'})
        data = root.find(x+'sheetData')
        rows = []
        if data is not None:
            if len(data) > MAX_ENTRIES + 1:
                raise ValueError('Row limit')
            for row in data:
                values = {}
                for cell in row:
                    address = re.fullmatch(r'([A-Z]+)\d+', cell.get('r', ''))
                    if not address:
                        raise ValueError('Cell address')
                    column = 0
                    for letter in address[1]:
                        column = column*26 + ord(letter)-64
                    if not 1 <= column <= MAX_COLUMNS or column in values:
                        raise ValueError('Column limit')
                    kind, value = cell.get('t', 'n'), cell.find(x+'v')
                    text = value.text or '' if value is not None else ''
                    if kind == 's':
                        index = int(text)
                        if not 0 <= index < len(strings):
                            raise ValueError('Shared string reference')
                        text = strings[index]
                    elif kind == 'inlineStr':
                        text = ''.join(e.text or '' for e in cell.iter(x+'t'))
                    elif kind == 'b':
                        if text not in {'0', '1'}: raise ValueError('Boolean cell')
                        text = 'True' if text == '1' else 'False'
                    elif kind not in {'n', 'str'}:
                        raise ValueError('Unsupported cell')
                    if len(text) > MAX_CELL:
                        raise ValueError('Cell limit')
                    values[column] = text
                if values and any(values.values()):
                    rows.append([values.get(i, '') for i in range(1, max(values)+1)])
        if rows:
            name = definition.get('name', '')
            if name in populated: raise ValueError('Duplicate sheet name')
            populated[name] = rows
    if sheet is None and len(populated) != 1:
        raise ValidationError({'detail': 'Select a populated answer-key worksheet.', 'sheets': list(populated)})
    selected = sheet if sheet is not None else next(iter(populated))
    if selected not in populated:
        raise ValidationError({'sheet': 'Select a populated answer-key worksheet.'})
    return table_entries(populated[selected], columns, known_sections), selected


def parse_answer_key(upload, *, sheet=None, columns=None, known_sections=()):
    if not upload:
        raise ValidationError({'file': 'Choose an answer-key file.'})
    name = posixpath.basename(upload.name.replace('\\', '/'))[:255]
    kind = name.rsplit('.', 1)[-1].lower()
    if kind not in {'docx', 'xlsx', 'csv'}:
        raise ValidationError({'file': 'Use a DOCX, XLSX or CSV answer key.'})
    try:
        data = upload.read(MAX_BYTES+1)
        if not data or len(data) > MAX_BYTES:
            raise ValueError('Upload limit')
        selected = None
        if kind == 'csv':
            text = data.decode('utf-8-sig')
            try:
                delimiter = csv.Sniffer().sniff(text[:4096], delimiters=',;\t').delimiter
            except csv.Error:
                delimiter = ','
            rows = []
            for row in csv.reader(io.StringIO(text), delimiter=delimiter, strict=True):
                if len(rows) >= MAX_ENTRIES+1: raise ValueError('Row limit')
                rows.append(row)
            entries = table_entries(rows, columns, known_sections)
        else:
            with archive_parts(data, kind) as archive:
                if kind == 'docx':
                    entries = docx_entries(archive, known_sections, columns)
                else:
                    entries, selected = xlsx_entries(archive, sheet, columns, known_sections)
        if not entries or len(entries) > MAX_ENTRIES:
            raise ValueError('Entry limit')
        for index, item in enumerate(entries, 1):
            item['id'] = f'k{index}'
        return {'source_document': {'filename': name, 'file_type': kind, 'sha256': hashlib.sha256(data).hexdigest(),
                                    **({'sheet': selected} if selected else {})},
                'parsed_entry_count': len(entries), 'entries': entries, 'matching_version': 1}
    except ValidationError:
        raise
    except (ValueError, OSError, RuntimeError, KeyError, IndexError, zipfile.BadZipFile, csv.Error, UnicodeError, ET.ParseError, zlib.error):
        raise ValidationError({'file': 'This answer key is invalid, unsafe or exceeds the import limits.'}) from None


def valid_labels(question):
    labels = [o['label'] for o in question['options']]
    value = question.get('correct_answer')
    values = value if isinstance(value, list) else [value] if isinstance(value, str) and value else []
    if not values or any(v not in labels for v in values) or len(values) != len(set(values)):
        return ()
    if question['question_type'] != 'multiple_select' and len(values) != 1:
        return ()
    return tuple(label for label in labels if label in values)


def answer_labels(question, value):
    """Exact representations only. Competing letter/text interpretations fail closed."""
    options, kind = question['options'], question['question_type']
    if isinstance(value, list):
        value = ','.join(str(v) for v in value)
    raw = normalized(value)
    text_matches = [o['label'] for o in options if normalized(o['text']) == raw]
    if len(text_matches) > 1:
        return ()
    raw_label = re.sub(r'^option\s+', '', raw).upper()
    representations = []
    if raw_label in [o['label'] for o in options]:
        representations.append((raw_label,))
    if kind == 'multiple_select':
        pieces = re.split(r'\s*(?:,|&|/|\band\b)\s*', raw, flags=re.I)
        values = [re.sub(r'^option\s+', '', p).upper() for p in pieces]
        if values and all(v in [o['label'] for o in options] for v in values):
            representations.append(tuple(o['label'] for o in options if o['label'] in values))
    if kind == 'true_false' and raw in {'true', 'false', 't', 'f'}:
        boolean = 'true' if raw in {'true', 't'} else 'false'
        matches = [o['label'] for o in options if normalized(o['text']) == boolean]
        if len(matches) == 1:
            representations.append(tuple(matches))
    if len(text_matches) == 1:
        representations.append(tuple(text_matches))
    distinct = set(representations)
    return next(iter(distinct)) if len(distinct) == 1 else ()


def assign_answer(question, labels, source):
    question['correct_answer'] = list(labels) if question['question_type'] == 'multiple_select' else labels[0] if labels else None
    question['answer_source'] = source


def recompute_matches(document, revision):
    from .import_reconciliation import canonicalize
    canonicalize(document)
    sources = [(name, document[name]) for name in ('embedded_answer_key', 'separate_answer_key') if document.get(name)]
    key = {'entries': [item for name, source in sources for item in source['entries']]}
    for name, source in sources:
        for item in source['entries']:
            item['source'] = 'embedded_key' if name == 'embedded_answer_key' else 'separate_key'
    if not sources:
        return document
    pairs = [(s, q) for s in document['sections'] for q in s['questions']]
    previous_answers = {q['id']: copy.deepcopy(q.get('correct_answer')) for _, q in pairs}
    questions = {q['id']: (s, q) for s, q in pairs}
    for _, question in pairs:
        if 'answer_baseline' not in question:
            question['answer_baseline'] = copy.deepcopy(question.get('correct_answer'))
            if question.get('correct_answer') != question.get('original', {}).get('correct_answer', question.get('correct_answer')):
                question['answer_source'] = 'manual_review'
        if question.get('answer_source') in {'separate_key', 'embedded_key', 'generated_template', 'manual_link'}:
            question['correct_answer'] = copy.deepcopy(question['answer_baseline'])
            question['answer_source'] = 'baseline'
    targets = defaultdict(list)
    for item in key['entries']:
        for field in ('question_id', 'candidate_ids', 'candidate_count', 'normalized_answer', 'agreement', 'resolved'):
            item.pop(field, None)
        if item.get('excluded'):
            item['status'] = 'excluded'
            continue
        item['rules_considered'] = []
        item.pop('reason', None)
        item.pop('matched_rule', None)
        sections = document['sections']
        if item.get('linked_question_id'):
            rule = 'manual_link'
            candidates = [questions[item['linked_question_id']]] if item['linked_question_id'] in questions else []
            item['reason'] = 'linked_question_not_found' if not candidates else None
        elif item.get('mapping_token'):
            rule = 'generated_template_id'
            candidates = [(s, q) for s, q in pairs if q.get('mapping_token') == item['mapping_token']]
            item['reason'] = 'unknown_or_foreign_question_id' if not candidates else None
        else:
            if item.get('section_id'):
                rule = 'section_identity_number'
                sections = [s for s in sections if item['section_id'] in {s['id'], s.get('section_key')}]
                item['reason'] = 'section_identity_not_found' if not sections else None
            elif item.get('section'):
                rule = 'section_title_number'
                sections = [s for s in sections if section_name(s['source_title']) == section_name(item['section'])]
                item['reason'] = 'section_title_not_found' if not sections else None
            else:
                rule = 'globally_unique_number'
            candidates = [(s, q) for s in sections for q in s['questions'] if item.get('question_number') is not None and q['source_number'] == item['question_number']]
            if len(sections) > 1 and item.get('section'):
                # A colliding title is not an authoritative section identity.
                candidates = [(s, q) for s in sections for q in s['questions'] if q['source_number'] == item['question_number']]
                item['reason'] = 'section_title_ambiguous'
        item['rules_considered'].append(rule)
        item['candidate_ids'] = [q['id'] for _, q in candidates][:50]
        item['candidate_count'] = len(candidates)
        if len(candidates) != 1 or item.get('reason') == 'section_title_ambiguous':
            item['status'] = 'ambiguous' if candidates else 'unmatched'
            item['reason'] = item.get('reason') or ('section_missing_and_number_not_global_unique' if candidates and not item.get('section') else 'multiple_candidate_questions' if candidates else 'question_number_not_found')
            continue
        section, question = candidates[0]
        item['question_id'] = question['id']
        item['matched_rule'] = rule
        item['resolution_source'] = 'manual_answer' if 'answer_override' in item else 'manual_link' if item.get('linked_question_id') else 'automatic'
        labels = answer_labels(question, item.get('answer_override', item['answer']))
        item['normalized_answer'] = list(labels)
        item['status'] = 'matched' if labels and (not item.get('diagnostic') or 'answer_override' in item) else 'invalid_answer'
        if not labels:
            item['reason'] = 'option_text_not_unique' if sum(normalized(o['text']) == normalized(item['answer']) for o in question['options']) > 1 else 'invalid_answer_label'
        targets[question['id']].append(item)
    for question_id, entries in targets.items():
        _, question = questions[question_id]
        manual = valid_labels(question) if question.get('answer_source') == 'manual_review' else ()
        overrides = [tuple(i['normalized_answer']) for i in entries if 'answer_override' in i and i['status'] == 'matched']
        if not manual and question.get('answer_source') != 'manual_review' and overrides and len(set(overrides)) == 1:
            manual = overrides[0]
            assign_answer(question, manual, 'manual_review')
        if manual:
            seen_sources = set()
            for item in entries:
                explicitly_reviewed = question.get('answer_review_revision') == revision or tuple(item.get('manual_answer_resolution', [])) == manual
                if tuple(item.get('normalized_answer', [])) != manual and not explicitly_reviewed:
                    item['status'] = 'conflict'
                    item['reason'] = 'conflicting_existing_answer'
                    continue
                item['manual_answer_resolution'] = list(manual)
                item['status'] = 'duplicate' if item['source'] in seen_sources else 'matched'
                seen_sources.add(item['source'])
                item['resolved'] = True
            continue
        valid = [i for i in entries if i['status'] == 'matched']
        answers = {tuple(i['normalized_answer']) for i in valid}
        existing = valid_labels(question)
        embedded = [i for i in valid if i['source'] == 'embedded_key']
        embedded_answers = {tuple(i['normalized_answer']) for i in embedded}
        if not existing and len(embedded_answers) == 1:
            existing = next(iter(embedded_answers))
            assign_answer(question, existing, 'manual_link' if embedded[0].get('linked_question_id') else 'embedded_key')
        if len(answers) > 1 or answers and existing and next(iter(answers)) != existing:
            for item in valid:
                if item['source'] == 'embedded_key' and len(embedded_answers) == 1: continue
                item['status'] = 'conflict'
                item['reason'] = 'conflicting_existing_answer'
        elif answers:
            labels = next(iter(answers))
            seen_sources = set()
            for item in valid:
                item['status'] = 'duplicate' if item['source'] in seen_sources else 'matched'
                seen_sources.add(item['source'])
                item['agreement'] = bool(existing) or len(valid) > 1
                if item['status'] == 'duplicate': item['resolved'] = True
            if not existing and question.get('answer_source') != 'manual_review':
                source = valid[0]['source']
                if valid[0].get('linked_question_id'): source = 'manual_link'
                elif valid[0].get('mapping_token'): source = 'generated_template'
                assign_answer(question, labels, source)
    document['key_errors'] = [e for e in document.get('key_errors', []) if not e.get('reconciliation')]
    for _, q in pairs:
        q.pop('key_issue', None)
    for name, source in sources:
        if name == 'embedded_answer_key':
            for item in source['entries']:
                if item['status'] == 'invalid_answer' and item.get('question_id') in questions:
                    questions[item['question_id']][1]['key_issue'] = 'Answer key refers to an unavailable option.'
                if item['status'] == 'unmatched' or item['status'] == 'invalid_answer' and not re.fullmatch(r'[A-Z]|TRUE|FALSE', item['answer'].upper()):
                    document['key_errors'].append({'source_order':item.get('source_order',0),'message':'Embedded answer entry requires reconciliation.','reconciliation':True})
        counts = Counter(i['status'] for i in source['entries'])
        source['summary'] = {f'{state}_count': counts[state] for state in ('matched', 'unmatched', 'ambiguous', 'invalid_answer', 'duplicate', 'conflict', 'excluded')}
        source['summary']['needs_review_count'] = sum(counts[s] for s in BLOCKING_STATES | {'duplicate'})
        source['summary']['blocker_count'] = sum(i['status'] in BLOCKING_STATES or i['status'] == 'duplicate' and not i.get('resolved') for i in source['entries'])
        source['summary']['questions_missing_answer'] = sum(q['included'] and not valid_labels(q) for _, q in pairs)
        source['matching_revision'] = revision
    document['reconciliation'] = {'matching_version': 2, 'revision': revision,
        'summary': {key: sum(source['summary'][key] for _, source in sources) for key in sources[0][1]['summary'] if key != 'questions_missing_answer'},
        'questions_missing_answer': sum(q['included'] and not valid_labels(q) for _, q in pairs)}
    for _, q in pairs:
        if q.get('correct_answer') != previous_answers[q['id']]:
            q['review_revision'] = revision
    return document


def replace_key(document, key, revision):
    remove_key(document, revision)
    document['separate_answer_key'] = key
    return recompute_matches(document, revision)


def remove_key(document, revision):
    # Keep explicit question corrections; restore every old automatic assignment.
    for section in document['sections']:
        for q in section['questions']:
            q.pop('answer_manual_entry_id', None)
            if q.get('answer_source') in {'separate_key', 'generated_template', 'manual_link'}:
                q['correct_answer'] = copy.deepcopy(q.get('answer_baseline'))
                q['answer_source'] = 'embedded_key'
            q['review_revision'] = revision
    document.pop('separate_answer_key', None)
    return recompute_matches(document, revision)
