import json
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from rest_framework.exceptions import ValidationError
from questions.docx_parser import parse_docx


class Command(BaseCommand):
    help = 'Parse a local DOCX without creating an import session or Question Bank records.'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, path, **options):
        try:
            with open(path, 'rb') as source:
                document, _ = parse_docx(File(source))
        except (OSError, ValidationError) as error:
            raise CommandError('The document could not be parsed safely.') from error
        report = {'summary':document['summary'], 'document_issues':document['key_errors'], 'sections':[]}
        for section in document['sections']:
            report['sections'].append({'source_title':section['source_title'], 'source_order':section['source_order'],
                'questions':len(section['questions']), 'review_items':[
                    {'id':q['id'],'number':q['source_number'],'source_order':q['source_order'],
                     'readiness':q['readiness'],'errors':q['errors'],'warnings':q['warnings']}
                    for q in section['questions'] if q['readiness']!='ready']})
        self.stdout.write(json.dumps(report,ensure_ascii=True,indent=2))
