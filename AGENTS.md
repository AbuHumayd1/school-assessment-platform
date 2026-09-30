# Development guardrails

- Keep this repository independent from the frozen Book Reading CBT project.
- Preserve the verified Phase 0 foundation, Phase 1 question bank, and Phase 2 Assessment Engine. Phase 3 candidate examination delivery is implemented; do not add marking, scores, results, analytics, proctoring, or later-phase features unless requested.
- Keep the architecture a lean Django modular monolith with shared-schema tenancy.
- Use email as the custom User authentication identity. Never attach a single institution role directly to User.
- Every institution-owned record must be filtered server-side by active institution memberships. Never trust client-side filtering or permit cross-tenant reassignment.
- Keep institution-specific candidate IDs, group codes, and subject codes protected by database constraints.
- Keep question-bank topics/questions and assessments scoped to active institution memberships. Never accept tenant assignment, calculated total marks, or workflow transitions on trust from the client.
- Validate subject/topic/creator/reviewer ownership and objective-option rules at model or service/API boundaries.
- Keep assessment configuration and candidate attempt/session processing separate. Do not introduce marking, scores, result processing, billing, AI, notifications, or other future-phase features or unnecessary dependencies.
- Read existing files before editing them; avoid unrelated changes.
