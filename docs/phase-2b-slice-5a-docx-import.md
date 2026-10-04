# Slice 5A DOCX question import

## Architecture and scope

DOCX import creates ordinary draft `Question` and `QuestionOption` records. The existing CSV importer, assessment attachment rules, candidate authentication, Quick Exam sessions, Attempt services, marking and result calculations are unchanged. The shared candidate question serializer and React question renderer receive an additive, answer-free media representation.

The repository previously had plain text questions/options and no question media. Staff Questions was a placeholder. The normal CSV importer already validates the entire file before an atomic write. Question content and options become immutable after an Attempt references them. Institution memberships and the existing question-bank write-context resolver remain authoritative.

Schema changes are narrowly additive: `Question.source_metadata` records source section title/order, question number/document order and equation conversion provenance; `DocxImportSession` retains temporary, uploader-owned, institution-scoped preview JSON; `QuestionMedia` owns private files, first through a temporary session and then through a normal question. Migrations: `questions/0002_question_source_metadata_docximportsession_and_more.py` and `0003_alter_questionmedia_import_session_and_more.py`. The latter records child-before-parent deletion, preserving the exactly-one-owner constraint on MySQL without temporarily nulling both owners. Both migrations have been applied to the development database. Topic is not used as a source section. No Attempt model or per-attempt binary copies were added.

## Parsing and security

`questions/docx_parser.py` reads OOXML directly with the standard library. It does not execute Office applications, macros, embedded objects or remote relationships. ZIP paths, duplicate members, encrypted members, extensions, required parts, main document content type and XML DTD/entity declarations are checked. Executable/macro/binary parts are rejected. Unsupported content is flagged for review. Invalid documents return a generic safe validation error; logs contain static rejection codes or exception classes, never answers or document contents.

Defaults can be overridden with `DOCX_IMPORT_LIMITS` in Django settings:

| Limit | Default |
| --- | --- |
| Upload | 10 MiB |
| Total uncompressed ZIP | 40 MiB |
| ZIP members | 1,000 |
| Questions | 1,000 |
| Images | 100 |
| Individual input/output image | 5 MiB |
| Total retained image content | 20 MiB |
| Image dimensions | 16 million pixels |
| Extracted content | 1 million characters |
| Individual question/option | 20,000 characters |

Section identity uses source title plus document order, so repeated section numbers do not merge sections. Explicit numeric markers and OOXML automatic decimal numbering are supported. Explicit a-e markers and automatic letter numbering support two to five options; paragraph continuations preserve authored wording. Multiple options in one paragraph are detected and require review. The importer does not correct spelling, capitalization or medical terminology.

Embedded answer keys support the requested heading variants, explicit numeric mappings and Word automatically numbered entries. Keys attach to preceding sections or an explicitly named, uniquely matching preceding section. Missing, invalid, duplicate, nonexistent and malformed mappings are flagged. Repeated question numbers require manual review. Only single-answer multiple choice and safely recognizable True/False are inferred; multiple select is not inferred.

Equations use explicit, escaped linear mathematical notation within the original prompt/option positions: runs, subscripts, superscripts, combined scripts, fractions and roots. For example, a subscript becomes `R_(1)`, and a fraction becomes `(numerator)/(denominator)`. This is a safe text representation, not raw HTML or arbitrary MathML. Unsupported OMML retains source XML in the private preview and blocks confirmation until the reviewer supplies complete replacement content or excludes the question. Unresolved option equations must also be replaced. No `dangerouslySetInnerHTML` is used.

Pillow is the only new dependency (`Pillow>=11.3,<13.0`). It validates/decodes images and produces bounded, metadata-free PNG output. The pilot's PNG and three EMF files convert on this Windows runtime. EMF/WMF decoding is platform-dependent; unavailable conversion preserves the bounded original privately and blocks that question rather than omitting its image. Images before questions use structural evidence and explicit references such as “above”; weak associations require review. Floating anchors, tables, charts, SmartArt, OLE, text boxes, unknown numbering and unsupported drawings require source review.

## Session and API workflow

Sessions use unpredictable UUID identifiers, a default two-hour expiry (`DOCX_IMPORT_SESSION_SECONDS`), institution membership validation and uploader ownership. Other staff, including another institution administrator, cannot inspect another uploader's preview. Candidates cannot access previews. Raw DOCX uploads are parsed in memory and are not retained permanently.

| Method and route | Purpose |
| --- | --- |
| GET `/api/v1/questions/import/docx/preview/` | Selected institution's subject choices |
| POST `/api/v1/questions/import/docx/preview/` | Multipart DOCX upload and private preview |
| GET `/api/v1/questions/import/docx/<uuid>/` | Retrieve owned, unexpired preview or completion receipt |
| PATCH `/api/v1/questions/import/docx/<uuid>/` | Controlled review edits with revision check |
| POST `/api/v1/questions/import/docx/<uuid>/confirm/` | Confirm current server revision atomically |
| GET `/api/v1/questions/media/<uuid>/` | Authorized staff/preview owner/active candidate Attempt media |
| GET `/api/v1/quick-exam/media/<uuid>/` | Media authorized through the existing Quick session and active Attempt |

Optional subject/topic/difficulty/default marks are not required to parse. A selected, tenant-valid subject is required to confirm. PATCH permits question text, options, keyed answer, supported type, section title, inclusion/exclusion, explicit review acknowledgement and complete equation replacement. It cannot replace the server document, source warnings, asset references or tenant/uploader identity. Original parsed values and modified flags remain visible. Revision checks prevent stale edits/confirmation.

Every included question must be ready; unresolved errors and unacknowledged review warnings block confirmation. Document-level issues also require explicit source review. All question serializers validate before any writes; creation, option creation, asset promotion, session confirmation and audit append share one transaction. A repeated confirmation fails. Successful confirmation clears sensitive preview JSON and returns draft question IDs/counts.

Preview and media responses use `no-store, private`; media uses `nosniff`. Files live outside the public media directory through a storage backend that deliberately has no public URL. Normal session/CSRF behavior is reused. Portal media requires an owned, active, unexpired Attempt; Quick media uses the existing cookie path and session resolver, so cookie scope and credential invalidation remain intact. Candidate media exposes only ID, private API URL, alt text, caption and order; no keys, correctness, explanations or source metadata.

Schedule `python manage.py cleanup_docx_imports` hourly. It removes expired preview state and unpromoted files; confirmed question files remain. Normal asset deletion also schedules file removal after transaction commit. Failed upload transactions explicitly remove newly written files. Production must supply durable private storage/backup and schedule cleanup; crash-created files without database rows need an operational orphan-file sweep. A future shared stimulus can own the same reusable asset rather than duplicating binaries across questions/attempts.

Audit records preview creation and confirmation with actor, institution, session ID and question/import/exclusion counts. Filenames, document binaries, question text, answer keys and credentials are not audited.

## Staff UI and rendering

Staff Questions now provides a small Question Bank inspection list and CSV/Word import choices. CSV still calls the existing `/questions/import/` endpoint. Word follows upload, processing, summary, section review, confirmation and draft-count success with “View Question Bank”. The review shows eight operational counts, source numbers, options, keys, images, equation representations/fallbacks, errors, warnings and modified/source previews.

Sections have accessible navigation; review filters include All/Ready/Needs review/Errors; at most ten questions are displayed per page after filtering the complete preview. All sections is selected by default; explicit section and text-search controls compose with status. Section headings remain visible within each page. Normal bank inspection displays twenty-five questions per page. Subject choices are resolved server-side for the selected institution. Review includes edits, exclusion, source acknowledgements, metadata selection, a visible expiry deadline and a cancel action. Cancel returns to the bank; server expiry/cleanup remains responsible for temporary files. Confirmation checks both client readiness and authoritative server validation.

English/Arabic/bilingual labels use `LanguageModeContext`; imported content remains authored and uses `dir="auto"`/`bdi`. Logical CSS and a 700px breakpoint accommodate smaller screens. Images scale to their container. Staff inspection, Exam Owner Questions, pure Exam Preview and the live candidate runner share the private image component. Equations remain safe text in prompts/options, so existing shared rendering handles them without an additional math execution library. No runner effects are mounted by staff preview.

## Actual pilot dry run

Reference: the local `EEG Comprehensive Examination 2.0.docx` in Downloads/Telegram Desktop. The parser command is generic and does not hard-code this filename:

```powershell
python manage.py preview_docx "path\to\document.docx"
```

This command creates no database session and no Question Bank records. The actual document was not confirmed or imported.

| Metric | Actual count |
| --- | --- |
| Sections | 9 |
| Questions | 171 |
| Answer-key entries | 148 |
| Matched answers | 148 |
| Missing answers | 23 |
| Invalid/ambiguous answers | 0 |
| Ready | 132 |
| Needs review | 11 |
| Hard errors | 28 |
| Images | 4 |
| Equations | 11 |
| Unsupported objects | 1 |

The first section has 28 questions, the next seven have 20 each, and Pattern Recognition has 3. The Word file records 46 pages; pagination is not recalculated by this XML parser. The source XML contains zero Word tables and no embedded packages. Non-content bookmarks are ignored, and heading media is associated with the new section rather than the preceding section.

### Question versus answer-key classification audit

The corrected manually counted total is 171. A fresh read-only dry run and an independent OOXML scan agree on all 171 question-start positions and all 148 answer-entry positions. Every detected question has a substantive source stem and following options; the complete source stem list was inspected. All 148 key paragraphs contain only an answer mapping/letter, with zero overlap with question-start paragraphs. Word automatic numbering and literal markers were checked separately from the parser. There are six key headings; the combined key after Electrical Safety supplies two sections using explicit titles. No parser changes or expected-count=100 regression assertions were made.

| Section in document order | Questions | Key entries | Matched | Missing | Ready | Needs review | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.0 EEG Instrumentation and Polarity | 28 | 28 | 28 | 0 | 26 | 2 | 0 |
| 2.0 EEG Machine Introduction MCQ | 20 | 20 | 20 | 0 | 14 | 1 | 5 |
| 3.0 EEG TERMINOLOGY | 20 | 20 | 20 | 0 | 17 | 3 | 0 |
| 4.0 BASIC PRINCIPLE OF ELECTRICITY | 20 | 20 | 20 | 0 | 20 | 0 | 0 |
| 5.0 ELECTRICAL SAFETY | 20 | 20 | 20 | 0 | 20 | 0 | 0 |
| 6.0 RECORDING PARAMETERS AND STANDARD SETTINGS MCQ | 20 | 0 | 0 | 20 | 0 | 0 | 20 |
| 5.0 Montages | 20 | 20 | 20 | 0 | 15 | 5 | 0 |
| 6.0 Activation during EEG, MCQ | 20 | 20 | 20 | 0 | 20 | 0 | 0 |
| 7.0 Pattern Recognition | 3 | 0 | 0 | 3 | 0 | 0 | 3 |
| **Total** | **171** | **148** | **148** | **23** | **132** | **11** | **28** |

The 23 missing answers are Recording Parameters Q1-Q20 and Pattern Recognition Q1-Q3. Recording Parameters ends after Q20/options and proceeds to Montages without an intervening key; Pattern Recognition ends after Q3/options without a key. No other recognized key block explicitly targets either section. These are genuine question items lacking keys in the supplied document, not answer-key false positives. Source body positions: Recording Parameters question starts 767-880; following Montages heading 889; Pattern Recognition heading 1185, question starts 1194/1202/1210, final options through 1215. Positions identify body XML elements, not rendered page numbers.

Readiness is separate from answer matching: all 148 keyed questions match, but five Machine Introduction questions still have hard option-structure errors. Eleven other keyed questions need review. All 23 unkeyed questions remain errors; Recording Parameters Q4 also has an option-marker issue, and Pattern Recognition Q1 retains its floating-anchor warning. All four images and eleven converted equations, ambiguous image association and the genuine unsupported floating anchor remain represented.

Source locations requiring review (section order is authoritative, not repeated source section numbers):

| Section | Questions and issue |
| --- | --- |
| 1 — Instrumentation and Polarity | Q6/Q7: image between questions on an option-numbered paragraph; verify association |
| 2 — Machine Introduction | Q2/Q3: overlapping inline/automatic option markers; Q6/Q9/Q14: duplicate, extra or missing markers; Q19: multiple inline options |
| 3 — Terminology | Q1/Q7/Q14: unnumbered text continuing an option |
| 6 — Recording Parameters | Q1–Q20: no detected answer key; Q4 also has missing first option marker |
| 7 — Montages | Q16–Q20: multiple options in a single paragraph |
| 9 — Pattern Recognition | Q1–Q3: no detected answer key; Q1 also has a floating image anchor requiring source review |

The combined Electrical Safety/Electricity key is matched through explicit source titles. All eleven equations were converted, including option-only equations. All four images were rasterized and the resulting EEG illustrations were visually inspected from temporary PNG files; the floating image warning remains despite successful image conversion. This checks decoded content, not browser layout. PNG alpha is preserved. Oversized decoder errors and corrupt compression streams are handled safely. Source issues have not been automatically corrected.

## Validation and manual acceptance

Synthetic DOCX fixtures are generated in tests rather than storing the 46-page pilot in the repository. They exercise four/five options, True/False, resets, explicit/automatic numbering, wrapped prompts, images, ambiguity, equations, missing/invalid/duplicate/malformed keys, unsupported objects and malicious/limited archives. Workflow tests exercise permissions, tenant/session ownership, expiry, revisions, editing/exclusion, transaction rollback, drafts/options/audit, private media, candidate allowlists, content freezing and cleanup. Existing CSV tests remain unchanged.

Native frontend tests cover the entry/upload contract, rendered review/counts/sections, filters, edit/exclusion controls, images, escaped equation fallback, confirmation guards, draft success and responsive/RTL contracts. These are native SSR/pure-function tests, not browser interaction tests.

Final validation: **720/720 full backend tests passed** (2,497.3 seconds). Focused backend validation passed **118 tests** covering DOCX workflow/parser, existing CSV/search import and Exam Owner Control Centre; the final parser-only run also passed **36/36 tests**, including four later image-decoder and structural bookmark/section-association regressions. **29/29 focused frontend tests** and **97/97 full native frontend tests** passed against the final frontend code. Production build passed (647.14 kB JavaScript bundle) with the existing large-bundle advisory. Django check reports no issues; migration drift check reports no changes; `git --no-pager diff --check` passes. Both migrations are applied. The earlier full 716-test snapshot also passed. The attempted parallel run failed at MySQL clone setup (deadlock/missing clone database) and was replaced by the normal sequential runner; the final full run passed. No permissions or database configuration were changed. A read-only development database check confirms zero DOCX sessions, zero imported media and zero DOCX-created questions.

Browser interaction and visual acceptance were not completed. Native frontend coverage uses SSR/pure-function/source-contract checks; it does not verify browser interaction, layout or candidate live media delivery visually. The manual steps below remain required. No files were staged, committed or pushed.

Manual acceptance:

1. Apply both new question migrations when deploying this working tree (already applied locally), start Django/Vite, and sign in with a question-bank staff role. Select a workspace.
2. Open `/app/questions`, verify normal bank inspection and the CSV choice, then upload the pilot using Word document.
3. Check the counts above; navigate sections and filters; inspect all four images and electrical equations in both prompts and options. Compare flagged source locations with the original Word document.
4. Correct keys/option boundaries or exclude affected questions; acknowledge source warnings only after reviewing the original. Save subject metadata and verify confirmation remains disabled for unresolved included items.
5. Use a small synthetic document for confirmation if the pilot must remain unimported. Verify all created questions are drafts and media appears in bank inspection.
6. Follow existing review/approval and assessment attachment rules; inspect Exam Owner Questions and pure Preview, then test authorized Portal and Quick candidate delivery. Confirm source equations/images appear and candidate responses contain no answer metadata.
7. Repeat at desktop/tablet/~390px widths and in English/bilingual/Arabic RTL; test expiry, workspace changes, retry and post-logout denial.

Limitations: this is an objective DOCX foundation, not arbitrary Word layout fidelity. Unsupported mathematical constructs require manual replacement; unsupported images require exclusion. Floating/table/complex object content requires review of the original. Shared stimuli, arbitrary separate key documents, rich option media layouts, registration and later product slices are not implemented.

## Exact files changed

- `.gitignore`
- `assessments/owner_serializers.py`
- `assessments/test_owner_control.py`
- `assessments/views.py`
- `attempts/serializers.py`
- `config/urls.py`
- `docs/phase-2b-slice-5a-docx-import.md`
- `frontend/src/App.jsx`
- `frontend/src/components/common/QuestionMedia.jsx`
- `frontend/src/components/student/StudentComponents.jsx`
- `frontend/src/pages/staff/ExamDetailPage.jsx`
- `frontend/src/pages/staff/QuestionsPage.jsx`
- `frontend/src/pages/staff/question-import.css`
- `frontend/src/pages/student/StudentExamPage.jsx`
- `frontend/src/services/examAdapters.js` (working-tree line-ending change only; no textual or behavioral diff)
- `frontend/tests/docx-import.test.js`
- `questions/apps.py`
- `questions/docx_parser.py`
- `questions/docx_urls.py`
- `questions/docx_views.py`
- `questions/management/__init__.py`
- `questions/management/commands/__init__.py`
- `questions/management/commands/cleanup_docx_imports.py`
- `questions/management/commands/preview_docx.py`
- `questions/migrations/0002_question_source_metadata_docximportsession_and_more.py`
- `questions/migrations/0003_alter_questionmedia_import_session_and_more.py`
- `questions/models.py`
- `questions/private_storage.py`
- `questions/serializers.py`
- `questions/signals.py`
- `questions/test_docx.py`
- `questions/views.py`
- `requirements.txt`

## Manual acceptance correction: preview collections and navigation

The bug was frontend-only. Direct authenticated GETs against both existing unconfirmed pilot sessions returned HTTP 200 with all 171 questions: 132 `ready`, 11 `needs_review`, and 28 `error`, without API pagination wrappers. `session_data` copies every section/question, and the frontend API client returns that JSON unchanged. Status-name mapping was correct. The UI initialized its selected section to the first section and filtered only that section's questions; the first section has two review questions and zero errors. Its ten-card paginator therefore showed one page for two review cards, rather than navigating the whole document. Search was not previously implemented, and backend pagination was not the cause.

The correction defaults to visibly selected **All sections**, builds the collection from the complete preview, composes explicit section/status/text-search filters, and only then paginates ten cards per page. The interface separately shows the question range/total and the page number/total. With no section/search restriction: All has 171 questions/18 pages; Ready 132/14 pages; Needs review 11/2 pages; Errors 28/3 pages. Review starts at questions 1-10 of 11, page 1 of 2, and Next reaches question 11. Error cards retain prompt/options, error messages, answer controls, equations, images and Save review. Section headings retain source grouping. English, Arabic and bilingual labels use the existing localization architecture and logical styles.

Filter changes reset page zero. Server-validated preview updates preserve the current page when valid, keeping neighboring edit forms mounted; the paginator immediately clamps and synchronizes a stale page if the collection shrinks. Resolving a review item uses the new authoritative summary (133 ready/10 review in the regression). Exclusion retains the parsed item in inspection and status totals, matching existing backend summary semantics; the separate included count updates, the card is marked Excluded, and confirmation still ignores excluded items. This preserves re-inclusion and avoids hiding questions.

Regression coverage adds nine frontend collection/rendering/navigation tests using a source-free nine-section 171-item distribution and one backend workflow test using generated DOCX paragraphs with the same readiness distribution. Backend GET, editing, exclusion and missing-answer correction are covered; CSV tests remain unchanged. No parser rules, production backend code, API contract, migration, permissions or confirmation behavior changed.

Files changed in this correction only:

- `frontend/src/pages/staff/QuestionsPage.jsx`
- `frontend/tests/docx-import.test.js`
- `questions/test_docx.py`
- `docs/phase-2b-slice-5a-docx-import.md`

Correction validation: 98/98 focused backend DOCX/CSV tests, 38/38 focused frontend tests and 106/106 full frontend tests passed. Production build passed with the existing large-bundle advisory (649.25 kB JavaScript); Django check, migration drift check and diff validation passed. A check using sanitized status/ID data from the actual pilot API response through the corrected frontend collection/pagination code also confirmed 171/132/11/28 unique accessible items. **721/721 full backend tests passed** (2,594.5 seconds). Final diff validation passed. No files were staged, committed or pushed.

Manual acceptance: select All sections and clear Search questions, then check All/Ready/Needs review/Errors totals and navigate to each final page. Confirm 23 missing-answer items show extracted content and editable answer controls. Explicitly select Recording Parameters + Errors (20), Pattern Recognition + Errors (3), and first section + Needs review (2); selected section must remain visibly highlighted. Check a search plus status combination, save a reviewed/corrected item and verify refreshed counts/page, then exclude/reinclude an item. Repeat mobile and Arabic RTL checks. Browser interaction/visual acceptance remains manual.

## Manual acceptance correction: recoverable review and confirmation

### Findings

Review PATCH already saves parsed items, question/option/answer/type corrections, exclusions, section edits, review flags and recomputed validation into the database session. Private media and equations remain server-owned. Refresh lost the frontend's only session identity/preview reference because the Questions page stored it only in React memory and never called the existing GET recovery endpoint. Saved data was not deleted by refresh. During investigation, the latest unconfirmed session contained 151 parsed questions, eight modified items, 151 included, zero excluded, eleven unresolved included items and no saved subject. Other 171-item sessions still existed; some were expired. These observations do not establish that every reported manual correction was saved to that particular session. No records or expiry times were changed during investigation.

The existing Confirm Import button already called the atomic endpoint and correctly ignored excluded errors, but was disabled without explaining prerequisites. Remaining included errors/review warnings, a missing saved subject, unreviewed document-level issues, no included questions or an in-flight request block it. There was no dedicated included-readiness summary and no post-refresh completion state.

### Implementation

- Stable staff route: `/app/questions/import/word/<opaque-session-uuid>`. Upload navigates to it. Refresh/reopen/navigation back fetches the authoritative server session, including saved review work. No browser storage holds review data or pointers.
- The Word entry screen has a minimal Resume Imports list: the uploader's five most recent unconfirmed, unexpired sessions in the selected institution. The existing subject-choice GET endpoint supplies these answer-free summaries; tenant/uploader/role checks remain unchanged. An expired session shows the explicit existing expiry error; an unavailable/cleaned-up session shows an unavailable/possibly-expired message and a bank return action, never an empty uploader pretending recovery succeeded.
- Confirmation area computes included-ready/excluded/unresolved counts from the complete server preview. For a fully resolved 171-item session with twenty exclusions it shows 151 ready, twenty excluded, zero unresolved. It explains missing subject/document review prerequisites and links to included errors/review warnings, resetting section/search/page and visibly enabling Included questions filtering. The existing ten-card review/navigation, media, equations, editing, CSV and authorization architecture remain intact.
- POST confirmation still locks the existing session and performs all validation, draft/option creation, media promotion, source metadata, audit and confirmation marking in one transaction. No alternate import path was introduced. A duplicate/retried POST still rejects the completed session without duplicates.
- The same transaction stores a small completion receipt (created IDs, imported count, draft status) inside existing session metadata and clears sensitive preview JSON. GET permits read-only recovery of a completed, still-valid owned session. Refresh renders success and View Question Bank without POSTing again. This also recovers a successful import whose response was lost over the network. Legacy completed sessions without receipts show a generic completed state. Expiry/cleanup behavior remains unchanged; normal bank questions survive cleanup. No model or migration was needed.

Meaningful saved review mutations are server authoritative. Unsaved form typing is not a server mutation: use Save review/Save section title/Save metadata before leaving or refreshing. View-only filters/pages need not survive reload. Default session validity remains two hours, with its deadline visible; recovery does not extend expiry or bypass authorization.

Files changed in this correction only:

- `questions/docx_views.py`
- `questions/test_docx.py`
- `frontend/src/App.jsx`
- `frontend/src/pages/staff/QuestionsPage.jsx`
- `frontend/tests/docx-import.test.js`
- `docs/phase-2b-slice-5a-docx-import.md`

### Validation and retest

Added three backend workflow regressions: full edited review/media/type/exclusion/section refetch through a fresh client; uploader/tenant/expiry-scoped recent sessions; completed receipt refresh and repeated confirmation without duplicate drafts. Added four native frontend regressions: dynamic 151/20/0 confirmation state and excluded errors; blocker navigation; stable route/server reload/Resume Imports contracts; explicit expiry and no confirmation POST on reload. Existing parser, CSV, isolation and rollback regressions remain part of validation. Native frontend tests use SSR/pure-function/source contracts; browser effects and actual clicks are still manual acceptance.

Current correction validation: 42 focused frontend tests and all 110 native frontend tests passed; production build passed (652.99 kB JavaScript, existing large-bundle advisory); Django check, migration drift check and diff validation passed. All 101 focused backend DOCX/CSV/import-session tests passed (396.8 seconds). **724/724 full backend tests passed** (2,598.9 seconds). Final diff validation passed. No new migration, parser change, permissions/ACL change, staging, commit or push.

Manual retest:

1. Sign in as the uploader and select the same workspace. Questions > Word document > Resume Imports recovers a still-valid prior session; use a new pilot upload if prior sessions have expired. The URL must contain its opaque session ID.
2. Correct one item and click Save review; exclude another and Save review. Refresh the stable URL. Verify the same session ID, saved text/options/answer/type/review flags and exclusion remain. Compare media/equations/source sections.
3. Return to Question Bank, select Word document and Resume Import. Verify the work again. Reopen the URL after closing the tab or restarting Vite; saved work remains while the session is valid.
4. For the 171-item pilot, exclude the twenty Recording Parameters items, supply the three Pattern Recognition answers and resolve all other warnings/options. Save a tenant-valid subject in metadata. Expected confirmation counts: 151 ready, twenty excluded, zero unresolved; button enabled. If blocked, use the included error/review links or displayed subject/document prerequisite. Do not confirm the real pilot as part of development checks.
5. The exam owner may perform the real confirmation manually after acceptance. Verify 151 draft questions, bank return, refreshed success receipt and no duplicates on repeat confirmation. Automated confirmation tests use only generated fixtures in the test database.
6. Check an expired URL and an unauthorized uploader/tenant; no preview/media recovery is permitted. Repeat English/bilingual/Arabic RTL and narrow/mobile controls. No permissions/ACL workarounds were attempted. Browser visual/interaction verification remains manual.

No parser changes, real pilot confirmation, staging, commit or push were performed.

## Final acceptance correction: persisted subject and authoritative eligibility

### Existing sessions inspected without mutation

The newest stored session at inspection was `59c75ed7-5890-4424-bc6b-35601ff91209`, institution 1 (Demo Training Institute), uploaded by `demo.admin@example.com`. Stored metadata had no subject (`subject_id` and name both null). It contained 151 parsed/included questions, zero exclusions, 132 ready, eleven needs-review, eight errors and nineteen unresolved included questions. It was unconfirmed and initially unexpired, with expiry 2026-10-04 12:23:40.361942 UTC (13:23:40 Lagos). An authenticated read-only GET returned 200. Backend blockers were exactly missing subject and nineteen unresolved included questions; no document-level issue blocker existed.

The session containing eight saved modifications, `61a59113-d811-48fd-a4fd-455a317714c0`, belongs to the same institution/uploader. It has null subject, 151 parsed/included, zero exclusions, 140 ready, eleven review, zero errors and eleven unresolved included; revision nine, unconfirmed. It had already expired at 2026-10-04 10:35:59.875758 UTC. Existing endpoint GET returns the explicit expiry error before content eligibility. Its saved work remains stored. There are exactly five stored sessions. The three older inspected 171-item sessions were expired, with 132 ready/11 review/28 errors, zero exclusions and no subject. These database records do not establish the requested fully resolved 171/20-excluded/151-ready state. The browser's exact session identity was requested while independent work continued; no session was guessed, reconstructed, reset or silently selected.

Hashes of preview JSON, metadata JSON and revision were recorded before implementation and checked afterward. All five inspected sessions remained identical. No pilot parsing, upload, PATCH, confirmation, deletion or expiry alteration was performed.

### Root cause and correction

The Subject select previously held a local copy of metadata, updated only local state on selection, and persisted only through Save metadata. Confirmation separately read the last server preview's metadata subject and locally duplicated eligibility rules. This allowed an unsaved/stale local subject to appear selected while the persisted prerequisite still said to select/save a subject. Local state initialized only once could also outlive server/session changes. Inspection found no persisted inferred/default subject. Exact browser rendering of an arbitrary first option was not reproduced; attributing that observation to a server default would be unsupported.

The stateless SubjectSelector now renders only top-level server `subject_id`/`subject_name`. Null selects the placeholder; it never chooses the first option. An explicit selection immediately sends the existing revision-controlled PATCH, disables the selector while saving and displays the resulting server value. A delayed subject-options response preserves an already persisted selection through a named fallback option. Changing/clearing explicitly sets the new ID/null and clears dependent topic. Optional difficulty/marks form state is separate; Save metadata merges with the current persisted subject and cannot write an obsolete local subject. Review state is keyed by institution/session. Tenant-filtered subject choices and normal QuestionSerializer rejection of invalid/foreign IDs remain authoritative.

Active preview/PATCH/recovery responses now return a `confirmation` contract: included-ready, included, excluded, unresolved, included error/review counts, persisted subject ID/name, eligible/blocked status and concrete blocker codes/messages/details. One read-only helper validates a copy of existing preview data and prepares normal QuestionSerializers. The same helper is used inside the existing locked atomic POST. Normal serializer validation failures are therefore visible before clicking Confirm as well as on POST; parser rules and stored preview remain unchanged. Frontend enables Confirm only from server eligibility and renders all server blockers/details. Busy state prevents an in-flight duplicate action. Nested 400 validation messages are surfaced; unexpected failures retain the existing retry message.

Confirmation still sends only the current revision: the server uses the persisted subject, never a client-reconstructed question list. Existing request/CSRF infrastructure is unchanged. Successful atomic creation still produces drafts/options, promotes private media, appends the audit, marks completion and returns the receipt; frontend shows success and bank return. Double confirmation remains rejected. No real pilot POST was performed, so there is no evidence of a pilot CSRF/network rejection; inspected stored prerequisites already explain why confirmation must remain blocked.

### Regression coverage / files

Three new backend workflow tests cover explicit null state, normalized subject save/refetch/recent-list/change/clear, invalid/foreign rejection without mutation, authoritative blocked/eligible responses, excluded errors, read-only recovery, persisted-subject draft creation and repeat rejection; normal serializer validation is reflected before confirmation. Four existing frontend confirmation tests/fixtures were updated to use the server contract, and four new frontend tests cover null/default-free/exact persisted selection, immediate subject/clear payloads, unavailable saved subjects and nested validation errors. These regressions fail against the previous missing response contract/selector implementation. Existing parser, CSV, isolation, media, rollback and recovery tests are retained.

Files changed by this correction only:

- `questions/docx_views.py`
- `questions/test_docx.py`
- `frontend/src/pages/staff/QuestionsPage.jsx`
- `frontend/tests/docx-import.test.js`
- `docs/phase-2b-slice-5a-docx-import.md`

No parser/model/migration/permission/session-auth architecture changes. Existing broader Slice 5A working-tree changes remain uncommitted.

Validation so far: 28/28 focused DOCX frontend tests and 114/114 full native frontend tests passed. Production build passed (653.95 kB JavaScript, existing bundle-size advisory). Django check and migration drift check passed. Diff check passed with existing LF/CRLF advisory warnings. The initial 104-test focused backend run caught two typed-contract failures (102 passed); DRF ValidationError had converted contract scalars into strings. Blocked confirmation now returns a typed private HTTP 400 Response. Both affected regressions passed on targeted rerun. The complete final-code backend run passed all 727 tests in 2,335.357 seconds, including all 104 focused DOCX/CSV/import tests. Final hashes again confirmed that all five production sessions retained identical preview, metadata and revision, with no confirmations and unchanged expiry times.

### Two-minute manual retest (existing still-valid session)

1. Sign in as the uploader, select Demo Training Institute and reopen the exact existing `/app/questions/import/word/<session-id>` URL. Check ID/counts and saved edits/exclusions. Null subject must select only Select a subject; confirmation shows Subject: Required and the actual backend blockers. Do not reupload.
2. Explicitly select a valid workspace subject, wait for the PATCH to finish, then refresh. The exact selected name must remain. Return to Questions > Word document > Resume Imports and reopen the same session; the subject and saved review work must agree again. Changing/clearing must save immediately.
3. When included questions are genuinely resolved, confirmation shows zero unresolved and becomes eligible with a valid subject (subject/document/normal-question validation must all pass). For the original 171-item session with twenty saved exclusions, expect 151 ready/20 excluded/zero unresolved; do not manufacture those counts. Remaining blockers must be visible and navigable. The administrator alone may click the real Confirm Import after acceptance; expect drafts, success/bank return and no duplication on reload.
4. Check narrow/mobile and Arabic/bilingual RTL placement. Actual browser click/visual verification remains manual. If the chosen session has expired, its existing endpoint expiry gate still applies: work remains stored, but recovery/confirmation cannot proceed. No expiry bypass, reupload or permission workaround was added.

No staging, commit or push.

## Final UX pass: seven-day review and inline subject creation

New unfinished DOCX sessions previously defaulted to 7,200 seconds (two hours). Creation now assigns `timezone.now() + timedelta(days=7)` directly. The persisted `expires_at` remains the authority for GET/PATCH/confirmation, private preview media, recent-session discovery and cleanup. There is no sliding renewal, permanent session, expired-session revival or backfill. Completed imports retain the existing completion receipt/protection behavior and persisted deadline. Existing valid/expired sessions retain their original expiry and review data. A read-only baseline snapshot of all six existing sessions records preview/metadata hashes, revision, expiry and completion state; no real pilot parsing/upload/creation/confirmation was performed.

The Word entry describes the seven-day policy and tells users to save each review change. Review displays a subtle saved-changes/resume message alongside its actual persisted deadline, so older two-hour sessions are not misleadingly promised seven days. No countdown was added; direct expired/unavailable session URLs retain clear existing errors.

The Subject selector remains null until explicit selection or successful Create & Select. A small inline form stays in the review page, with only required Subject Name (160-character maximum) and Subject Code (64-character maximum), Cancel and Create & Select. It reuses normal `POST /api/v1/subjects/`, supplying the current workspace's institution ID and the existing staff CSRF/session request wrapper. The returned Subject is added to the current options; the existing revision-controlled import metadata PATCH then saves its ID and clears dependent topic. Only the PATCH's server preview updates the selected subject/confirmation contract. Name/code input is local form state; there is no separate local selected-subject state. No reload is needed. Saved review text/options/answers/types/exclusions, source sections, equations and private media are untouched.

Creation and selection are two existing requests. Normal creation failure leaves the import unchanged and renders its validation error inside the form. If creation succeeds but PATCH fails (for example a stale revision), the created subject remains available in the list; the form explains the failure, disables repeat creation and allows Cancel followed by normal selection. For a stale revision, refresh the same review URL before selecting; saved work stays server-owned. Changing workspace/session aborts the outstanding flow and prevents a later POST response from selecting a subject in a different context. Workspace-options reload clears prior subject/recent-session lists while the tenant-scoped response loads; the exact persisted selected subject still renders through its server-owned fallback name. Existing active-institution, staff-role, uploader and private-media checks remain unchanged.

Inspection confirmed SubjectSerializer has no generated uniqueness validators because institution is read-only. The normal API previously relied on the per-institution/code database constraint, allowing a duplicate create to escape as IntegrityError. The existing SubjectViewSet now performs an authorized-institution duplicate-code check and translates a concurrent database conflict on that same constraint to a code-field HTTP 400. The database uniqueness constraint remains intact; duplicate names with different codes continue to follow the existing model rules. No fuzzy duplicate detection, new Subject model/endpoint or importer-specific permission was added.

The same backend confirmation contract remains authoritative. Its missing-subject blocker now says Select or create a subject before importing. A valid saved subject plus resolved included items enables confirmation, provided existing document/normal-question validations pass. Included unresolved items block; excluded unresolved items do not. Existing atomic draft creation, audit, completion receipt, rollback and duplicate-confirmation protection are unchanged. Confirmation tests use synthetic sessions only.

Files changed by this UX pass only:

- `questions/docx_views.py`
- `questions/test_docx.py`
- `subjects/views.py`
- `subjects/tests.py`
- `frontend/src/pages/staff/QuestionsPage.jsx`
- `frontend/tests/docx-import.test.js`
- `docs/phase-2b-slice-5a-docx-import.md`

Regression additions: three DOCX workflow tests cover approximate seven-day creation, six-day recovery and protected media, post-expiry denial and ownership/tenant checks; normal subject creation plus revision save/refetch/fresh-client/Resume with preserved edits/exclusions and draft/duplicate behavior; failed blank/duplicate/foreign creation without import mutation. Three Subject API tests cover normal validation/duplicate HTTP 400, foreign/student/anonymous denial and per-institution code uniqueness. Six frontend tests cover the inline form/required fields, normal POST-to-PATCH sequence and authoritative selection, duplicate failure, partial-success recovery, workspace/session cancellation, and persisted expiry UX. Existing parser, CSV, readiness, authorization, private media, completed receipt and rollback tests remain included.

Validation: all 114 focused backend DOCX/CSV/Subject/tenant-isolation cases passed across the initial run and targeted rerun. The initial run had one new test expecting 404 instead of the existing unauthorized-workspace 403; correcting the assertion preserved the production permission behavior. Its targeted rerun passed. The final-code full backend suite passed all 733 tests in 2,183.086 seconds, including all 114 focused cases. Frontend: 34/34 focused and 120/120 full native tests passed. Production build passed (657.57 kB JavaScript; existing bundle-size advisory). Django check, migration drift and diff validation passed. All seven correction files also passed trailing-whitespace validation, including untracked files. Final read-only hashes confirmed all six pre-existing sessions retained identical preview, metadata, revision, expiry and completed state. No schema migration, parser change, dependency, permission/ACL change, staging, commit or push.

Short manual retest:

1. Start a new test DOCX import manually and verify its deadline is approximately seven days after upload. Save a correction/exclusion and confirm Subject starts at Select a subject, with the select-or-create blocker.
2. Click + Create new subject. Enter a valid current-workspace name/code, then Create & Select. Verify the exact returned subject appears selected, counts/work remain intact and eligibility updates without reloading.
3. Refresh, then navigate to Questions > Word document > Resume Imports and reopen the same session. Verify the subject and saved corrections/exclusions remain.
4. Test a duplicate code or blank field: see validation, cancel and select the existing subject. With remaining included issues, confirmation remains blocked; resolve them and verify eligible/Confirm enabled. Excluded errors must not block. Do not automatically confirm the real EEG pilot.
5. Check English/bilingual/Arabic RTL and desktop/mobile layout. Browser click/visual acceptance remains manual. Existing older deadlines stay unchanged; expired URLs stay inaccessible with the clear error.
