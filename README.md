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

API routes are under `/api/v1/`: `institutions/`, `candidates/`, `groups/`, `subjects/`, `topics/`, `questions/`, `assessments/`, `attempts/`, and `results/`; login/logout uses `auth/`. Topic, question, and assessment writes derive the institution from one active staff membership. Candidate session routes include `attempts/start/`, attempt summary/list, submit, ordered question navigation, answer saving, and review flags. Candidate accounts must be linked to an active Candidate profile; assigned-group membership is required to start. A started attempt consumes an attempt-limit slot even if it later expires. Candidate access modes `specific_candidates` and `access_code` are not enabled for delivery until their eligibility mechanisms exist. Staff can mark completed attempts at `results/attempts/{id}/mark/`; results are available to staff by tenant, while candidates can only retrieve their own published results through `results/my/` or the result detail route. Approval-required and manual-release results require an authorised institution admin to publish them. Hidden results stay unavailable to candidates.
