# Quick Exam backend access (Phase 2B Slice 2)

Quick Exam is an access layer over the existing Attempt Engine. It creates no
User or institution membership and never logs a User into Django. The public UI
and Quick result retrieval remain deferred. Slice 1's migration is unchanged.

## Client protocol

1. Obtain a CSRF token with `GET /api/v1/auth/csrf/` using same-origin cookies.
2. Send `POST /api/v1/quick-exam/verify/` with `exam_code`, `candidate_id`, and
   `pin` in JSON, and the token in `X-CSRFToken`. Exam codes use Slice 1's ASCII
   uppercase normalization. Candidate IDs are trimmed like the existing DRF
   Candidate input; no new case conversion or identity rule is applied.
3. Success returns only `{"verified": true}` and sets `quick_exam_session`.
   Missing, incorrect, inactive, expired, disabled, or foreign-tenant credential
   paths return the same HTTP 401 detail. Absent credentials use a dummy Django
   password hash. Malformed verification data also pays a dummy hash check.
   This removes obvious hash-cost differences, not all possible timing signals.
4. `GET /api/v1/quick-exam/session/` restores safe Candidate/assessment details
   and availability after refresh. Verification never creates an Attempt or
   starts its timer. Availability is disclosed only after authentication.
5. Send `POST /api/v1/quick-exam/start/` with an empty JSON object. Candidate and
   Assessment come exclusively from the server session. It delegates to the same
   start/resume transaction as portal access, using ACCESS_CODE eligibility
   without requiring group membership. Portal new starts remain assigned-group
   only; normal candidate runner routes cannot bypass Quick credential/session
   authorization for an ACCESS_CODE Attempt. Existing staff viewing authority
   remains intact. Active resume is considered before new-start window/configuration rules.
6. Runner routes use the returned Attempt ID:

   | Method | Path beneath `/api/v1/quick-exam/` |
   |---|---|
   | GET | `attempt/` (latest authorized Attempt) |
   | GET | `attempt/<id>/` |
   | GET | `attempt/<id>/questions/` |
   | GET | `attempt/<id>/questions/<question_id>/` |
   | PUT/PATCH | `attempt/<id>/questions/<question_id>/answer/` |
   | PATCH | `attempt/<id>/questions/<question_id>/review/` |
   | GET/POST | `attempt/<id>/integrity/` |
   | POST | `attempt/<id>/submit/` |

   Every Attempt lookup is bound to the session's Candidate, Assessment, and
   institution. Existing safe serializers and runner methods handle questions,
   answers, review flags, integrity, submission, expiry, and marking. Submission
   contains no scores. Existing publication rules remain unchanged; there is no
   Quick result endpoint in this slice.
7. `POST /api/v1/quick-exam/logout/` with an empty object revokes the current
   resolvable Quick session and clears its cookie. It is idempotent, including
   missing/expired sessions. It leaves the Django User session, credential,
   Candidate, Attempt, answers, and Result intact.

All state-changing Quick routes require Django CSRF checks, including anonymous
verification and logout. Reuse the bootstrap endpoint after a normal User login
rotates the CSRF token. Cross-origin requests are subject to Django's existing
origin/referer checks. No new CSRF exemption or global authentication change is
introduced. Quick JSON responses, including errors, use `no-store, private`.

## Token, lifetime, replacement, and invalidation

The token is `secrets.token_urlsafe(32)` (256 random bits). Only its SHA-256 digest
is stored. The raw token appears only in an HttpOnly, SameSite=Lax cookie scoped
to `/api/v1/quick-exam/`, with Secure enabled in production settings. It never
appears in JSON, URLs, audit metadata, or browser storage.

Let `t` be issuance time, `d` assessment duration in seconds, `b` recovery buffer,
and `l` base lifetime:

```
expiry = t + max(l, d + b)
if assessment.end_at exists:
    expiry = min(expiry, max(t, assessment.end_at) + d + b)
if credential.expires_at exists:
    expiry = min(expiry, credential.expires_at)
```

Defaults are `QUICK_EXAM_SESSION_BASE_SECONDS=28800` (8 hours) and
`QUICK_EXAM_RECOVERY_BUFFER_SECONDS=7200` (2 hours), configurable via environment.
Sessions do not slide. Recovery beyond an entry window cannot authorize a new
start after that window: existing Assessment eligibility and Attempt deadlines
remain authoritative. Long examinations receive duration plus recovery time.

Each successful verification atomically revokes earlier unrevoked sessions for
that credential and creates one new live session. It does not rotate the PIN or
modify examination state. Verification and engine entry use the existing
Candidate -> Assessment locking order, then configuration/credential/session
locks. Engine entry rechecks authorization after acquiring lifecycle locks.

Every authenticated Quick request validates session expiry/revocation,
credential/configuration version snapshots, active credential/configuration,
credential expiry, active Candidate/institution, ACCESS_CODE mode, and tenant
ownership. Invalid sessions return a generic 401; they never fall back to User
authentication. Quick cookies are not registered with global DRF authentication
and cannot grant portal or staff access.

Session expiry, credential revocation, and logout do not finalize an Attempt.
Re-verification can recover the same active Attempt if existing resume rules
permit. Only existing deadline, integrity, and manual finalization rules mark it.

## Throttling and auditing

Verification applies DRF limits of 10/minute per IP and 5/minute per
IP + normalized Exam Code + Candidate ID. Identifier keys use keyed SHA-256;
they contain no raw identifiers or PIN. Candidate case-folding is used only for
throttle keys, not authentication. Limits never deactivate or globally lock a
Candidate. Quick runner requests are scoped to session IDs: 600/minute normally,
300/hour for starts, 60/minute for submissions, and 120/hour for integrity.

The current default Django cache is process-local. These limits are a useful
application layer but are not sufficient distributed production brute-force
protection. Configure a shared Django cache plus edge/rate-limit protection
before public production deployment. DRF cache throttles also have concurrency
limitations. Configure trusted proxy handling/NUM_PROXIES and sanitize forwarded
IP headers at the deployment edge. No Redis dependency is added in this slice.

Successful session creation/replacement and logout append existing
MEMBERSHIP_CHANGED audit events with explicit safe action metadata and resolved
institution/Candidate/assessment/configuration IDs. Actor is null because Quick
identity is not a User. Unknown verification failures fabricate no tenant event.
No PIN, password hash, raw token, or digest is logged or audited by this code.

Before Slice 3, review lifetime defaults, production shared throttling/proxy
configuration, HTTPS cookie delivery, and the future public UI's CSRF/recovery
integration. Browser UI testing is deferred with that UI.
