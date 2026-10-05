"""Bounded, non-executing OOXML parser. No database writes or pilot-specific rules."""
import io
import hashlib
import logging
import posixpath
import re
import zipfile
import zlib
from collections import Counter
from xml.etree import ElementTree as ET

from django.conf import settings
from rest_framework.exceptions import ValidationError

log = logging.getLogger(__name__)
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'v': 'urn:schemas-microsoft-com:vml'}
W, M = '{' + NS['w'] + '}', '{' + NS['m'] + '}'
DEFAULT_LIMITS = dict(upload_bytes=10*1024*1024, uncompressed_bytes=40*1024*1024,
                      members=1000, questions=1000, images=100, image_bytes=5*1024*1024,
                      media_bytes=20*1024*1024, image_pixels=16000000, content_chars=1000000, item_chars=20000)
KEY = re.compile(r'^\s*(?:key|answers?|answers?\s+keys?|keys?\s+answers?|correct\s+answers?|marking\s+keys?)(?:\s*:\s*(.*)|\s*[.!–—-])?\s*$', re.I)
QUESTION = re.compile(r'^\s*(\d+)[.)]\s+(.+)$', re.S)
OPTION = re.compile(r'^\s*([a-e])[.)]\s*(.*)$', re.I | re.S)
SECTION = re.compile(r'^(?:\d+\.0\s+\S|SECTION\s*:\s*\S)', re.I)
DIRECTION = re.compile(r'^(?:directions?|instructions?)\s*:\s*(\S.*)$', re.I | re.S)
ANSWER = re.compile(r'^\s*(\d+)[.)]?\s+([a-z]|true|false)\s*[.]?\s*$', re.I)
REVIEW_WARNING = 'Unsupported Word object detected near this question. Review the original document before importing.'


class DocxInputError(ValueError):
    """Static diagnostic codes only; never include uploaded content in this exception."""


def limits():
    return {**DEFAULT_LIMITS, **getattr(settings, 'DOCX_IMPORT_LIMITS', {})}


def xml(data):
    # ElementTree does not fetch external entities; prohibit all DTD/entity declarations too.
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)', data.replace(b'\x00', b''), re.I):
        raise DocxInputError('DTD')
    return ET.fromstring(data)


def math_text(node):
    """Explicit linear math notation; grouping preserves supported OMML semantics."""
    tag = node.tag.removeprefix(M)
    if node.tag.startswith(W) or tag.endswith('Pr'):
        return ''
    if tag == 't':
        return node.text or ''
    if tag in {'oMath', 'oMathPara', 'r', 'e', 'num', 'den', 'sub', 'sup', 'deg'}:
        return ''.join(math_text(child) for child in node)
    def part(name):
        child = node.find('m:' + name, NS)
        if child is None:
            raise ValueError('Incomplete equation')
        return math_text(child)
    if tag == 'sSub': return f'{part("e")}_({part("sub")})'
    if tag == 'sSup': return f'{part("e")}^({part("sup")})'
    if tag == 'sSubSup': return f'{part("e")}_({part("sub")})^({part("sup")})'
    if tag == 'f': return f'({part("num")})/({part("den")})'
    if tag == 'rad':
        degree = node.find('m:deg', NS)
        return f'root({math_text(degree) if degree is not None else "2"}; {part("e")})'
    raise ValueError('Unsupported equation')


def paragraph_content(p):
    equations = []
    def walk(node):
        if node.tag == M + 'oMath':
            try:
                text = math_text(node)
                equations.append({'representation': text, 'status': 'converted'})
                return text
            except ValueError:
                equations.append({'representation': None, 'status': 'needs_review',
                                  'source_xml': ET.tostring(node, encoding='unicode')})
                return '[Equation content requires manual review.]'
        if node.tag == W + 't': return node.text or ''
        if node.tag in {W + 'tab', W + 'br'}: return '\n' if node.tag.endswith('br') else '\t'
        return ''.join(walk(child) for child in node)
    return walk(p).strip(), equations


class Numbering:
    def __init__(self, root):
        self.definitions, self.counts = {}, {}
        if root is None: return
        abstracts = {n.get(W+'abstractNumId'): n for n in root.findall('w:abstractNum', NS)}
        for num in root.findall('w:num', NS):
            ref = num.find('w:abstractNumId', NS)
            if ref is None or ref.get(W+'val') not in abstracts: continue
            for level in abstracts[ref.get(W+'val')].findall('w:lvl', NS):
                index = level.get(W+'ilvl', '0')
                fmt, start = level.find('w:numFmt', NS), level.find('w:start', NS)
                override = num.find(f'w:lvlOverride[@w:ilvl="{index}"]/w:startOverride', NS)
                self.definitions[(num.get(W+'numId'), index)] = (
                    fmt.get(W+'val') if fmt is not None else '',
                    int((override if override is not None else start).get(W+'val', '1')) if start is not None or override is not None else 1)

    def marker(self, p):
        num = p.find('w:pPr/w:numPr/w:numId', NS)
        level = p.find('w:pPr/w:numPr/w:ilvl', NS)
        if num is None or num.get(W+'val') == '0': return None, None
        key = (num.get(W+'val'), level.get(W+'val', '0') if level is not None else '0')
        fmt, start = self.definitions.get(key, ('unsupported', 1))
        value = self.counts.get(key, start-1) + 1
        self.counts[key] = value
        return fmt, value


def raster_image(data, name):
    """Decode bounded raster/EMF input and emit metadata-free PNG, never SVG/HTML."""
    from PIL import Image
    if posixpath.splitext(name)[1].lower() not in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.emf', '.wmf'}:
        raise ValueError('Unsupported image')
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError:
        raise ValueError('Image dimensions') from None
    with image:
        if image.width * image.height > limits()['image_pixels']: raise ValueError('Image dimensions')
        image.load()
        output = io.BytesIO()
        image.convert('RGBA').save(output, format='PNG')
        result = output.getvalue()
        if len(result) > limits()['image_bytes']: raise ValueError('Image size')
        return result


def validate_preview(document):
    from .answer_keys import valid_labels
    questions = [q for s in document['sections'] for q in s['questions']]
    for section in document['sections']:
        numbers = Counter(q['source_number'] for q in section['questions'])
        for q in section['questions']:
            errors = []
            if not q['text'].strip(): errors.append('Question text is required.')
            if len(q['text']) > limits()['item_chars']: errors.append('Question text exceeds the limit.')
            if not 2 <= len(q['options']) <= 5: errors.append('Use two to five options.')
            if any(not o['text'].strip() or len(o['text']) > limits()['item_chars'] for o in q['options']): errors.append('Every option requires bounded, non-empty text.')
            if any('[Equation content requires manual review.]' in o['text'] for o in q['options']): errors.append('Replace every unresolved option equation with complete mathematical content.')
            labels = [o['label'] for o in q['options']]
            if labels != list('ABCDE')[:len(labels)]: errors.append('Option markers are missing, repeated or out of order.')
            missing_answer = not valid_labels(q)
            if q['question_type'] not in {'multiple_choice', 'multiple_select', 'true_false'}: errors.append('Choose a supported objective question type.')
            if q['question_type'] == 'true_false' and {o['text'].strip().casefold() for o in q['options']} != {'true', 'false'}: errors.append('True/false requires True and False options.')
            warnings = list(q['source_warnings'])
            if missing_answer: warnings.append('Missing answer')
            if numbers[q['source_number']] > 1: warnings.append('Duplicate source question number; verify the answer manually.')
            if q.get('key_issue'): warnings.append(q['key_issue'])
            if any(e['status'] != 'converted' for e in q['equations']):
                if not q.get('equation_replacement'): errors.append('Equation content requires manual review. Supply a complete replacement or exclude this question.')
            if any(m['status'] != 'converted' for m in q['media']): errors.append('An image could not be converted. Exclude this question; its image must not be omitted.')
            q['errors'], q['warnings'] = errors, list(dict.fromkeys(warnings))
            q['readiness'] = 'error' if errors else 'needs_review' if missing_answer or warnings and not q.get('reviewed') else 'ready'
    document['summary'] = dict(sections_detected=len(document['sections']), questions_detected=len(questions),
        ready_count=sum(q['readiness']=='ready' for q in questions), review_count=sum(q['readiness']=='needs_review' for q in questions),
        excluded_count=sum(not q['included'] for q in questions),
        error_count=sum(q['readiness']=='error' for q in questions), answers_matched=sum(bool(valid_labels(q)) for q in questions),
        answers_missing=sum(not valid_labels(q) for q in questions),
        answer_key_entries=document.get('answer_key_entries', 0),
        invalid_ambiguous_answers=sum(bool(q.get('key_issue')) for q in questions) + len(document['key_errors']),
        media_detected=document.get('media_count', 0), equations_detected=sum(len(q['equations']) for q in questions),
        unsupported_objects_detected=document.get('unsupported_count', 0))
    return document


def parse_docx(upload):
    from .answer_keys import ENTRY, entry, recompute_matches, section_name, table_entries
    from .import_reconciliation import initialize_blocks
    lim = limits()
    try:
        if not upload or not getattr(upload, 'name', '').lower().endswith('.docx'): raise DocxInputError('Extension')
        if getattr(upload, 'size', 0) > lim['upload_bytes']: raise DocxInputError('Upload size')
        data = upload.read(lim['upload_bytes']+1)
        if len(data) > lim['upload_bytes']: raise DocxInputError('Upload size')
        archive = zipfile.ZipFile(io.BytesIO(data))
        with archive:
            members = archive.infolist()
            if len(members) > lim['members'] or sum(m.file_size for m in members) > lim['uncompressed_bytes']: raise DocxInputError('Archive limits')
            names = set()
            for m in members:
                path = m.filename
                if path in names or '\\' in path or path.startswith('/') or ':' in path or '..' in path.split('/') or m.flag_bits & 1: raise DocxInputError('Archive path/encryption')
                names.add(path)
                if re.search(r'(vbaproject|\.exe$|\.dll$|\.js$|\.bin$)', path, re.I): raise DocxInputError('Executable part')
            if not {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'} <= names: raise DocxInputError('DOCX structure')
            if archive.testzip() is not None: raise DocxInputError('Archive CRC')
            types = xml(archive.read('[Content_Types].xml'))
            if not any(e.get('PartName') == '/word/document.xml' and e.get('ContentType') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml' for e in types): raise DocxInputError('Document type')
            root = xml(archive.read('word/document.xml'))
            body = root.find('w:body', NS)
            if body is None: raise DocxInputError('Document body')
            numbering = Numbering(xml(archive.read('word/numbering.xml')) if 'word/numbering.xml' in names else None)
            rels = {}
            if 'word/_rels/document.xml.rels' in names:
                for rel in xml(archive.read('word/_rels/document.xml.rels')):
                    if rel.get('TargetMode') != 'External':
                        target = posixpath.normpath(posixpath.join('word', rel.get('Target', '')))
                        if not target.startswith('word/'): raise DocxInputError('Relationship path')
                        rels[rel.get('Id')] = target
            image_names = [name for name in names if name.startswith('word/media/') and not name.endswith('/')]
            if len(image_names) > lim['images']: raise DocxInputError('Image count')
            assets, doc = {}, {'sections': [], 'key_errors': [], 'answer_key_entries': 0, 'media_count': 0, 'unsupported_count': 0}
            current, section, key_mode, pending, text_count = None, None, False, [], 0
            def new_section(title, order):
                if len(title) > 500: raise DocxInputError('Section title size')
                result = {'id': f's{len(doc["sections"])+1}', 'source_title': title, 'source_order': order, 'questions': [], 'key_entries': [], 'directions': ''}
                doc['sections'].append(result)
                return result
            embedded_entries, key_blocks = [], []
            active_key_block = None
            key_section_title = ''
            body_items = list(body)
            def numbering_format(node):
                num = node.find('w:pPr/w:numPr/w:numId', NS)
                level = node.find('w:pPr/w:numPr/w:ilvl', NS)
                return numbering.definitions.get((num.get(W+'val'), level.get(W+'val', '0') if level is not None else '0'), (None,))[0] if num is not None else None
            for order, p in enumerate(body_items, 1):
                if p.tag in {W+'sectPr', W+'bookmarkStart', W+'bookmarkEnd', W+'proofErr', W+'permStart', W+'permEnd'}: continue
                text, equations = paragraph_content(p)
                if any(len(e.get('source_xml','')) > lim['item_chars'] for e in equations): raise DocxInputError('Equation source size')
                text_count += len(text) + sum(len(e.get('source_xml','')) for e in equations)
                if text_count > lim['content_chars']: raise DocxInputError('Content limit')
                fmt, number = numbering.marker(p)
                style = p.find('w:pPr/w:pStyle', NS)
                styled_heading = style is not None and bool(re.match(r'^heading[1-6]$', style.get(W+'val', ''), re.I))
                next_text = paragraph_content(body_items[order])[0] if order < len(body_items) and body_items[order].tag == W+'p' else ''
                next_item = ENTRY.fullmatch(next_text)
                next_answer_like = bool(next_item and re.fullmatch(r'(?:[A-E]|True|False)', next_item[2].strip(), re.I))
                if order < len(body_items) and numbering_format(body_items[order]) == 'decimal':
                    next_answer_like |= bool(re.fullmatch(r'(?:[A-E]|True|False)', next_text.strip(), re.I))
                uncertain_heading = bool(current and current['options'] and text and not ENTRY.match(text) and not OPTION.match(text) and fmt is None and next_answer_like)
                is_heading = fmt not in {'lowerLetter', 'upperLetter'} and not KEY.fullmatch(text) and bool(SECTION.match(text) or styled_heading or uncertain_heading)
                if key_mode and is_heading:
                    # Repeated headings inside a consolidated key reference source sections.
                    # A following question/options block instead starts a real new section.
                    nodes = [node for node in body_items[order:order+8] if node.tag == W+'p' and paragraph_content(node)[0].strip()]
                    following = [paragraph_content(node)[0].strip() for node in nodes]
                    begins_questions = bool(following and (QUESTION.match(following[0]) or numbering_format(nodes[0]) == 'decimal') and any(OPTION.match(value) or numbering_format(node) in {'lowerLetter','upperLetter'} for value,node in zip(following[1:],nodes[1:])))
                    matching = [s for s in doc['sections'] if section_name(s['source_title']) == section_name(text)]
                    if not begins_questions:
                        section = matching[0] if len(matching) == 1 else None
                        key_section_title = '' if section else text
                        if section is None:
                            doc['key_errors'].append({'source_order': order, 'message': 'Answer-key section is unknown or ambiguous; correct affected answers manually.'})
                        continue
                if key_mode and p.tag == W+'tbl':
                    rows = [[''.join(t.text or '' for t in cell.iter(W+'t')) for cell in row.findall('w:tc', NS)] for row in p.findall('w:tr', NS)]
                    try:
                        if any(e.tag.split('}')[-1] in {'object','drawing','pict','oMath','altChunk'} for e in p.iter()):
                            raise ValidationError('Unsupported answer-key object.')
                        items = table_entries(rows)
                        if not items: raise ValidationError('Empty answer-key table.')
                        for item in items:
                            item.update(id=f'embedded-{order}-{len(embedded_entries)}', source_order=order,
                                        section_id=section['id'] if section and not item['section'] else '',
                                        block_id=active_key_block['id'])
                            if len(embedded_entries) >= 2000: raise DocxInputError('Answer entry count')
                            embedded_entries.append(item)
                            active_key_block['entries'].append(item)
                    except ValidationError:
                        doc['key_errors'].append({'source_order': order, 'message': 'Answer-key table requires source review.'})
                        if section and section['questions']: section['questions'][-1]['source_warnings'].append(REVIEW_WARNING)
                    continue
                if p.tag == W+'tbl':
                    rows = [[''.join(t.text or '' for t in cell.iter(W+'t')) for cell in row.findall('w:tc', NS)] for row in p.findall('w:tr', NS)]
                    try:
                        items = table_entries(rows)
                    except ValidationError:
                        items = [entry(row[0] if row else '', ' | '.join(row[1:])) for row in rows[:2000] if any(row)]
                        for item in items: item['diagnostic'] = 'Unrecognized answer-key table row.'
                    block_id = f'table-block-{order}'
                    for index, item in enumerate(items):
                        item.update(id=f'embedded-table-{order}-{index}', block_id=block_id, source_order=order)
                        if any(e.tag.split('}')[-1] in {'object','drawing','pict','oMath','altChunk'} for e in p.iter()):
                            item['diagnostic'] = 'Answer-key object requires manual review.'
                    key_blocks.append(dict(id=block_id, title=f'Table {order}', classification='ignore', uncertain=True,
                                           entries=items, unparsed=[{'text':' | '.join(row)[:1000]} for row in rows[:3]]))
                unsupported = p.tag != W+'p' or fmt == 'unsupported' or any(e.tag.split('}')[-1] in {'anchor', 'object', 'chart', 'relIds', 'altChunk', 'txbxContent'} for e in p.iter())
                media = []
                for e in p.iter():
                    rid = e.get('{'+NS['r']+'}embed') if e.tag == '{'+NS['a']+'}blip' else e.get('{'+NS['r']+'}id') if e.tag == '{'+NS['v']+'}imagedata' else None
                    if not rid: continue
                    doc['media_count'] += 1
                    if doc['media_count'] > lim['images']: raise DocxInputError('Image count')
                    target = rels.get(rid)
                    item = {'id': f'm{doc["media_count"]}', 'source_order': order, 'alt_text': '', 'status': 'needs_review', 'source_name': posixpath.basename(target or '')}
                    if target in names:
                        if archive.getinfo(target).file_size > lim['image_bytes']: raise DocxInputError('Image size')
                        raw = archive.read(target)
                        try:
                            assets[item['id']] = raster_image(raw, target)
                            item['status'] = 'converted'
                        except (OSError, ValueError, SyntaxError, ImportError):
                            # Preserve the bounded original privately for inspection, never serve it as an image.
                            assets[item['id']] = raw
                        if sum(len(binary) for binary in assets.values()) > lim['media_bytes']: raise DocxInputError('Total image size')
                    media.append(item)
                drawing_without_image = any(e.tag.split('}')[-1] in {'drawing', 'pict'} for e in p.iter()) and not media
                unsupported |= drawing_without_image
                if unsupported:
                    doc['unsupported_count'] += 1
                    if current and not is_heading: current['source_warnings'].append(REVIEW_WARNING)
                    elif not is_heading: pending.append({'warning': REVIEW_WARNING})
                # Automatic letter numbering wins over apparent decimal text such as "1.0 µV" in options.
                if is_heading:
                    if pending and current: current['source_warnings'].append('Media association is ambiguous at the section boundary.')
                    section, current, key_mode = new_section(text, order), None, False
                    pending.extend(media)
                    if unsupported: pending.append({'warning': REVIEW_WARNING})
                    continue
                direction = DIRECTION.match(text)
                if direction and section is not None and current is None and not key_mode and not unsupported and not media and not equations and fmt is None:
                    value = direction[1].strip()
                    combined = '\n'.join(filter(None, [section['directions'], value]))
                    if len(combined) > lim['item_chars']: raise DocxInputError('Directions size')
                    section['directions'] = combined
                    continue
                key_heading = KEY.fullmatch(text)
                if key_heading:
                    key_section_title = key_heading[1].strip() if key_heading[1] else ''
                    if key_heading[1]:
                        matching = [s for s in doc['sections'] if section_name(s['source_title']) == section_name(key_heading[1])]
                        section = matching[0] if len(matching) == 1 else None
                    elif len(doc['sections']) > 1:
                        scoped = {e.get('section_id') for e in embedded_entries}
                        # A subsequent question section closes a local question/key block.
                        # Without that boundary, an unqualified consolidated key cannot
                        # inherit the last section while earlier sections lack key context.
                        closes_local_block = False
                        for next_index in range(order, len(body_items)):
                            node = body_items[next_index]
                            title = paragraph_content(node)[0]
                            style_node = node.find('w:pPr/w:pStyle', NS)
                            if not (SECTION.match(title) or style_node is not None and re.match(r'^heading[1-6]$', style_node.get(W+'val', ''), re.I)):
                                continue
                            following = [n for n in body_items[next_index+1:next_index+9] if n.tag == W+'p' and paragraph_content(n)[0]]
                            if following and (QUESTION.match(paragraph_content(following[0])[0]) or numbering_format(following[0]) == 'decimal') and any(OPTION.match(paragraph_content(n)[0]) or numbering_format(n) in {'lowerLetter','upperLetter'} for n in following[1:]):
                                closes_local_block = True
                                break
                        if not closes_local_block and any(s is not section and s['id'] not in scoped for s in doc['sections']): section = None
                    key_mode, current = True, None
                    active_key_block = dict(id=f'key-block-{order}', title=text[:500], classification='answer_key', uncertain=False, entries=[])
                    key_blocks.append(active_key_block)
                    continue
                if key_mode:
                    if text:
                        matching = [s for s in doc['sections'] if section_name(s['source_title']) == section_name(text)]
                        if matching:
                            section = matching[0] if len(matching) == 1 else None
                            key_section_title = '' if section else text
                            if section is None: doc['key_errors'].append({'source_order': order, 'message': 'Answer-key section is ambiguous; correct affected answers manually.'})
                            continue
                        match = ENTRY.fullmatch(text)
                        if match or fmt == 'decimal':
                            value = match[2].strip() if match else text
                            if re.fullmatch(r'(?:[a-z]|true|false)\.', value, re.I): value = value[:-1]
                            item = entry(match[1] if match else number, value, section=key_section_title if section is None else '',
                                         section_id=section['id'] if section else '', location=f'paragraph {order}')
                            item.update(id=f'embedded-{order}', source_order=order, block_id=active_key_block['id'])
                            if media or equations or unsupported:
                                item['diagnostic'] = 'Answer-key object requires manual review.'
                                active_key_block['uncertain'] = True
                                doc['key_errors'].append({'source_order': order, 'message': 'Answer-key object requires manual review.'})
                            if len(embedded_entries) >= 2000: raise DocxInputError('Answer entry count')
                            embedded_entries.append(item)
                            active_key_block['entries'].append(item)
                        else:
                            doc['key_errors'].append({'source_order': order, 'message': 'Unrecognized answer-key paragraph; review the source block.'})
                            active_key_block['uncertain'] = True
                            active_key_block.setdefault('unparsed', []).append({'source_order':order, 'text':text[:1000]})
                            section = None
                            key_section_title = text[:500]
                    continue
                option = OPTION.match(text)
                question = QUESTION.match(text) if fmt not in {'lowerLetter', 'upperLetter'} else None
                numbered_entry = ENTRY.fullmatch(text) if fmt not in {'lowerLetter', 'upperLetter'} else None
                if not question and numbered_entry and re.fullmatch(r'(?:[A-E]|True|False)', numbered_entry[2].strip(), re.I):
                    question = numbered_entry
                if media and not text and not equations:
                    if fmt in {'lowerLetter', 'upperLetter'} and current:
                        pending.extend(media)
                        current['source_warnings'].append('An image between questions has ambiguous association; review both neighboring questions.')
                        pending.append({'warning': 'Image occurs on an option-numbered paragraph; verify its association against the original.'})
                        continue
                    pending.extend(media)
                    continue
                if fmt == 'decimal' or question:
                    if current and current['options'] and re.fullmatch(r'(?:[A-E]|True|False)', (question[2] if question else text).strip(), re.I):
                        section = new_section('Unclassified numbered block', order)
                    if section is None: section = new_section('Untitled section', order)
                    current = {'id': f'{section["id"]}q{len(section["questions"])+1}', 'source_number': int(question[1]) if question else number,
                        'source_order': order, 'text': question[2] if question else text, 'options': [], 'correct_answer': None,
                        'question_type': 'multiple_choice', 'equations': equations, 'media': media, 'source_warnings': [],
                        'included': True, 'reviewed': False, 'modified': False}
                    for item in pending:
                        if 'warning' in item: current['source_warnings'].append(item['warning'])
                        else:
                            current['media'].append(item)
                            if not re.search(r'\b(above|illustration|sample|figure|diagram)\b', current['text'], re.I): current['source_warnings'].append('Media association is ambiguous; verify against the source document.')
                    pending = []
                    section['questions'].append(current)
                    if sum(len(s['questions']) for s in doc['sections']) > lim['questions']: raise DocxInputError('Question count')
                elif option or fmt in {'lowerLetter', 'upperLetter'}:
                    if current:
                        label = option[1].upper() if option else chr(64+number) if 1 <= number <= 26 else '?'
                        option_text = option[2] if option else text
                        pieces = re.split(r'\s+([b-e])[.)]\s*', option_text, flags=re.I)
                        current['options'].append({'label': label, 'text': pieces[0]})
                        for i in range(1, len(pieces), 2):
                            current['options'].append({'label': pieces[i].upper(), 'text': pieces[i+1]})
                        if len(pieces) > 1: current['source_warnings'].append('Multiple options share a paragraph; verify the detected boundaries.')
                        for equation in equations: equation['option_label'] = label
                        current['equations'].extend(equations)
                        current['media'].extend(media)
                elif media and not text:
                    pending.extend(media)
                elif text and current:
                    if current['options']:
                        current['options'][-1]['text'] += '\n' + text
                        current['source_warnings'].append('Unnumbered continuation after an option; verify its association.')
                    else: current['text'] += '\n' + text
                    current['equations'].extend(equations)
                    current['media'].extend(media)
                elif equations and current:
                    current['equations'].extend(equations)
                elif text or media or equations:
                    doc['key_errors'].append({'source_order': order, 'text': text[:1000], 'message': 'Content outside a recognized question requires source review.'})
            if pending:
                doc['key_errors'].append({'source_order': len(body), 'message': 'Unassociated media requires source review.'})
            for section in doc['sections']:
                for q in section['questions']:
                    if {o['text'].strip().casefold() for o in q['options']} == {'true', 'false'}: q['question_type'] = 'true_false'
                    q['original'] = {'text': q['text'], 'options': [dict(o) for o in q['options']], 'correct_answer': None, 'question_type': q['question_type']}
            doc['embedded_answer_key'] = {'entries': embedded_entries, 'parsed_entry_count': len(embedded_entries),
                                         'source_document': {'filename': 'Embedded answers', 'file_type': 'docx', 'sha256': hashlib.sha256(data).hexdigest()}}
            doc['answer_key_entries'] = len(embedded_entries)
            recompute_matches(doc, 1)
            for s in doc['sections']:
                for q in s['questions']: q['original']['correct_answer'] = q['correct_answer']
            initialize_blocks(doc)
            doc['blocks'].extend(key_blocks)
            if not doc['sections'] or not any(s['questions'] for s in doc['sections']): raise DocxInputError('No questions')
            doc['source_document'] = {'filename': posixpath.basename(upload.name.replace('\\', '/'))[:255], 'sha256': hashlib.sha256(data).hexdigest()}
            doc['original_parsed_count'] = sum(len(s['questions']) for s in doc['sections'])
            return validate_preview(doc), assets
    except (ValueError, zipfile.BadZipFile, zlib.error, ET.ParseError, OSError, RuntimeError, OverflowError, KeyError, RecursionError, NotImplementedError) as error:
        log.warning('DOCX import rejected (%s)', str(error) if isinstance(error, DocxInputError) else type(error).__name__)
        raise ValidationError({'file': 'This file is not a supported, valid DOCX within the import limits.'}) from None
