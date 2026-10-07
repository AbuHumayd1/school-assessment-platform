# Create Exam delivery correction

Create Exam first offers Quick Exam or Through their account. The create request
persists `delivery_mode`; the backend represents new Quick exams with the existing
`candidate_access=access_code` marker. Account exams retain their group/direct
eligibility strategy. API responses expose delivery and eligibility separately.
Historical Quick configurations remain recognised, including configurations on
specific-candidate exams. No migration, backfill, or real-record mutation is needed.

Delivery changes are rejected by the assessment API and model before or after
Quick configuration. Creating a Quick configuration cannot convert an account
exam. Account eligibility can still change between group and direct assignment.
Quick eligibility continues using direct assignment; its bulk picker and the bulk
question attachment workflow are preserved.

Access reflects saved delivery without another chooser. Quick Access manages the
Exam Code, assigned/generated/needed counts, explicit credential generation, and
immediate CSV download. Candidate upload, assignment, exam creation and Exam Code
configuration do not issue PINs or create candidate User accounts.

Validation in this session: 32 focused setup/Access tests passed, production build
passed (existing chunk-size advisory), and git diff --check passed. Subsequent
broader frontend regressions encountered Windows access errors while Vite loaded
its config. Python launch was denied, preventing backend regressions, Django check
and the migration dry-run. Added creation/immutability tests still require a clean
run. These checks are incomplete, not accepted as passing.

Manual browser acceptance remains pending: verify the initial decision for both
methods, saved delivery after tab changes/refresh/reopening, bulk question and
candidate selection, Quick candidates without accounts, explicit generation and
immediate sheet download, and the absence of PIN controls for account delivery.
Use dedicated acceptance fixtures; do not generate real Activus credentials.
