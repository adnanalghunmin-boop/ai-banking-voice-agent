# Banking Voice Agent — Backend (Phase 1 + Phase 2 + Phase 3)

Backend API sitting between the HeyBreez voice platform and the mock Oracle
banking database for a fictional Jordanian bank POC.

Phase 1: project foundation, Oracle connectivity, health checks, and
deterministic customer verification.

Phase 2: V1 account/card information and actions, the human-reviewed
request flows (card block, card replacement, customer detail changes),
complaints, callback requests, and document requests.

Phase 3: security hardening. Verification now issues a short-lived opaque
token, and every account/card-scoped endpoint requires it instead of
trusting a caller-supplied customer_id/account_id. See "Phase 3: verification
tokens" below. HeyBreez integration and FAQ/RAG are still not implemented.

## Project structure

```
app/
  main.py              FastAPI app, startup/shutdown, exception handlers
  config.py             Settings loaded from environment (.env)
  api/                  Route handlers (health, verification, accounts, cards,
                          customers, complaints, callback_requests, document_requests)
  models/                Pydantic request/response schemas
  services/              Business logic (verification, identity/ownership
                          checks, accounts, cards, customer_requests,
                          complaints, callbacks, documents)
  db/                     Oracle connection pool + parameterized queries
  utils/                  Cross-cutting helpers (masking, exceptions)
tests/                   pytest suite (mocked unit tests + small read-only
                          integration tests)
```

## Requirements

- Python 3.12
- Oracle Database reachable (already running in Docker as `oracle-db`,
  service `FREEPDB1`)

## Setup

```bash
cd ~/Desktop/banking-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in real credentials (a working `.env`
is already present for local development and is git-ignored):

```bash
cp .env.example .env
```

Environment variables (see `.env.example`):

```
DB_USER=banking_app
DB_PASSWORD=your_database_password
DB_HOST=localhost
DB_PORT=1521
DB_SERVICE=FREEPDB1
```

## Running the API

```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The Oracle connection pool is created on startup and closed on shutdown.

## Endpoints

- `GET /health` — process liveness only, no DB access.
  ```json
  {"status": "ok"}
  ```
- `GET /api/v1/database/health` — runs `SELECT 1 FROM dual` against Oracle.
  ```json
  {"status": "ok"}
  ```
- `POST /api/v1/verification/verify` — deterministic customer verification.

  Request:
  ```json
  {
    "national_id": "9876543210",
    "account_number": "1002003001",
    "last_transaction_amount": 32.5,
    "last_transaction_merchant_or_type": "Carrefour"
  }
  ```

  Successful response — `verification_token` is a short-lived (30 minute)
  opaque token; see "Phase 3: verification tokens" below:
  ```json
  {"verified": true, "customer_id": 1, "account_id": 1, "verification_token": "<random>", "reason": null}
  ```

  Failed response (reason is intentionally generic — it never reveals which
  factor was wrong; no token is issued):
  ```json
  {"verified": false, "customer_id": null, "account_id": null, "verification_token": null, "reason": "verification_failed"}
  ```

### Manual test of successful verification

```bash
curl -s -X POST http://localhost:8000/api/v1/verification/verify \
  -H "Content-Type: application/json" \
  -d '{
    "national_id": "9876543210",
    "account_number": "1002003001",
    "last_transaction_amount": 32.5,
    "last_transaction_merchant_or_type": "Carrefour"
  }'
```

## Verification logic

Implemented in `app/services/verification.py`, kept separate from both the
API layer (`app/api/verification.py`) and raw DB access
(`app/db/repository.py`):

1. Look up the customer by `national_id`.
2. Look up the account by `account_number` and confirm it belongs to that
   customer.
3. Fetch the most recent transaction with `transaction_status = 'COMPLETED'`
   for that account (`ORDER BY transaction_date DESC`).
4. Compare the supplied amount to the stored amount as exact `Decimal`
   values.
5. Compare the supplied merchant/type against the transaction's
   `merchant_or_type` OR `transaction_type`. Both sides are first resolved
   through the deterministic merchant-alias table (see below), then
   compared case-insensitively with whitespace normalized.
6. `verified = true` only if every step passes. Any failure at any step
   returns the same generic `verification_failed` reason — the API never
   indicates which specific factor was wrong, to avoid leaking information
   useful to an attacker.

The backend makes this decision deterministically in SQL/Python; the LLM
never decides verification outcomes. The backend evaluates exactly one
attempt per call — retry counting (max 3 attempts) is the voice workflow's
responsibility, not the backend's.

### Merchant alias resolution

A customer speaking a merchant's Arabic name (e.g. "كارفور") against a
database record stored in Latin script ("Carrefour") is semantically the
same merchant, but plain case/whitespace normalization can't know that. A
small reference table, `MERCHANT_ALIASES` (`alias_id`, `canonical_value`,
`alias_value`, `active`), maps known alternate spellings to one canonical
value:

```sql
CANONICAL_VALUE  ALIAS_VALUE
CARREFOUR        Carrefour
CARREFOUR        carrefour
CARREFOUR        كارفور
```

`app/services/merchant_alias.py` loads every active alias once per
verification attempt (`build_alias_map`) and resolves the spoken value,
`merchant_or_type`, and `transaction_type` through the same map
(`resolve`) before comparing them. A string with no configured alias falls
back to its own normalized form — so unaliased merchants keep matching
exactly as before this mechanism existed. This is a deterministic
dictionary lookup, not fuzzy matching and not an LLM decision: an alias
either exists in the table or it doesn't.

## Phase 3: verification tokens

Phase 2's ownership mechanism re-validated a caller-supplied
`customer_id`/`account_id` pairing against the database on every call, but
never proved the caller was entitled to claim that `customer_id` at all —
any caller who discovered a valid pair could call protected endpoints
without ever completing verification. Phase 3 closes that gap with an
opaque, short-lived **verification token**, without introducing JWT.

**Issuance.** A successful `POST /api/v1/verification/verify` calls
`app/services/verification_sessions.create_session()`, which:

1. Generates 256 bits of randomness with `secrets.token_urlsafe(32)` —
   cryptographically secure, not predictable/sequential.
2. Hashes it with SHA-256 and inserts only the hash, plus `customer_id`,
   `account_id`, and an `expires_at` 30 minutes out, into the new
   `VERIFICATION_SESSIONS` table.
3. Returns the raw token to the caller exactly once, as
   `verification_token` in the response. It is never logged and never
   stored anywhere — only its hash exists in the database.

Failed verification issues no token at all.

**Consumption.** Every protected endpoint now takes a `verification_token`
field (see `app/models/common.py:TokenContext`) instead of accepting
`customer_id`/`account_id` directly. `app/services/verification_sessions.
resolve_session()` hashes the supplied token, looks it up, and returns the
trusted `{customer_id, account_id}` pair only if a row exists, `active = 1`,
and `expires_at` is still in the future — checked in Python against a
consistent UTC clock. That resolved pair is what every subsequent ownership
check (`app/services/identity.py`, unchanged from Phase 2) runs against —
raw `customer_id`/`account_id` values are no longer accepted from the
caller at all for these endpoints, so they can't be trusted *or* untrusted;
they simply don't exist as an attack surface anymore. If a `card_id` is
also supplied (card endpoints), it's still checked against the *resolved*
customer/account, exactly as Phase 2 checked it against the caller-supplied
one — ownership validation itself is unchanged, only its input is now
trustworthy.

**Failure handling.** Missing, unknown, expired, and deactivated tokens all
raise the same `InvalidSessionError`, mapped to `401` with the identical
generic body `{"detail": "Invalid or expired verification session"}` in
every case — the caller cannot learn which of those four it was.

**Unprotected flows**, per spec, need no token: general complaints (no
account reference), and callback requests (used precisely when
verification has failed or wasn't attempted). If either of those *does*
reference an account, it must go through `verification_token` instead of a
raw `account_id` — see the complaints/callbacks table below.

**Schema change:** one new table, `VERIFICATION_SESSIONS`
(`session_id` identity PK, `token_hash` unique, `customer_id`/`account_id`
with `FK_VERIFICATION_SESSION_*` constraints to `CUSTOMERS`/`ACCOUNTS`,
`created_at`/`expires_at`, `active`), created to match the existing
schema's own conventions (identity columns, FK naming, `CURRENT_TIMESTAMP`
defaults) exactly. No existing table was altered.

## Phase 2 endpoints

All Phase 2 endpoints are `POST` with a JSON body (consistent with
`/api/v1/verification/verify`, and appropriate for tool-style calls from an
orchestration layer rather than a browser).

### Account information (`app/api/accounts.py`) — protected

Body for all of these is `{"verification_token": "<token>"}` unless noted.
`customer_id`/`account_id` are resolved from the token, not accepted from
the caller.

| Endpoint | Returns |
|---|---|
| `POST /api/v1/accounts/balance` | `balance`, `available_balance` |
| `POST /api/v1/accounts/iban` | `iban` |
| `POST /api/v1/accounts/status` | `account_status` |
| `POST /api/v1/accounts/held-amount` | `held_amount` |
| `POST /api/v1/accounts/transactions` | `transactions: [...]` (adds `limit`, default 5, max 10) |

### Card information / direct actions (`app/api/cards.py`) — protected

Body includes `verification_token`, `card_id` (still checked against the
*resolved* customer/account), and for every mutating action a required
`"confirmed": true` — if `confirmed` is not `true`, the action is rejected
with `400` and nothing is changed.

| Endpoint | Effect |
|---|---|
| `POST /api/v1/cards/delivery-status` | read-only, returns `delivery_status` |
| `POST /api/v1/cards/activate` | `card_status` → `ACTIVE` (must currently be `INACTIVE`) |
| `POST /api/v1/cards/unfreeze` | `card_status` → `ACTIVE` (must currently be `FROZEN`) |
| `POST /api/v1/cards/online-purchases` | sets `online_purchases_enabled` (`enabled: bool`) |
| `POST /api/v1/cards/international-usage` | sets `international_usage_enabled` (`enabled: bool`) |
| `POST /api/v1/cards/spending-limit` | sets `spending_limit` (`new_limit`, must be > 0) |
| `POST /api/v1/cards/atm-withdrawal-limit` | sets `atm_withdrawal_limit` (`new_limit`, must be > 0) |

### Human-reviewed requests (never mutate the protected fields directly) — protected

| Endpoint | Creates | Never touches |
|---|---|---|
| `POST /api/v1/cards/block-request` | `SERVICE_REQUESTS` row, `request_type=CARD_BLOCK`, `reason` ∈ `LOST`/`STOLEN`/`CUSTOMER_REQUEST` | `CARDS.card_status` |
| `POST /api/v1/cards/replacement-request` | `SERVICE_REQUESTS` row, `request_type=CARD_REPLACEMENT`, `reason` ∈ `LOST`/`STOLEN`/`DAMAGED`/`OTHER` | issues no card |
| `POST /api/v1/customers/detail-change-request` | `SERVICE_REQUESTS` row, `request_type=CUSTOMER_DETAIL_CHANGE`, `field` ∈ `MOBILE_NUMBER`/`EMAIL`/`ADDRESS`/`EMPLOYMENT_DETAILS`, `requested_value` | `CUSTOMERS` table |

All three require `verification_token` + `"confirmed": true` and return
`201` with `{"request_id": int, "request_status": "PENDING"}`.

### Complaints, callbacks, documents — mixed

| Endpoint | Notes |
|---|---|
| `POST /api/v1/complaints` | **Unprotected** for a general complaint (no `verification_token` needed, `customer_id` optional). Referencing an account is **protected**: supply `verification_token` instead of a raw `account_id` (a bare `account_id` without a token is rejected with `400`) — the resolved identity is used, overriding any `customer_id`/`account_id` also present in the body. Returns `complaint_id`, `complaint_reference` (e.g. `CMP-000001`, derived from the real `complaint_id`), `complaint_status`. `201`. |
| `POST /api/v1/callback-requests` | **Unprotected**, unchanged from Phase 2 — explicitly the fallback after failed/unavailable verification, so it still accepts `customer_id`/`account_id` directly (with the Phase 2 ownership check when both are given). |
| `POST /api/v1/document-requests` | **Protected** when it involves an account: supply `verification_token` instead of a raw `account_id`. A request with no account (e.g. a general bank certificate) may supply `customer_id` directly. `document_type` ∈ `ACCOUNT_STATEMENT`/`IBAN_CERTIFICATE`/`BANK_CERTIFICATE`/`LOAN_STATEMENT`. Returns `document_request_id`, `request_status`; only ever records the request. `201`. |

## Aggregated read-only endpoint — `POST /api/v1/get-services`

Lets HeyBreez request several read-only banking facts in a single call
after verification, instead of one HTTP round trip per fact. Protected —
`verification_token` required, `customer_id`/`account_id` never accepted
from the caller.

Request: `verification_token` plus any combination of `get_balance`,
`get_iban`, `get_account_status`, `get_held_amount_details`,
`get_card_delivery_status` (all default `false`). At least one must be
`true`, or the response is `400`. The response contains only the fields
that were requested (`response_model_exclude_none=True` drops the rest).

```json
{"verification_token": "...", "get_balance": true, "get_iban": true}
```
```json
{"balance": "2450.75", "available_balance": "2300.75", "iban": "JO71JHBK0000001002003001"}
```

**Card delivery without a `card_id`.** The caller never needs to know
internal card IDs. `get_card_delivery_status` lists every card belonging
to the *token-resolved* account (`repository.get_cards_for_account`, a new
function alongside the existing single-card lookup): exactly one card
returns its `delivery_status` as a bare string; more than one returns an
array of `{card_id, card_type, masked_card_number, delivery_status}`,
where `masked_card_number` is always `"****" + <last 4 digits>` — the full
card number is never read into a response.

Implemented in `app/services/aggregated.py`, reusing
`verification_sessions.resolve_session` and
`identity.verify_account_ownership` exactly as Phase 2/3 do (one token
resolution, one account lookup, regardless of how many flags are set) —
not by calling through each individual accounts.py/cards.py endpoint
function, which would have re-resolved the same token and re-run the same
ownership query once per flag.

## Aggregated action endpoint — `POST /api/v1/post-services`

The write-side counterpart to `get-services`: lets HeyBreez request several
account/card actions in one call, after HeyBreez has already obtained
explicit customer confirmation for each. Protected —
`verification_token` required; `customer_id`/`account_id` are never
accepted from the caller.

**Request-level validation (whole request rejected before anything runs):**
- No action flag `true` → `400`.
- A flag is `true` but its required companion value is missing (e.g.
  `set_online_purchases` without `online_purchases_enabled`, `change_email`
  without `new_email`) → `400`, naming which value(s) are missing.
- Missing/invalid/expired/inactive token → `401` (identical generic
  message, same as every other endpoint).

**Per-action results (whole request still returns `200`):** everything
that depends on database/account state — card ownership, ambiguous card
resolution, "card already active", an invalid numeric limit — is captured
per action into `results[<action_name>]`, so one action failing never
blocks or hides the others:
```json
{"results": {
  "activate_card": {"success": false, "status": "FAILED", "request_id": null, "reason": "Card is already active."},
  "change_email": {"success": true, "status": "PENDING_REVIEW", "request_id": 22, "reason": null}
}}
```
`status` is one of `COMPLETED` (a direct action was applied),
`PENDING_REVIEW` (a `SERVICE_REQUESTS`/`DOCUMENT_REQUESTS` row was created
for human follow-up), or `FAILED` (`reason` is always a short,
machine-readable code or an existing `BusinessRuleError`'s already-safe
message — never a raw exception or SQL error).

**Direct actions** (`activate_card`, `unfreeze_card`,
`set_online_purchases`, `set_international_usage`, `change_spending_limit`,
`change_atm_limit`) call the *exact* existing Phase 2 `cards.py` functions
with `confirmed=True` — no new mutation logic, no second confirmation
step (HeyBreez already got one).

**Human-reviewed actions** (`freeze_card`→`CardBlockReason.CUSTOMER_REQUEST`,
`stolen_card`→`STOLEN`, `lost_card`→`LOST`, `replacement_card`→
`CardReplacementReason.OTHER`, `damaged_card`→`DAMAGED`, plus
`change_address`/`change_email`/`change_mobile_number`/
`update_employment_details`) call the existing `cards.py`/
`customer_requests.py` request-creating functions unchanged — never touch
`CARDS.card_status` or the `CUSTOMERS` table directly. `request_account_statement`
calls the existing `documents.py` logic with `document_type=ACCOUNT_STATEMENT`.

**Card resolution without `card_id`:** every card-specific action accepts
`card_last4` (preferred — exactly 4 digits, leading zeros preserved as a
plain string) or the legacy `card_number` (kept only for backward
compatibility; `card_last4` takes priority whenever both are given).
Resolution always runs against `repository.get_cards_for_account`'s
result, which is already scoped to the token-resolved customer/account —
`card_last4` can therefore never match a card belonging to anyone else,
by construction, not just by a business-rule check.

- `card_last4` given → 0 matches → `card_not_found`; 1 match → resolved;
  more than 1 match (two cards sharing the same last 4 digits) →
  `card_identification_ambiguous`.
- `card_last4` not given, exactly one card on the account → auto-resolved
  (backward compatible with calls made before `card_last4` existed).
- `card_last4` not given, more than one card → `card_identification_required`
  (or resolved via the legacy `card_number`, if that's supplied instead).

Card responses never include a full card number (the `ActionResult` model
has no such field at all), and full card numbers are never logged.

**Freeze must always have a reason.** `freeze_card` additionally requires
`request_reason` — non-null and non-blank after stripping whitespace —
checked in the same up-front request-validation pass as every other
missing-conditional-value check, so a `freeze_card` request with no
reason is rejected with `400` before touching the database: no
`SERVICE_REQUESTS` row is created and the card is never touched.
`lost_card`/`stolen_card` do **not** require it (the flag itself already
conveys the category), but will still store it if given. The stripped
free-text reason is persisted in `SERVICE_REQUESTS.REQUEST_REASON` in
place of the bare category value (`CardBlockRequest.request_reason` in
`app/models/card.py`, used by `cards.create_card_block_request`); when no
free text is given (the `lost_card`/`stolen_card` common case),
`REQUEST_REASON` falls back to the category itself (`LOST`/`STOLEN`/
`CUSTOMER_REQUEST`) exactly as it always has. The resolved `CARD_ID` is
always persisted alongside it — `SERVICE_REQUESTS.CARD_ID` (with its
`FK_SERVICE_CARD` constraint) already existed before this change and
required no schema migration.

**Multiple actions, independent processing:** each requested action is
executed and reported independently — a failure in one never stops or
hides the others (see the `activate_card`/`change_email` example above).
This is **not** one Oracle transaction: each reused Phase 2 function opens
and commits its own `db_session()`, exactly as it does when called
directly by its own Phase 2 endpoint. This was a deliberate choice per the
brief ("prefer independent action results unless existing service
architecture strongly requires one transaction") — these are ten-plus
unrelated tables/rows with no cross-action invariant to protect, so
wrapping them in one transaction would add complexity without a
correctness benefit, at the cost of no longer being able to reuse the
existing per-action functions as-is.

## Tests

```bash
source venv/bin/activate
pytest -v
```

The suite includes:

- Pure unit tests of the verification logic (`tests/test_verification_unit.py`)
  with the DB layer mocked — covering success, wrong national ID, wrong
  account number, account owned by another customer, wrong amount, wrong
  merchant/type, case-insensitive merchant match, matching on
  `transaction_type` instead of merchant, no completed transactions, and
  simulated Oracle errors.
- API-level error handling test (`tests/test_api_error_handling.py`)
  confirming a database failure surfaces as a generic `503` with no
  credentials, stack traces, or driver internals in the response.
- Small read-only integration tests (`tests/test_integration.py`,
  `tests/test_health.py`) that exercise the real Oracle connection using the
  seeded mock data. They only `SELECT`; nothing is inserted, updated, or
  deleted.
- Phase 2 unit tests (`tests/test_accounts.py`, `test_cards.py`,
  `test_card_requests.py`, `test_customer_requests.py`, `test_complaints.py`,
  `test_callbacks.py`, `test_documents.py`, `test_db_session.py`) — all
  mocked at the repository layer, so they never touch the real database.
  They cover: balance/IBAN/status/held-amount/transactions retrieval,
  account and card ownership validation, card activation/unfreeze state
  transitions, online-purchase/international-usage toggles, spending/ATM
  limit changes (including rejecting non-positive limits), confirmation
  enforcement on every mutating action, card block and replacement requests
  (asserting `CARDS.card_status` is never touched), customer detail change
  requests, complaint creation and `CMP-######` reference formatting,
  callback requests, document requests, invalid enum values on every
  enum-typed field, and safe database-error propagation.
- `tests/test_api_error_handling.py` also verifies the new `NotFoundError`
  (→ 404) and `BusinessRuleError` (→ 400) handlers return their message
  as-is (both are always safe, human-facing text — never raw exceptions)
  while `DatabaseUnavailableError` (→ 503) still never leaks credentials or
  driver internals.
- **Demo data protection**: every Phase 2/3 test that would otherwise mutate
  business data (card toggles/limits, block/replacement requests,
  complaints, callbacks, document requests) is a mocked unit test — it
  never opens a real DB connection. `tests/test_integration.py` does hit
  the real database, but only ever inserts/updates rows in
  `VERIFICATION_SESSIONS` (the table that exists precisely to hold this
  kind of ephemeral session state) and reads `CUSTOMERS`/`ACCOUNTS`/
  `TRANSACTIONS`/`CARDS` — it never writes to those four tables.
- Phase 3 tests (`tests/test_verification_sessions.py`, plus additions to
  `test_accounts.py`, `test_cards.py`, `test_integration.py`,
  `test_api_error_handling.py`) cover: token issuance on successful
  verification, token unpredictability (two tokens from the same
  customer/account are never equal), that only the SHA-256 hash is ever
  passed to the repository/persisted (never the raw token), that a valid
  token permits a protected action end-to-end, that a missing/invalid/
  expired/inactive token is rejected with the identical generic `401`
  message, that the token correctly resolves to the customer/account it
  was issued for, that card ownership is still enforced after token
  resolution, that a token cannot be used to reach a card/account it
  wasn't issued for, and that database errors during token resolution are
  still handled safely (via the shared `db_session` wrapper).

## Logging & data handling

- National ID, account number, and other identifiers are masked in logs
  (`app/utils/masking.py`) — only the last 4 characters are logged.
- Database errors are logged server-side with full detail but never
  returned to API clients; clients only see a generic message.
- All SQL uses bind parameters (`python-oracledb` named binds) — no string
  concatenation of user input.

## Known assumptions / limitations

Phase 1:

- `oracledb` runs in default **thin mode** (no Oracle Instant Client
  required), which is compatible with the Oracle Database Free container.
- Connection pool sized `min=1, max=5` — reasonable for a POC, not tuned for
  production load.
- `GET /health` deliberately does not touch the database, per the spec's
  separate `GET /api/v1/database/health` endpoint for that purpose.

Phase 2:

- **No schema changes were made.** All Phase 2 tables/columns already
  existed and matched what was needed (identity-column PKs, `PENDING`/`OPEN`
  status defaults, `CURRENT_TIMESTAMP` defaults) — confirmed by inspecting
  `user_tab_columns`/`user_constraints` before writing any code.
- **No enum CHECK constraints exist in the database** for `request_type`,
  `request_status`, `complaint_category`, `card_status`, `delivery_status`,
  etc. (only `NOT NULL` and the two `0/1` boolean checks on
  `CARDS.online_purchases_enabled`/`international_usage_enabled`). Enum
  validity is therefore enforced entirely in the Pydantic layer, for the
  fields the spec explicitly enumerated: card block reason, card
  replacement reason, customer-detail-change `field`, and `document_type`.
- `CALLBACK_REQUESTS.request_type` and `DOCUMENT_REQUESTS.delivery_method`
  are **not** enumerated anywhere in the spec, so they're accepted as
  free-text strings (length-limited) rather than an invented enum — inventing
  one would have been a silent business-policy assumption, which the
  instructions said not to make.
- `activate_card`/`unfreeze_card` enforce a state precondition
  (`INACTIVE`→`ACTIVE`, `FROZEN`→`ACTIVE`) since the spec lists them as
  direct, non-reviewed actions distinct from the freeze/block flow; there is
  no direct way to set a card to `FROZEN` in this API (by design — only a
  human employee acting on a `CARD_BLOCK` service request would do that),
  so `unfreeze_card` will always 400 with the seeded demo card today. This
  mirrors the spec's own asymmetry (freezing needs review, the spec still
  asked for a direct unfreeze endpoint) rather than second-guessing it.
- (Superseded by Phase 3, kept for history) Phase 2's identity/ownership
  mechanism re-validated a caller-supplied `customer_id`/`account_id`
  against the database on every call, but didn't prove the caller was
  entitled to claim that `customer_id` in the first place. Phase 3's
  verification tokens close that gap — see below.
- Decimal fields (`balance`, `spending_limit`, transaction `amount`, etc.)
  serialize to JSON as **strings** (Pydantic v2's default for `Decimal`),
  e.g. `"1000"` not `1000` — this preserves exact precision instead of
  going through float, at the cost of clients needing to parse them as
  decimals rather than raw JSON numbers.

Phase 3:

- **One schema change**: the new `VERIFICATION_SESSIONS` table (see "Phase
  3: verification tokens" above). No existing table was altered.
- Only the SHA-256 hash of a token is ever persisted; the raw token exists
  only in the HTTP response body at issuance and in the caller's memory.
  There is no way to recover the raw token from the database, including by
  the backend itself.
- Token lifetime is fixed at 30 minutes and is not configurable via
  environment variable in this POC (`SESSION_LIFETIME` in
  `app/services/verification_sessions.py`) — deliberately simple, since the
  spec gave one concrete number.
- There is no logout/revoke endpoint and no cap on concurrent sessions per
  customer. A customer verifying twice gets two valid, independent tokens.
  Not needed for the stated requirements; would be a `PATCH .../deactivate`
  style addition later if HeyBreez needs it (e.g. on call end).
- Complaints/document-requests that reference an account now require a
  `verification_token` rather than a raw `account_id`; a bare `account_id`
  without a token is rejected with `400`. This is a stricter contract than
  Phase 2 shipped, per this task's explicit instruction that "the protected
  version should require a valid verification token" whenever
  account-specific data is involved.
- `datetime.now(timezone.utc).replace(tzinfo=None)` is used everywhere
  instead of `datetime.utcnow()` (both naive UTC) to avoid a Python 3.12
  deprecation warning while keeping the exact same semantics. All
  session-clock comparisons happen in Python against this consistent clock
  — never against Oracle's `CURRENT_TIMESTAMP`, whose timezone depends on
  the connecting session and isn't guaranteed to be UTC (confirmed during
  testing: the oracledb thin-mode session's `CURRENT_TIMESTAMP` differed
  from Python's UTC clock by several hours in this environment).

