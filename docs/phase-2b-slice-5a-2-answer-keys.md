# Slice 5A-2: final corrective pass

This report supersedes the earlier architectural-pass report. No staging, commit, push, historical backfill, customer-specific parsing, permission change, migration or dependency change is part of this correction.

## Evidence and exact causes

The retained embedded manual session is 16d1aed3-9c50-4397-a50e-2d2483eae6fa. Read-only inspection found its `Untitled section` (20 questions with four options each) classified as Answer Key, while `ANSWER KEYS` (20 optionless letter items) remained Questions. The saved collection contained 20 embedded entries made from question text, not zero entries. Those entries were invalid answers against the remaining optionless items. Thus the supplied explanation of zero entries is not the saved state's exact cause. The source document is not retained; browser history cannot be reconstructed.

A memory-only copy, restoring the question block to Questions and classifying the answer block as Answer Key, now yields 20 canonical questions, 20 embedded entries, 20 matches, 20 Ready, zero missing, zero question errors. Three genuine introductory-content checks remain in that saved document. The real session was not rewritten.

Two independent generic extraction weaknesses were also confirmed: the heading expression omitted the plural ANSWER KEYS, and the answer-line reader omitted middle-dot/bullet separators. Classification trusted an empty archived `entries` list rather than extracting a retained question section. Regression tests cover these weaknesses independently and the actual swapped-block recovery.

The separate confirmation contradiction came from counting only question readiness in `unresolved`, while document checks, key-entry issues, subject/metadata and required classifications could block independently. The old UI displayed all questions ready and zero question issues alongside Blocked. The actual separate manual session is no longer available, so its specific source paragraphs cannot be asserted. Real introductory/unsupported content remains a required visible check; resolved section-matching notices and reconciliation notices no longer require a second unrelated source checkbox.

Earlier saved XLSX evidence had 20 explicit section values equal to option text rather than section titles. The original XLSX is unavailable. Inspection found recognized headers map by name, optional extra columns are ignored rather than assigned as Section, and there is no arbitrary positional section inference. CSV/XLSX regressions prove `Section | Question Number | Correct Answer | Option Text` uses the correct three fields, including case variations. Common Question/Answer, Question Number/Answer and Q No/Correct Option aliases work. Duplicate or unknown column meanings request explicit distinct column mapping. There is no evidence justifying a new parser workaround; unsafe unknown-section fallback was not added.

## Backend correction and preserved contracts

- Generic headings support ANSWER KEY, ANSWER KEYS, ANSWERS, ANSWERS KEY, KEY ANSWERS, CORRECT ANSWERS, MARKING KEY, case/spacing and common terminal punctuation. Anchored headings and negative normal-question cases prevent matching arbitrary text mentioning answer. Middle-dot/bullet answer separators are supported.
- Classification archives live edits, removes the classified section from participation, extracts retained entries even when the archived list is empty, normalizes source markers, and calls the same `recompute_matches` engine. Unsupported media/equations/warnings on converted items remain diagnostics. Classification is a manual document decision; automatically matched individual answers retain automatic resolution provenance.
- Answer Key -> Questions removes that block's embedded entries and automatic dependent answers, restoring question participation and stable identities. Ignore removes question/answer participation. Saved classifications, edits and links remain reversible and refresh-safe.
- `needs_classification` marks genuinely uncertain answer-like question runs or undecided table blocks. Their UI starts with Choose an option rather than pretending Questions is a deliberate decision. Required decisions block confirmation. No database schema is added.
- Confirmation retains question `unresolved` semantics and adds `additional_issues`, `attention_count` and `document_issues`. Every non-question blocker has a visible count or contributes one issue. Source excerpts are retained for newly parsed introductory content; old sessions can still show original document positions.
- Only matching-derived notices that are already represented by key-entry blockers, or old section notices whose embedded entries are fully resolved, cease to demand redundant source acknowledgement. Genuine unsupported objects/media/content are not suppressed.
- Missing valid answers remain Needs Review, even with Reviewed checked. Invalid question structure/type/options/equations/media remain Errors. Questions of every status remain inspectable.
- Existing generated-template IDs, conservative matching, manual links/answer overrides, tenant/uploader authorization, session/CSRF, revision checks, audit and atomic/idempotent confirmation remain. No sequence, count, half-document or fuzzy matching was introduced.
- Remove/replace/delete behavior is retained: confirmations, automatic-state cleanup, explicit manual/embedded answer preservation, unfinished-only deletion, temporary-media cleanup and completed-import protection.

No new endpoint was introduced in this final correction. Existing classification/review/upload/confirmation responses gain the preview/eligibility fields above. No model, migration, dependency or authentication change was made.

## Simple user experience

The normal path is Upload -> Check -> Import, or Upload Questions -> Add Answers -> Check -> Import. Success shows Your import is ready, question/answer counts, No issues found and Import Questions (N). Technical count cards, source classifications and question editors live in collapsed Import details/Review Questions areas. Answer-file/template controls collapse after a key is uploaded.

When help is required, the document prompt asks What are these numbered items? with Questions / Answer Key / Ignore. Confirmation displays a counted actionable issue and links directly to Review document section. Genuine content checks show an excerpt or original document position and I checked this content against my Word file.

Only unresolved answer entries appear by default. Match Answer selects the intended question without changing its value; Change match handles relinking. Change answer reveals the separate explicit Correct answer correction. Ambiguous targets retain section optgroups; no guess is made. Matching reasons are plain-language instructions, not diagnostic codes. Resolved agreeing duplicates remain accessible in All but do not demand unnecessary intervention. Matching summaries count each target question once when embedded and separate sources agree.

The optional recommended template is preserved: download the session-specific XLSX, fill only Correct Answer and upload. Question ID is a preview token, not a database ID; unknown/foreign/duplicate IDs reject before replacing an existing key. Formula, macro, ZIP/XML, external-link and injection protections remain. Existing DOCX/XLSX/CSV keys are still supported; ambiguous headers show Tell us which columns contain with question number, answer and optional section choices.

Canonical identity, provenance, source registries, rules/reasons, revisions and developer diagnostics remain internal. Stale-revision messages now ask users to refresh. EN/bilingual/Arabic copy uses the existing localization architecture; logical CSS, wrapped controls, bdi/dir=auto and the existing 700px breakpoint are retained. Added disclosures have wrapping and minimum-width constraints. Real browser/Excel verification remains manual.

## File ownership

Modified tracked files in this final pass:

- frontend/src/pages/staff/QuestionsPage.jsx
- frontend/src/pages/staff/question-import.css
- frontend/tests/docx-import.test.js
- questions/docx_parser.py
- questions/docx_views.py

Modified files that were already untracked before this final pass:

- docs/phase-2b-slice-5a-2-answer-keys.md
- frontend/src/pages/staff/AnswerKeyPanel.jsx
- frontend/src/pages/staff/ImportBlocks.jsx
- frontend/src/pages/staff/ImportWorkflow.jsx
- frontend/tests/answer-key.test.js
- frontend/tests/import-reconciliation.test.js
- frontend/tests/import-workflow.test.js
- questions/answer_keys.py
- questions/import_reconciliation.py
- questions/test_answer_keys.py
- questions/test_import_reconciliation.py

No new file was created by this final correction. The existing untracked questions/test_import_management.py was retained without edits. Earlier uncommitted tracked changes in frontend/src/services/api.js, questions/docx_urls.py, questions/signals.py and questions/test_docx.py were retained without edits. The unrelated pre-existing frontend/src/services/examAdapters.js modification was untouched.

## Required manual acceptance A-G

Use new unfinished imports and keep the completed historical pilot untouched. Select a subject when required.

A. Embedded normal: upload the real 20-question/20-answer DOCX. Expect automatic ANSWER KEYS recognition, 20 questions, 20 answers and 20 Ready without manual classification. Import is enabled after any genuine visible content checks are acknowledged.

B. Embedded recovery: upload an uncertain answer block, open the plain-language prompt and choose Answer Key. Expect automatic matching and updated Ready counts. For the existing swapped-block session, first restore Untitled section to Questions, then set ANSWER KEYS to Answer Key. Check the three highlighted original-document positions before importing.

C. Existing separate key: upload questions, then your XLSX/CSV/DOCX key. Recognized headers skip mapping; ambiguous headers ask for simple column choices. Resolve only remaining entries with Match Answer or explicit corrections. Import enables when the server reports all blockers resolved.

D. Template: upload questions, download the prepared template, fill only Correct Answer and upload it. Expect direct deterministic matching and ready state, including repeated numbering.

E. Repeated numbering: Section A Q1 and Section B Q1 plus an unscoped Q1 key must remain ambiguous. Choose the intended section/question and Match Answer; refresh to verify persistence.

F. Remove/replace/refresh: cancel each confirmation once, then remove/replace a key. Automatic source-derived answers disappear/recompute; appropriate saved manual and embedded answers survive. Refresh classifications, matches, subject and counts; a stale second tab must require refresh.

G. Delete: cancel once, then delete an unfinished synthetic import. It disappears and cannot reopen. Completed imports offer no delete and server mutation remains prohibited.

Repeat A-G at desktop, tablet and about 390px in English, bilingual and Arabic RTL. Check keyboard/disclosure controls, wrapping, target selection and no horizontal overflow. Open/fill the XLSX in the institution's spreadsheet software. No browser runner ACL workaround was attempted.

## Validation and historical safety

Before and after fingerprints matched exactly: 151 Questions IDs 10-160, 698 options/answers, all provenance, Subject 3 and completed pilot 54fde495-77b7-4d27-85dc-f688bebf50ef revision 22; SHA-256 bab04f90f0b8600a5cee0991f180650016088745fdddaffa5ab74089787d4c93. All development-data investigation was read-only; recovery was tested on copies in memory and isolated test databases.

Final validation (final application/test state):

- Focused backend classification/reconciliation + separate-key tests: 93/93 passed. One later actual swapped-block regression is additionally included in the final importer, related and full suites.
- All DOCX/import-management/answer-key/reconciliation tests: 193/193, native exit 0.
- Questions/subjects/assessments: 588/588, native exit 0.
- Full backend: 856/856, native exit 0, 1083.929 seconds. Suites ran sequentially against fresh isolated test databases with backend application/test code frozen.
- Final focused frontend: 107/107, native exit 0.
- Final full native frontend: 193/193, native exit 0, 44.347 seconds. Existing serial/force-exit invocation was retained; no test harness settings changed.
- Production frontend build: passed, native exit 0; 122 modules, JS 698.41 kB / 197.99 kB gzip, CSS 187.28 kB. Existing 500 kB chunk advisory remains.
- Django system check: no issues. Migration consistency: no changes. No migrations/dependencies/models changed.
- Tracked diff check and all 12 untracked whitespace checks: passed. Index empty; no staging, commit, push or history change.
- Read-only final fingerprint: MATCH. All 151 Questions, 698 options/answers and provenance, Subject 3, completed pilot UUID and revision 22 unchanged. SHA-256 bab04f90f0b8600a5cee0991f180650016088745fdddaffa5ab74089787d4c93.

The first exact-middle-dot regressions exposed PowerShell's legacy stdin encoding replacing a Unicode fixture literal with a question mark; fixtures were corrected to explicit Unicode escapes. The actual parser delimiter change uses UTF-8 patching. No production matching rule or assertion was weakened to make those tests pass. Earlier presentation assertions were updated to the requested labels, collapsed details and nonzero issue summaries while preserving control/authorization/collection assertions.

Remaining manual verification: the actual DOCX/XLSX/CSV files and spreadsheet application, plus desktop/tablet/mobile and English/bilingual/Arabic RTL browser acceptance A-G. No browser automation or ACL workaround was attempted. Legacy source bytes/paragraphs that were never retained cannot be reconstructed. Original separate XLSX and the previously inspected unfinished separate session are unavailable, so its precise original mapping choice/header cause remains unproven.

Final working tree (earlier uncommitted changes are included; ownership is listed above):

```text
 M frontend/src/pages/staff/QuestionsPage.jsx
 M frontend/src/pages/staff/question-import.css
 M frontend/src/services/api.js
 M frontend/src/services/examAdapters.js
 M frontend/tests/docx-import.test.js
 M questions/docx_parser.py
 M questions/docx_urls.py
 M questions/docx_views.py
 M questions/signals.py
 M questions/test_docx.py
?? docs/phase-2b-slice-5a-2-answer-keys.md
?? frontend/src/pages/staff/AnswerKeyPanel.jsx
?? frontend/src/pages/staff/ImportBlocks.jsx
?? frontend/src/pages/staff/ImportWorkflow.jsx
?? frontend/tests/answer-key.test.js
?? frontend/tests/import-reconciliation.test.js
?? frontend/tests/import-workflow.test.js
?? questions/answer_keys.py
?? questions/import_reconciliation.py
?? questions/test_answer_keys.py
?? questions/test_import_management.py
?? questions/test_import_reconciliation.py
```
