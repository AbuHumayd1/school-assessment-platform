# Slice 5B — Submissions, results and client reports

## Architecture and scope

The audit found an existing objective marking engine (`results.services.mark_attempt`),
stored `Result` / `ResultQuestion` values, attempt question/option presentation order,
and audited publication (`publish_result`). These remain authoritative. `pass_mark`
is **raw marks**, captured on the attempt/result. Stored percentage, pass/fail and the
existing A–F grade are reused. No marking engine, model, migration or policy was added.

The Exam Owner workspace now hosts Submissions, Results and Reports, with a participation
summary on Overview. Student Results uses `/results/my/`, replacing preview data. It
shows only the current user's active candidate profiles' released results; no answer
keys or staff marking metadata are returned. Quick completion and its visibility rules
are unchanged; Quick participants need neither User nor email for owner reporting.

## Reporting semantics

`build_assessment_report` is read-only. Population is the union of current eligibility
(effective active group membership, or associated Quick credential) and historical
participants. It includes never-started candidates. Historical participants remain if
membership or candidate status subsequently changes. Specific-candidate assignment is
not implemented in the existing delivery engine; this limitation is explicitly shown.

One candidate row represents the **latest attempt number**, with ID as a deterministic
tie breaker. A previous result is not substituted for a later unfinished attempt.
Staff can inspect a historical finalized submission using its scoped detail URL.
No GET expires, marks, repairs or otherwise writes attempts/results.

- Before the window ends: no attempt = Not started; active attempt = In progress;
  cancelled = Cancelled.
- Finalized submitted = Submitted. Expired = Auto-submitted. A submitted attempt is
  labelled Auto-submitted for integrity only when its recorded integrity event exists.
- After the window ends, no finalized latest attempt = Not submitted, including an
  overdue unfinished attempt. The stored state is unchanged. Unrecorded causes are not
  inferred. The existing engine treats the exact end timestamp as still open.
- `started_count` includes any latest attempt; `submitted_count` includes normal and
  auto-submitted completions. Auto-submitted is also a separate subset count.
- Result statistics use stored results attached to those latest attempts, including
  provisional/withheld results visible to staff. Missing scores remain null/blank.
- Mean/high/low percentage exclude candidates without a result. Pass rate is passed
  results / available results × 100, rounded to two decimals. With no results these
  statistics are null, not zero. Participation and performance stay separate.
- Released means the existing candidate visibility predicate passes, including published
  state/date, institution activation, hidden policy and scheduled release window.

## APIs and authority

All paths are under `/api/v1/assessments/<exam>/` and validate selected active workspace
using the existing role/context resolver before finding the assessment:

| Method | Suffix | Purpose |
| --- | --- | --- |
| GET | `outcomes/` | Participation/performance summary |
| GET | `submissions/` | Participant roster |
| GET | `results/` | Same authoritative roster with scores |
| GET | `submissions/<attempt>/` | Finalized staff response/result breakdown |
| POST | `results/<result>/release/` | Existing admin-only audited publication service |
| GET | `reports/csv/`, `reports/pdf/`, `reports/docx/` | Full unfiltered report |

Collections accept `search` (name/ID), `status`, `sort` and `page`; page size 25.
Sort fields: name, percentage, score, submitted_at; `-` reverses, nulls stay last.
Filters: submission states, passed/failed, released/not_released. Publication filters
match existing results only. Summaries describe the entire exam, not filtered rows.
Admin, examiner and teacher reads reuse existing assessment management authority.
Platform admins and superusers follow existing context rules; Django staff alone grants
no authority. Release is institution/platform admin only and remains governed by the
existing hidden/scheduled policy. Exports have private/no-store responses. Read views
do not append audit events. Candidate endpoints remain separate and answer-free.
Nested question/offered-option reads are institution-scoped too; a malformed historical
foreign reference cannot expose its text/key. Linked results must match the attempt's
institution, assessment and candidate before their values enter any reporting dataset.

## Exports and dependencies

CSV, PDF and DOCX consume the same normalized dataset. All include non-submitters with
blank scores, stored grades/pass-fail, and operational submission status. No question
answers, PINs, internal marking notes or audit data are included. CSV includes timestamps
and candidate publication state, UTF-8 BOM, standard quoting and formula-prefix escaping
(`=`, `+`, `-`, `@`, including leading whitespace). PDF/DOCX include institution/exam/window,
generation date, participation/performance summary and candidate rows, with repeated
table headers and wrapped cells. Dates use institution timezone. No logo is required.

Added `reportlab` for PDF layout and `python-docx` for editable Word tables. Added the
small `arabic-reshaper` and `python-bidi` helpers for Arabic PDF names. DOCX retains logical
Unicode and bidi properties. PDF embeds a local Unicode font: configure
`RESULT_REPORT_FONT` (Django setting or environment path); Windows Arial and Linux
DejaVu Sans are discovered by default. No remote font/image fetching. Missing fonts
produce a real export failure rather than silently dropping Arabic text.

## Performance and limits

Roster queries use latest-attempt subqueries, one batched attempt/result join and a
batched recorded-integrity-event lookup. The latter avoids text-column joins across
legacy MySQL collations; no database collation or schema is changed. They load no
answers or result-question breakdown.
Detail alone batches responses, marks, offered options and question media. The query
count is bounded independently of candidate count. The normalized full roster is
materialized for summary, filtering and pagination; memory/work is O(participants).
This is suitable for hundreds/thousands, but very large cohorts may later need database
aggregation/pagination and streaming/background exports. No advanced analytics/manual
marking was added. Live owner information refreshes on demand, not through polling.
PDF/DOCX report labels are English; names/content support Unicode. Interface labels
support English, bilingual and Arabic RTL through the existing language context.

## Manual acceptance

A. With eligible candidates and no submissions, check roster/counts and blank scores.
B. With one never-started, active and submitted candidate, inspect all status filters.
C. Compare stored scores/pass-fail to Results and summary; check search/sort/pages.
D. Open submitted response detail; verify presentation order, selections, correct
answers, unanswered questions and marks; no duplicate question rows.
E. As a candidate confirm unreleased results are absent; release as an administrator,
refresh Student Results and confirm only that candidate's safe released values appear.
F. Download/open CSV, PDF and Word, compare numbers and blank non-submitter scores,
check long/multiple-page tables and confirm no PINs/answer keys.
G. Check a Quick candidate without email/account appears in all owner views/reports;
complete Quick Exam and verify its original visibility behavior.
H. Test desktop and approximately 390px in English/bilingual/Arabic RTL. Check table
scrolling, filters, modal focus/close, release confirmation and downloads.

Automated DOM/static-markup checks are not a replacement for real browser acceptance.

## Focused manual-acceptance correction

The existing main Submissions, Results and Reports entries were wired to
`PlaceholderPage`. They now open assessment-first centres, retaining the existing
workspace and navigation capability guards. Search is server-side; assessments are
paginated in groups of 25 before loading their summaries. Each card links to the
existing exam section. Reports uses the same CSV/PDF/DOCX endpoints and disables
downloads when there are no reportable results. Download progress and failures are
visible; the API currently returns blobs without response-header metadata, so the
existing safe title-based filename remains the fallback.

One shared read endpoint supports the three centres:
`GET /api/v1/assessments/outcomes/{results|reports|submissions}/?institution=...&search=...&page=...`.
It uses the existing selected active institution resolver and assessment read roles,
never the unscoped legacy Result list. Each summary comes from the same 5B report
dataset; no React score calculation or second reporting engine is introduced.
Unauthorized explicitly selected institutions continue returning the resolver's
404. Teacher visibility of the main Submissions navigation remains unchanged;
exam-level read permissions remain the existing assessment read roles.

Publication summaries now contain `released_count`, `unreleased_count` and
`release_state`: `no_results`, `not_released`, `partially_released`, `released`.
Counts use the latest result per participating candidate and the existing candidate
visibility predicate, including hidden/scheduled visibility. These are derived
values, not stored Assessment flags. No-result averages and pass rates remain null.

Exam Results now has a publication header and primary **Release Results** action.
The confirmation states the number of pending publications and explains visibility
and portal access. Cancel sends no request. Success refreshes the rows, summary and
open detail; failures leave the dialog open for retry. Individual release remains
available on unpublished result rows to authorized administrators. Hidden results
and scheduled results before the release time show an explanation instead of an
action. Overview links now explicitly say View Submissions, View Results and View
Report. Download labels are CSV, PDF and Word.

`POST /api/v1/assessments/<id>/results/release/?institution=...` is an atomic,
administrator-only orchestration of the existing `publish_result` service. It
validates institution/assessment ownership and locks the assessment and eligible
results. Only existing marked results from finalized attempts with consistent
candidate, attempt and institution ownership are considered. It skips already
published results (including their publication timestamp and audit record), calls
the audited service for each remaining result, and reports newly/already published
counts, available result count and refreshed latest-participant publication state.
Hidden/scheduled restrictions are still enforced by that service; a failure rolls
back the whole operation. Zero-result requests safely publish nothing.

Bulk publication includes all valid available historical attempt results for the
selected assessment. The normal reporting population remains one latest attempt per
candidate. Consequently the confirmation's `release_pending_count` and bulk
`results_available` may exceed the latest-participant result count where retakes
exist. This avoids silently leaving an older candidate-visible result unpublished.
The published state shown in the centre/header describes the latest-participant
report population. Already published rows are never republished by the bulk action.

The centres load at most 25 assessments per request. Their query/work budget is
O(assessments on the page + their participant populations), reusing the bounded
roster queries; it is not one query per candidate. Bulk release deliberately calls
the audited publication service per result, so queries/audits grow with pending
result count. It creates no results, finalizes no attempts, changes no scores and
adds no dependency, model or migration. The candidate API remains the existing
own-only released-result whitelist; Quick candidates still need no user/email.

These exam components accept institution, exam, authorization and localization
inputs and do not import StaffLayout. Future Managed Exam presentation can reuse
them. No service modes, entitlements, plan/name/email hacks, fake memberships,
managed-client routes or Platform Admin console are introduced.

### Correction browser acceptance

1. Open main Results, Reports and Submissions. Check real assessments, search,
   truthful empty/participation/performance states and links into each exam section.
2. In an exam with several unreleased results, open Results. Check publication
   state; click Release Results, cancel once, then confirm. Check success, updated
   rows and Released state without a manual refresh.
3. In a partial-publication case, release one row and check the aggregate state.
   Non-admins must have no publication controls. Hidden/future-scheduled results
   must retain their existing restriction.
4. Before/after publication, sign in as the test candidate: unreleased results are
   absent; afterwards only their authorized released values appear, without keys.
5. Download CSV, PDF and Word from the main Reports centre; compare against the
   contextual report and Results. No-result export buttons must be disabled.
6. Repeat at desktop and approximately 390px, English/bilingual/Arabic RTL. Check
   cards, search, badges, wrapped actions, confirmation focus/cancel and downloads.

Browser automation initialization failed with `failed to write kernel assets:
The system cannot find the path specified. (os error 3)`. No ACL/permission
workaround was attempted; final browser appearance remains a manual check.

### Correction validation

- 91 focused backend tests passed (39 correction + 52 existing reporting tests).
- 763 assessment/result/candidate/attempt/Quick/question/import regressions passed.
- 947 full native backend tests passed, with successful process exit.
- 77 focused and 252 full native frontend tests passed.
- Production build passed; the existing >500 kB chunk advisory remains.
- Django check and `makemigrations --check --dry-run` passed; no migration changes.
- Tracked diff and all untracked whitespace checks passed.
- Before/after historical fingerprint matched the previous baseline exactly:
  `50a88e38a6b205144dc8232a46cd8b18f313c1e1dc94ef1fc152634f8e2f5171`.
  This covers all existing assessment/attempt/response/result rows, Questions 10–160
  (151), their 698 options and provenance, Subject 3 and the completed pilot session
  at revision 22. No development data was modified for testing.
- All changes remain unstaged; checkpoint `9eba9b0` and the unrelated pre-existing
  `frontend/src/services/examAdapters.js` modification remain untouched.

## Final result-availability correction

The domain already has two independent fields. Visibility is `hidden` (publication
forbidden), `after_submission` (published results may be visible) or
`scheduled_release` (published results visible only after `end_at`). Publication
mode is `immediate` (publish on marking when the visibility gate permits),
`approval_required` or `manual_release` (mark without publishing). The latter two
currently use the same administrator publication service. Marked is not released.

The dead-end screenshot corresponds to `hidden`, not manual publication. A
read-only audit found all three current development assessments scheduled, hidden,
approval-required and already containing attempts. Their settings are frozen by
existing model/API rules. They were not mutated or backfilled to make acceptance
pass, and the correction does not add a policy-edit exception.

Create/Edit now exposes one **Result availability** control with a question and
policy explanation. The control only maps to the existing fields:

| Product choice | result_visibility | result_release_mode |
| --- | --- | --- |
| When I release them | after_submission | manual_release |
| After they submit | after_submission | immediate |
| After the exam closes | scheduled_release | manual_release |
| Keep results hidden | hidden | approval_required |

Existing combinations load accurately and remain unchanged if the availability
choice is not edited. Legacy after-submission/approval-required displays as manual
publication. Legacy scheduled/immediate still keeps its original mode when saved
unchanged, and its explanation makes clear that results marked before closing need
publication afterwards. There is no background publication job at exam closing.
The new after-close choice explicitly explains both closing and publication gates.
After-submit explains that availability follows marking submitted attempts.

Overview displays the same human-readable availability. Exam Results explains the
active policy. Editable administrator drafts link to
`/app/exams/<id>/edit#result-availability`; the form scrolls/focuses the control once
its asynchronous data is loaded. Started exams explain that settings cannot be
changed and a new draft must be configured before candidates start. Other non-draft
states direct the administrator to Overview and existing workflow actions, without
bypassing approval/edit permissions. Partial publication says **Release Remaining
Results**; fully released results retain no duplicate publication action. Bulk and
individual controls share the same existing visibility gate. The backend service
and candidate own-only published-result whitelist are unchanged.

English, bilingual and Arabic use the existing localization/context and responsive
form/button styles. No production backend file, model, migration, dependency,
permission, API or Quick Exam behavior was changed in this final correction.

### Necessary browser acceptance

1. Use an editable draft with no attempts, or create a new exam through Exams.
   Choose Result availability → When I release them and save. The three current
   historical test assessments cannot be reconfigured under the preserved rules.
2. Complete the normal question/candidate/access/review/schedule workflow, then
   submit/mark a candidate attempt.
3. As administrator, open Exam → Results: Not released, 0 / N Released and Release
   Results. As candidate, confirm the result is absent.
4. Confirm Release Results. Check Released, N / N Released; the candidate can now
   see only their own authorized result. Check remaining/individual publication
   for a partial-publication scenario.
5. On another editable draft choose Keep results hidden or After the exam closes.
   Check accurate policy guidance and Change Result Settings. With attempt history,
   check the locked-state explanation instead of an edit shortcut. Repeat the new
   controls in English/bilingual/Arabic RTL and approximately 390px.

Final availability validation: 107 focused backend/5B tests passed (16 new policy
workflow tests); all 963 native backend tests passed. All 100 focused and 275 full
native frontend tests passed (23 new availability/edit-controller tests).
Production build, Django check, migration consistency and diff/whitespace checks
passed. No production backend or dependency/model/migration change was needed.
The historical before/after fingerprint again matched exactly:
`50a88e38a6b205144dc8232a46cd8b18f313c1e1dc94ef1fc152634f8e2f5171`.
Final browser appearance/focus remains a manual check because browser automation
could not initialize its kernel assets. No permission workaround, stage, commit or
push was performed.
