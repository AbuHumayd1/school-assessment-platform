# Platform Library — Slice 2

Platform Library content has an explicit platform owner and no institution. Institution banks retain their existing institution owners. No institution is fabricated for the platform, and no existing content is moved.

## Ownership and migration

Subject, Topic and Question have `owner_scope` (`institution` by default, or `platform`). Each has a database check requiring an institution exactly for institution-owned content. Model saves and guarded queryset/bulk writes reject ownership transfer and cross-owner relationships. A topic with questions/children cannot change its subject. The existing Question revision guards remain in place.

Subject retains its institution/code unique constraint. A private, derived nullable `platform_code` unique key and a check tying it to `code` enforce platform code uniqueness on MySQL without conditional indexes. It is not an API field. Topics additionally have a subject/name unique constraint, covering platform topics as well as institution topics.

New migrations:

- `subjects.0002_content_ownership`
- `questions.0005_content_ownership` (ownership only; no SQL triggers)
- `audit.0004_platform_content_context`

Ownership fields default all existing rows to `institution`; institution IDs, row IDs, revision UUIDs/numbers, media, assessment pins and attempt pins are untouched. No platform seed content is created. The audit institution becomes nullable so actual platform resources can be logged without fictitious tenant ownership. Platform audit entries remain hidden from institution audit queries.

The new topic uniqueness constraint assumes existing topics satisfy the pre-existing same-institution/subject invariant. Do not repair data silently if migration detects an existing inconsistency.

## API and browser

Platform-admin authority is the existing `is_platform_administrator` rule, not `is_staff`. It applies to collection, detail and inherited workflow actions. Selected workspace headers cannot change platform ownership.

Routes:

- `/api/v1/platform/library/subjects/` — list/create/detail/update; deactivate via `is_active=false`.
- `/api/v1/platform/library/topics/` — list/create/detail/update; filter by subject; deactivate via `is_active=false`.
- `/api/v1/platform/library/questions/` — shared objective serializer, filtering, pagination, draft/review editing.
- Question detail actions: `submit-for-review`, `request-changes`, `approve`, `archive`, `new-revision`.

Platform requests omit both `institution` and `owner_scope`; the server assigns ownership. Institution endpoints explicitly exclude platform rows and reject ownership input/null institution and platform relationships. Institution CSV/DOCX import paths continue assigning institution ownership. Private platform question media is accessible only to platform administrators.

The platform navigation adds `/platform/library` and `/platform/institution-banks`. Library supports subject creation, subject/topic selection, topic creation, search/type/difficulty/status filters, pagination, question editing, review/approval/archive and revision creation. Institution Banks links to the existing client/workspace workflow, not a mixed question table.

Platform imports, new media upload/import UI, question copying, platform-to-exam attachment, multi-source assessment pickers and `Assessment.library_subject` are deferred. Existing media representation/storage and revision copying are reused. Institution exam attachment still rejects platform questions.

## Manual deployment and acceptance

Run checks/tests in normal PowerShell before applying schema changes if sandbox validation is unavailable. No application database migration is applied by this implementation.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test questions subjects institutions.test_platform tenants.test_security accounts.test_workspace_context assessments.tests assessments.test_bulk_questions assessments.test_bulk_question_removal assessments.test_setup_workflow assessments.test_owner_control attempts.tests --keepdb
python manage.py migrate --plan
python manage.py migrate
```

Use a legitimate Platform Admin account. Do not touch Activus subjects/exams or historical Demo questions.

1. Open Platform Library. Create a disposable subject such as `Slice 2 Acceptance` / `S2-ACC-20261007`. The create request contains only name/code; the response has `institution=null`.
2. Select it, optionally create a disposable topic, then Create question. Enter V1 text and at least two options with the objective type's valid correct-answer configuration. Save; expect Draft / Revision 1.
3. Edit the draft and save. Submit for review; expect In review. Approve; expect Approved / Revision 1 and a content lock.
4. Confirm Edit is disabled. A direct PATCH to its platform question URL with changed text must return 400 and preserve V1.
5. Create new revision. Expect a distinct Question ID, the same revision family, Revision 2 and Draft. Edit V2; retrieve V1 to confirm text/options remain unchanged and its lock persists.
6. Submit/approve V2. V1 remains approved and locked but becomes unavailable for new selections. This intentionally preserves Slice 1 semantics: creating a draft V2 alone does not supersede V1; approving V2 does.
7. Enter a disposable Demo workspace through Institution Banks → Clients → Manage, then Questions. The platform subject/question must be absent. An institution-only user must not see platform navigation and receives 403 from platform library endpoints.
8. Read-only check Activus bank remains institution 3 / subject 5 / 151 questions, Assessment 5 has its 151 distinct question pins, and Assessment 6 retains 10 attachments / 1 attempt / 1 result / 10 attempt question pins. Compare exact pin IDs and rehearsal stored score against the pre-migration snapshot.
9. Retain approved acceptance revisions, archive them if desired, and deactivate the disposable subject/topic using platform PATCH endpoints. Do not bypass immutable-revision deletion guards.

After migration, inspect owners with read-only ORM queries, for example:

```python
from django.db.models import Count
from questions.models import Question, Topic
from subjects.models import Subject
from assessments.models import AssessmentQuestion
from attempts.models import Attempt, AttemptQuestion
from results.models import Result
for model in (Subject, Topic, Question):
    print(model.__name__, list(model.objects.values('owner_scope', 'institution_id').annotate(count=Count('pk')).order_by('owner_scope', 'institution_id')))
print('Activus', list(Question.objects.filter(subject_id=5).values('owner_scope', 'institution_id').annotate(count=Count('pk'))))
print('Exam 5 pins', list(AssessmentQuestion.objects.filter(assessment_id=5).order_by('order', 'pk').values_list('pk', 'question_id')))
print('Exam 6 pins', list(AssessmentQuestion.objects.filter(assessment_id=6).order_by('order', 'pk').values_list('pk', 'question_id')))
print('Exam 6 attempts', list(Attempt.objects.filter(assessment_id=6).values('pk', 'status')))
print('Exam 6 historical questions', list(AttemptQuestion.objects.filter(attempt__assessment_id=6).order_by('pk').values_list('pk', 'question_id')))
print('Exam 6 results', list(Result.objects.filter(assessment_id=6).values('pk', 'marks_obtained', 'total_marks', 'percentage', 'grade', 'passed')))
```

No real acceptance records are automatically created, no cloning command is run, and implementation changes remain unstaged.
