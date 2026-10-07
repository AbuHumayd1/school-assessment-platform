# Focused pre-pilot exam setup correction

This correction continues the unstaged Slice 5B work at checkpoint `9eba9b0`.
Nothing is staged, committed or pushed. The pre-existing `examAdapters.js` file is untouched.

## Domain audit and approved decision

Questions already use `AssessmentQuestion`, with unique assessment/question and
assessment/order constraints. The existing attachment API validates approved,
same-subject, same-institution questions and freezes configuration after attempts.
Removing an attachment does not delete its bank question.

Portal eligibility previously supported only `Assessment.group` and effective
`GroupMembership`. `specific_candidates` was an enum placeholder, excluded from
form options and explicitly unsupported by the owner eligibility endpoint. No
direct-assignment relation existed.

The approved migration `assessments/0004_assessment_candidate.py` creates only
`AssessmentCandidate`: assessment FK (CASCADE), candidate FK (PROTECT), assigned_by
FK (PROTECT), assigned_at, and the normal primary key. It adds
`unique_assessment_candidate` on assessment/candidate. Django supplies FK indexes;
there is no redundant additional index. No historical backfill or data update is
included. The migration was applied successfully to the development database;
the assignment table remains empty until owners assign candidates themselves.

Eligibility strategies remain alternatives: assigned_group uses effective group
membership; specific_candidates uses direct assignments. There is no group/direct
eligibility union. Reports continue preserving historical participants in addition
to the currently eligible population, as before.

`candidate_access=access_code` remains the legacy enum for Quick delivery, not an
exam code. The actual code is `QuickExamConfiguration.exam_code`. Quick candidate
population, PINs, credentials and sessions continue using the existing Quick
models/services. Direct assignments never replace credentials.

## Workspace behavior

- Create/Edit contains exam configuration and result availability. Eligibility
  and attachment controls live in the contextual workspace. Creation opens
  Questions; saving edits retains Overview. Existing drafts may be incomplete;
  readiness warns and scheduling retains authoritative requirements.
- Questions shows attached items, count, total marks, inspection, order/marks
  edits and safe removal. Add Questions searches approved questions in the saved
  subject, supports pagination and multi-selection, marks attached items, and
  adds a batch atomically using each question's saved bank marks. The empty state
  explains approval and links to Question Bank; search misses are distinguished
  from a subject with no approved questions.
- Attached questions lock the Subject control with an explanation. Existing
  server-side validation rejects a subject mismatch without detaching anything.
- Candidates shows the active strategy and current roster, optional email and
  participation information. Drafts can configure Specific Candidates or a
  required Group/Cohort. Direct selection searches candidate ID or full name,
  uses multi-select and handles duplicate assignment idempotently.
- Direct assignments must be removed before changing strategy. Explicitly saving
  Assigned Group without a group is rejected. A specific-candidate exam needs
  assignments before scheduling. Group membership is managed outside the exam.
- Access explains Candidate Portal separately from eligibility and reuses Quick
  controls. Existing configured Quick exams retain their delivery lock. A draft
  without Quick configuration may switch back to Candidate Portal.
- Overview shows compact configuration, question, active eligible-candidate,
  access, schedule and result-availability readiness with contextual links.
- Existing language-mode architecture supplies English, bilingual and Arabic
  RTL. Pickers wrap, use logical spacing and share the mobile exam form layout.
  Mutation callbacks ignore completion after their workspace/page is disposed.

## APIs and authority

New endpoints under `/api/v1/assessments/{id}/`:

- GET `candidate-assignments/`: paginated active workspace candidate picker,
  optional search and assigned flags.
- POST `candidate-assignments/`: validated, atomic, idempotent selected-ID batch.
- DELETE `candidate-assignments/{candidate_id}/`: safe direct-assignment removal.
- POST `questions/add/`: atomic selected-question attachment batch.

Existing form-options now exposes the implemented specific-candidate strategy.
Question-options accepts an assessment for attached flags. Eligibility includes
direct assignments, optional email, participation flags and active eligible count;
inspection includes bank marks. Reports include directly assigned candidates.

All endpoints resolve the selected workspace through existing tenant authority,
filter server-side and apply read/write roles and draft object permissions. Writes
lock the assessment, the same lock used by attempt start. Assignment removal checks
Attempt and Result history under that lock. Model boundaries also check tenant,
assigning actor, immutable assignment identity and participation protections.
Assignment removal deletes only the relation. New assignments and other setup
writes are blocked after participation starts.

`portal_candidate_is_assigned` supplies the shared authoritative eligibility
predicate used for portal listing validation and attempt start. Portal listing
queries both supported strategies without requiring group membership for direct
assignments. Attempt ownership/detail/list/answer/submission/integrity lookups now
accept both portal strategies while retaining separate Quick session authority and
safe candidate serializers. Schedule, status, institution, candidate activity,
attempt limits, resume behavior, CSRF and result publication remain authoritative.

## Validation and manual acceptance

Final validation passed:

- Broad setup/eligibility/Quick Exam/5B/question-import backend regressions:
  741 tests passed. Final focused setup/owner run: 51 passed; setup/5B run:
  154 passed. The new setup module contains 26 tests, including the complete
  direct-assignment/start/submission/manual-publication/own-result journey.
- Full backend: 989 passed (`--parallel 4`, 910.926 seconds).
- Final focused frontend setup/exams/5B: 120 passed. Full native frontend:
  295 passed. Production build passed; the existing >500 kB chunk advisory remains.
- Django check passed. `makemigrations --check --dry-run`: no additional changes.
  The intentional migration has one CreateModel operation and applied cleanly,
  including during isolated test database creation. No RunPython/backfill.
- `git diff --check` passed. Untracked whitespace check passed for 24 files.
  The index is empty and HEAD remains `9eba9b0`.

All historical rows in the current development baseline, including Quick
credentials/sessions and group memberships, match exactly after validation:
`56592e341b2cc4950eb11c0261c1cf92ea10efad80c3dd06a9a9d33eed43c4f0`.
The original protected pilot fingerprint also matches exactly:
`50a88e38a6b205144dc8232a46cd8b18f313c1e1dc94ef1fc152634f8e2f5171`.
The pilot retains 151 questions, 698 options, provenance and revision 22. The
development assignment table contains zero rows. No TEST001 assignment was seeded.
The protected adapter's byte hash is unchanged.

Files modified in this correction (including existing unstaged/untracked work):

```text
assessments/models.py
assessments/owner_serializers.py
assessments/serializers.py
assessments/test_owner_control.py
assessments/urls.py
assessments/views.py
attempts/services.py
attempts/views.py
candidates/views.py
frontend/src/pages/staff/ExamAccess.jsx
frontend/src/pages/staff/ExamDetailPage.jsx
frontend/src/pages/staff/ExamFormPage.jsx
frontend/src/pages/staff/exam-ui.jsx
frontend/src/pages/staff/exams.css
frontend/src/pages/student/StudentExamsPage.jsx
frontend/tests/exams.test.js
frontend/tests/result-availability.test.js
results/reporting.py
```

Files newly added in this correction:

```text
assessments/eligibility.py
assessments/migrations/0004_assessment_candidate.py
assessments/setup_views.py
assessments/test_setup_workflow.py
docs/exam-setup-workflow-correction.md
frontend/src/pages/staff/ExamSetup.jsx
frontend/src/pages/staff/setup-copy.js
frontend/tests/exam-setup.test.js
```

Manual acceptance A–H:

1. Create `ISLAMIC QUESTIONS`, subject `ISLAMIC QUIZ`, duration 5 minutes, result
   availability **When I release them**, and an appropriate start/end window.
2. **A — Questions:** add one approved same-subject question; verify count 1.
   If none is approved, use Question Bank to approve a legitimate question first.
3. **B — Candidates:** choose Specific Candidates, save eligibility, search
   `TEST001`, select and add; verify the roster without a group.
4. **C — Access:** verify Candidate Portal. Submit for Review, Approve and Schedule
   through the existing Overview workflow; ensure the window is open.
5. **D — Take exam:** sign in as `teststudent@example.com` using the supplied test
   password, find the eligible exam, start and submit.
6. **E — Before release:** confirm Candidate Results does not expose the result.
7. **F/G — Admin Results:** confirm Not released / 0 of 1 and Release Results;
   confirm release, then verify Released / 1 of 1.
8. **H — Candidate:** sign in again; verify only the candidate's own released
   result, without an answer key or other candidate information.

Also visually check desktop, tablet and ~390px, English/bilingual/Arabic RTL,
picker focus/scrolling, group readiness and partial/individual result release.
Browser automation was previously unavailable because kernel assets could not be
initialized; no permissions or ACL workarounds are used. Final visual acceptance
remains manual. Bulk candidate import/credentials, mixed eligibility, service modes
and later slices remain outside this correction.
