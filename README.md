# School Assessment & Examination Platform

Phase 0 and Phase 1 foundation for a multi-tenant assessment platform. The separate Book Reading CBT project is frozen and is not part of this codebase.

## Stack and scope

Python, Django 5.2 LTS, Django REST Framework, MySQL 8+, and python-dotenv. The foundation includes accounts, institutions, memberships, candidates, groups, subjects, hierarchical topics, reusable questions/options, and tenant-scoped APIs. Assessments, exams, attempts, results, and other later-phase features are not implemented.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, and `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` for a MySQL database.
4. Run `python manage.py makemigrations`, then `python manage.py migrate`.
5. Create an administrator with `python manage.py createsuperuser` (email is the login identity).
6. Start with `python manage.py runserver`; run tests with `python manage.py test`.

API routes are under `/api/v1/`: `institutions/`, `candidates/`, `groups/`, `subjects/`, `topics/`, and `questions/`; login/logout uses `auth/`. Topic and question writes derive the institution from one active staff membership. If the user can manage multiple institutions, select one with the `X-Institution-ID` header or `?institution=` query parameter; the server validates that selection against the user's access. Question status changes use the `submit-for-review/`, `request-changes/`, `approve/`, and `archive/` actions.
