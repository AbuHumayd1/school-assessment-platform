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
KEY = re.compile(r'^(?:key|answers?|answers?\s+key|key\s+answers?)\s*:?[\s]*$', re.I)
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
            if q.get('correct_answer') not in labels: errors.append('A valid correct answer is required.')
            if q['question_type'] not in {'multiple_choice', 'true_false'}: errors.append('Choose a supported objective question type.')
            if q['question_type'] == 'true_false' and {o['text'].strip().casefold() for o in q['options']} != {'true', 'false'}: errors.append('True/false requires True and False options.')
            warnings = list(q['source_warnings'])
            if numbers[q['source_number']] > 1: warnings.append('Duplicate source question number; verify the answer manually.')
            if q.get('key_issue'): warnings.append(q['key_issue'])
            if any(e['status'] != 'converted' for e in q['equations']):
                if not q.get('equation_replacement'): errors.append('Equation content requires manual review. Supply a complete replacement or exclude this question.')
            if any(m['status'] != 'converted' for m in q['media']): errors.append('An image could not be converted. Exclude this question; its image must not be omitted.')
            q['errors'], q['warnings'] = errors, list(dict.fromkeys(warnings))
            q['readiness'] = 'error' if errors else 'needs_review' if warnings and not q.get('reviewed') else 'ready'
    document['summary'] = dict(sections_detected=len(document['sections']), questions_detected=len(questions),
        ready_count=sum(q['readiness']=='ready' for q in questions), review_count=sum(q['readiness']=='needs_review' for q in questions),
        error_count=sum(q['readiness']=='error' for q in questions), answers_matched=sum(q.get('correct_answer') in [o['label'] for o in q['options']] for q in questions),
        answers_missing=sum(not q.get('correct_answer') for q in questions),
        answer_key_entries=document.get('answer_key_entries', 0),
        invalid_ambiguous_answers=sum(bool(q.get('key_issue')) for q in questions) + len(document['key_errors']),
        media_detected=document.get('media_count', 0), equations_detected=sum(len(q['equations']) for q in questions),
        unsupported_objects_detected=document.get('unsupported_count', 0))
    return document


def parse_docx(upload):
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
            for order, p in enumerate(body, 1):
                if p.tag in {W+'sectPr', W+'bookmarkStart', W+'bookmarkEnd', W+'proofErr', W+'permStart', W+'permEnd'}: continue
                text, equations = paragraph_content(p)
                if any(len(e.get('source_xml','')) > lim['item_chars'] for e in equations): raise DocxInputError('Equation source size')
                text_count += len(text) + sum(len(e.get('source_xml','')) for e in equations)
                if text_count > lim['content_chars']: raise DocxInputError('Content limit')
                fmt, number = numbering.marker(p)
                is_heading = fmt not in {'lowerLetter', 'upperLetter'} and bool(SECTION.match(text))
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
                if KEY.match(text):
                    if section is None: doc['key_errors'].append({'source_order': order, 'message': 'Answer key has no preceding section.'})
                    key_mode = True
                    continue
                if key_mode:
                    if text:
                        title = re.sub(r'^\d+\.0\s+', '', text).strip().casefold()
                        matching = [s for s in doc['sections'] if re.sub(r'^\d+\.0\s+', '', s['source_title']).strip().casefold() == title]
                        if len(matching) == 1:
                            section = matching[0]
                            continue
                        doc['answer_key_entries'] += 1
                        match = ANSWER.match(text)
                        if match and section is not None: section['key_entries'].append({'number': int(match[1]), 'answer': match[2].upper(), 'source_order': order})
                        elif fmt == 'decimal' and re.fullmatch(r'[A-Za-z]|true|false', text, re.I) and section is not None:
                            section['key_entries'].append({'number': number, 'answer': text.upper(), 'source_order': order})
                        else: doc['key_errors'].append({'source_order': order, 'message': 'Malformed or unassociated answer-key entry.'})
                    continue
                option = OPTION.match(text)
                question = QUESTION.match(text) if fmt not in {'lowerLetter', 'upperLetter'} else None
                if media and not text and not equations:
                    if fmt in {'lowerLetter', 'upperLetter'} and current:
                        pending.extend(media)
                        current['source_warnings'].append('An image between questions has ambiguous association; review both neighboring questions.')
                        pending.append({'warning': 'Image occurs on an option-numbered paragraph; verify its association against the original.'})
                        continue
                    pending.extend(media)
                    continue
                if fmt == 'decimal' or question:
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
                    doc['key_errors'].append({'source_order': order, 'message': 'Content outside a recognized question requires source review.'})
            if pending:
                doc['key_errors'].append({'source_order': len(body), 'message': 'Unassociated media requires source review.'})
            for section in doc['sections']:
                for q in section['questions']:
                    entries = [e for e in section['key_entries'] if e['number'] == q['source_number']]
                    if len(entries) == 1:
                        answer = entries[0]['answer']
                        if answer in {'TRUE', 'FALSE'}:
                            matches = [o['label'] for o in q['options'] if o['text'].strip().upper() == answer]
                            answer = matches[0] if len(matches) == 1 else answer
                        q['correct_answer'] = answer
                        if answer not in [o['label'] for o in q['options']]: q['key_issue'] = 'Answer key refers to an unavailable option.'
                    elif len(entries) > 1: q['key_issue'] = 'Duplicate answer-key entry; choose the correct answer manually.'
                    if {o['text'].strip().casefold() for o in q['options']} == {'true', 'false'}: q['question_type'] = 'true_false'
                    q['original'] = {'text': q['text'], 'options': [dict(o) for o in q['options']], 'correct_answer': q['correct_answer'], 'question_type': q['question_type']}
                known = {q['source_number'] for q in section['questions']}
                for entry in section['key_entries']:
                    if entry['number'] not in known: doc['key_errors'].append({'source_order': entry['source_order'], 'message': 'Answer references a nonexistent question.'})
            if not doc['sections'] or not any(s['questions'] for s in doc['sections']): raise DocxInputError('No questions')
            doc['source_document'] = {'filename': posixpath.basename(upload.name.replace('\\', '/'))[:255], 'sha256': hashlib.sha256(data).hexdigest()}
            doc['original_parsed_count'] = sum(len(s['questions']) for s in doc['sections'])
            return validate_preview(doc), assets
    except (ValueError, zipfile.BadZipFile, zlib.error, ET.ParseError, OSError, RuntimeError, OverflowError, KeyError, RecursionError, NotImplementedError) as error:
        log.warning('DOCX import rejected (%s)', str(error) if isinstance(error, DocxInputError) else type(error).__name__)
        raise ValidationError({'file': 'This file is not a supported, valid DOCX within the import limits.'}) from None
