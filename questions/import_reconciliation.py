"""Session-local identities, reversible source classification and safe XLSX export."""
import copy
import io
import re
import uuid
import zipfile
from xml.etree import ElementTree as ET

from rest_framework.exceptions import ValidationError


def canonicalize(document, namespace=None):
    def token(prefix, value):
        return prefix + (uuid.uuid5(uuid.NAMESPACE_URL, str(namespace)+":"+value).hex if namespace else uuid.uuid4().hex)
    for order, section in enumerate(document['sections'], 1):
        section.setdefault('section_key', token('PS-', section['id']))
        for q in section['questions']:
            q.setdefault('preview_question_id', q['id'])
            q.setdefault('mapping_token', token('PQ-', q['id']))
            q.update(section_key=section['section_key'], section_title=section['source_title'],
                     section_order=order, source_question_number=q['source_number'], document_order=q['source_order'])
    return document


def initialize_blocks(document):
    canonicalize(document)
    if 'blocks' not in document:
        document['blocks'] = [dict(id='block-' + s['id'], title=s['source_title'], classification='questions',
                                   uncertain=any(not q['options'] for q in s['questions']),
                                   section=copy.deepcopy(s)) for s in document['sections']]
    for block in document['blocks']:
        if 'needs_classification' not in block:
            items = block.get('section', {}).get('questions', [])
            block['needs_classification'] = bool(not block.get('classification_revision') and block.get('uncertain') and
                (not block.get('section') and block['classification'] == 'ignore' or
                 items and all(not q['options'] and re.fullmatch(r'[\s·•:.)–—-]*(?:[A-E]|True|False)[.]?', q['text'], re.I) for q in items)))
    return document


def classify_block(document, block_id, classification, revision):
    from .answer_keys import MAX_ENTRIES, entry, recompute_matches
    from .docx_parser import limits
    if not isinstance(classification, str) or classification not in {'questions', 'answer_key', 'ignore'}:
        raise ValidationError({'classification': 'Choose Questions, Answer Key or Ignore.'})
    initialize_blocks(document)
    block = next((b for b in document['blocks'] if b['id'] == block_id), None)
    if block is None:
        raise ValidationError({'block': 'Select a block from this import session.'})
    # Archive current edits before removing a collection; IDs and decisions survive restoration.
    for b in document['blocks']:
        live = next((s for s in document['sections'] if s['id'] == b['section']['id']), None) if b.get('section') else None
        if live:
            b['section'] = copy.deepcopy(live)
        if b['classification'] == 'answer_key':
            b['entries'] = copy.deepcopy([e for e in document.get('embedded_answer_key', {}).get('entries', []) if e.get('block_id') == b['id']])
    block['classification'], block['classification_revision'] = classification, revision
    block['needs_classification'] = False
    if classification == 'questions' and not block.get('section'):
        section = dict(id=block_id, source_title=block['title'], source_order=min((e.get('source_order', 0) for e in block.get('entries', [])), default=0), questions=[], key_entries=[], directions='')
        for i, item in enumerate(block.get('entries', []), 1):
            section['questions'].append(dict(id=f'{block_id}q{i}', source_number=item.get('question_number') or i,
                source_order=item.get('source_order', i), text=item['answer'], options=[], correct_answer=None,
                question_type='multiple_choice', equations=[], media=[], source_warnings=[], included=True,
                reviewed=False, modified=False))
        block['section'] = section
    document['sections'] = [copy.deepcopy(b['section']) for b in document['blocks']
                            if b['classification'] == 'questions' and b.get('section')]
    document['sections'].sort(key=lambda s:s['source_order'])
    if sum(len(s['questions']) for s in document['sections']) > limits()['questions']:
        raise ValidationError({'classification':'The question collection exceeds the import limit.'})
    key = document.setdefault('embedded_answer_key', {'entries': [], 'source_document': document.get('source_document', {})})
    retained = [e for e in key['entries'] if e.get('block_id') != block_id]
    if classification == 'answer_key':
        prior = {e['id']: e for e in key['entries'] if e.get('block_id') == block_id}
        converted = block.get('entries')
        if not converted and block.get('section'):
            converted = []
            from .answer_keys import ENTRY
            for q in block['section']['questions']:
                # The retained item may contain its source marker, or only its body.
                match = ENTRY.fullmatch(q['text'])
                number = match[1] if match else q['source_number']
                answer = match[2] if match else re.sub(r'^[\s·•:.)–—-]+', '', q['text'])
                item = dict(entry(number, answer, location=f"block {block_id}"),
                            id=f"embedded-{q['id']}", block_id=block_id, source_order=q['source_order'])
                if q.get('media') or q.get('equations') or q.get('source_warnings'):
                    item['diagnostic'] = 'Answer-key object requires manual review.'
                converted.append(item)
            block['entries'] = copy.deepcopy(converted)
        for item in converted:
            if len(retained) >= MAX_ENTRIES:
                raise ValidationError({'classification':'The answer key exceeds the entry limit.'})
            item = copy.deepcopy(prior.get(item['id'], item))
            item['block_id'] = block_id
            retained.append(item)
    key['entries'], key['parsed_entry_count'] = retained, len(retained)
    document['answer_key_entries'] = len(retained)
    return recompute_matches(document, revision)


def template_bytes(document):
    """Inline text cells only; no formulas, hidden database IDs, macros or external links."""
    canonicalize(document)
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    package = 'http://schemas.openxmlformats.org/package/2006/relationships'
    root = ET.Element('worksheet', xmlns=ns)
    views = ET.SubElement(root, 'sheetViews')
    view = ET.SubElement(views, 'sheetView', workbookViewId='0')
    ET.SubElement(view, 'pane', ySplit='1', topLeftCell='A2', state='frozen')
    cols = ET.SubElement(root, 'cols')
    for i, width in enumerate([42, 28, 18, 65, 20], 1):
        ET.SubElement(cols, 'col', min=str(i), max=str(i), width=str(width), customWidth='1')
    data = ET.SubElement(root, 'sheetData')
    rows = [['Question ID', 'Section', 'Question Number', 'Question Preview', 'Correct Answer']]
    rows += [[q['mapping_token'], s['source_title'], str(q['source_number']), q['text'][:240], '']
             for s in document['sections'] for q in s['questions'] if q['included']]
    for index, values in enumerate(rows, 1):
        row = ET.SubElement(data, 'row', r=str(index))
        for column, value in enumerate(values):
            text = ''.join(c for c in str(value) if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
            # Defense in depth for spreadsheet programs that reinterpret text on paste/export.
            if text.lstrip().startswith(('=', '+', '-', '@')):
                text = "'" + text
            cell = ET.SubElement(row, 'c', r=f'{chr(65+column)}{index}', t='inlineStr')
            ET.SubElement(ET.SubElement(cell, 'is'), 't').text = text
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels', f'<Relationships xmlns="{package}"><Relationship Id="r1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="Answers" sheetId="1" r:id="r1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{package}"><Relationship Id="r1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr('xl/worksheets/sheet1.xml', ET.tostring(root, encoding='utf-8', xml_declaration=True))
    return stream.getvalue()


def diagnostics(document):
    from .answer_keys import normalized, section_name, valid_labels
    return {'questions': [dict(preview_question_id=q['id'], section_key=s.get('section_key', s['id']),
                              section_title=section_name(s['source_title']), source_question_number=q['source_number'],
                              document_order=q['source_order'], question_type=q['question_type'],
                              option_labels=[o['label'] for o in q['options']], has_authoritative_answer=bool(valid_labels(q)),
                              answer_source=q.get('answer_source')) for s in document['sections'] for q in s['questions']],
            'entries': [dict(id=e['id'], section_identity=e.get('section_id'), raw_section=e.get('section'),
                            normalized_section=section_name(e.get('section', '')), question_number=e.get('question_number'),
                            normalized_answer=normalized(e.get('answer', '')), document_order=e.get('source_order'),
                            parse_status='invalid' if e.get('diagnostic') else 'parsed', status=e.get('status'),
                            reason=e.get('reason'), rules_considered=e.get('rules_considered', []),
                            matched_rule=e.get('matched_rule'), candidate_ids=e.get('candidate_ids', []))
                        for name in ('embedded_answer_key', 'separate_answer_key') for e in document.get(name, {}).get('entries', [])]}
