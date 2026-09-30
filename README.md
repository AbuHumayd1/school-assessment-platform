# School Assessment & Examination Platform

Phase 0 foundation, Phase 1 Question Engine, Phase 2 Assessment Engine, Phase 3 candidate examination sessions, and Phase 4 objective marking and result release for a multi-tenant assessment platform. The separate Book Reading CBT project is frozen and is not part of this codebase.

## Stack and scope

Python, Django 5.2 LTS, Django REST Framework, MySQL 8+, and python-dotenv. The foundation includes accounts, institutions, memberships, candidates, groups, subjects, hierarchical topics, reusable questions/options, and tenant-scoped APIs. The Assessment Engine adds configurable assessments that reuse approved questions. Candidate sessions support attempts, stable question/option ordering, answers, review flags, server-side expiry, resume, and submission. Phase 4 marks objective answers against the attempt's snapshotted marks and pass mark, stores result details, and provides controlled publication/withholding. Analytics, proctoring, manual marking, and later-phase features are not implemented.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, and `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` for a MySQL database.
4. Run `python manage.py makemigrations`, then `python manage.py migrate`.
5. Create an administrator with `python manage.py createsuperuser` (email is the login identity).
6. Start with `python manage.py runserver`; run tests with `python manage.py test`.

API routes are under `/api/v1/`: `institutions/`, `candidates/`, `groups/`, `subjects/`, `topics/`, `questions/`, `assessments/`, `attempts/`, and `results/`; login/logout uses `auth/`. Tenant querysets and role permissions are enforced on the server. Candidate session routes include `attempts/start/`, attempt summary/list, submit, ordered question navigation, answer saving, and review flags. Candidate accounts must be linked to an active Candidate profile; assigned-group membership is required to start. A started attempt consumes an attempt-limit slot even if it later expires. Candidate access modes `specific_candidates` and `access_code` are intentionally unavailable until their eligibility mechanisms exist. Staff can mark completed attempts at `results/attempts/{id}/mark/`; candidates can retrieve only their own published summary. Approval-required and manual-release results require an authorised institution admin to publish them. Hidden results stay unavailable to candidates. Question and assessment configuration used by attempts is protected from application-level edits after an attempt begins.

Security-sensitive lifecycle actions append tenant-scoped `AuditEvent` rows without answer content or authentication secrets. Audit records are read-only in admin. DRF applies a per-user anonymous limit of 120 requests/hour, a 300 starts/hour limit, and 60 submissions/hour plus 60/minute limits for result marking, publishing, and withholding. Routine answer saves, review flags, and navigation are not throttled. The default cache is process-local, so production deployments with multiple workers should configure a shared Django cache for consistent throttling. Production settings require `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`; SSL redirect is enabled by default there, and HSTS can be enabled with `DJANGO_SECURE_HSTS_SECONDS` after HTTPS is confirmed. Development settings do not require HTTPS.
