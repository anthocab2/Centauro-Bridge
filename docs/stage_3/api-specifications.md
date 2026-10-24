# External Services and Internal API Specifications

## 1 Interface boundaries

Centauro Bridge is a local Python application with a CLI and Streamlit UI.
**Application-owned HTTP endpoints: not applicable to this MVP.** No `/jobs`,
`/login`, or other custom REST routes exist. The contracts below specify the
actual external service operations and internal Python/CLI interfaces.

## 2 Massive external API

The engine uses `GET https://api.massive.com` with this resource:

```text
/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}
Authorization: Bearer <runtime-secret>
```

| Input | Application format and behavior |
| --- | --- |
| ticker | Uppercase string matching `[A-Z0-9][A-Z0-9.:-]{0,31}`; CLI/UI normalize to uppercase |
| start_date, end_date | Exact valid YYYY-MM-DD strings, end on or after start |
| adjusted | Boolean in Request; serialized as lowercase true/false in provider query; default true |
| sort | asc |
| limit | 50000 in the extraction contract; 1 for the separate one-day probe |
| API key | Runtime authorization header; never a stored request parameter |

The provider's [Custom Bars documentation](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
describes aggregate OHLCV responses, millisecond timestamps, and optional
pagination. Access depends on the user's permitted operation and date range;
this document makes no subscription entitlement claim.

Illustrative response accepted by the current adapter; values are synthetic:

```json
{
  "ticker": "DEMO",
  "adjusted": true,
  "status": "OK",
  "resultsCount": 1,
  "results": [
    {"t": 1704191400000, "o": 100, "h": 104, "l": 99, "c": 103, "v": 1200}
  ]
}
```

The engine requires an object, `status: OK`, a `results` list, and a matching
nonnegative integer `resultsCount` when present. Valid emptiness is represented
by an empty list. A documented provider field being optional does not mean this
adapter currently accepts its omission: test omitted-results empty responses as
a compatibility case before changing that rule. Timestamps are transformed to
UTC for display; do not reinterpret provider daily windows as local browser dates.

`next_url` drives subsequent requests. Each authenticated pagination URL must
use HTTPS, host `api.massive.com`, no user information, and no port other than
443/default. Authentication query parameters are removed from persisted URLs;
the next request uses the authorization header. Do not accept arbitrary hosts.

### Timeouts, retries, and errors

The ingestion HTTP helper has a 30-second request timeout and up to four retries
after the first attempt for timeout exceptions or HTTP 429/500/502/503/504.
Exponential local delay is capped at 60 seconds; 429 uses at least 15 seconds
without Retry-After. A valid Retry-After value takes precedence and is **not**
capped by the local 60-second setting. These are request policies, not a maximum
job-duration guarantee. Other transport failures propagate to safe diagnostics.
401 and 403 are not retried by this helper. Their meaning is limited to observed
authentication/access rejection; they do not identify a subscription plan.

Source: [massive.py](../../src/centauro_atlas_bridge/sources/massive.py) and
[http_client.py](../../src/centauro_atlas_bridge/ingestion/http_client.py).

## 3 MongoDB Atlas external interface

The application uses the PyMongo driver with an authorized connection URI and
configured database, not the Atlas administration REST API. The engine creates
indexes, reads evidence, upserts raw fragments/runs/checkpoints/ledgers, and
records verification. The reader only reads the selected extraction's evidence.
The [data design](data-design.md#5-atlas-collection-structures-and-indexes)
defines collections, fields, and indexes.

The explicit reader/probe client uses Stable API version 1, timezone-aware
datetimes, and 10,000 ms server-selection/connect/socket timeouts. Those values
describe that client, not a blanket deadline for every ingestion operation.
Acceptance requires authorized read, write, and needed index-creation access to
a dedicated MVP database. Driver errors are translated at the application
boundary; neither a URI nor an arbitrary provider error body is returned to users.

## 4 Public input values

### Request

```json
{"ticker":"AAPL","start_date":"2024-01-02","end_date":"2024-01-05","adjusted":true}
```

This is an example of syntax, not a claim that this account can access those
dates. Python callers use `Request(...)`; strings/booleans are strictly validated.
Invalid input raises `InputError` before launching a worker.

### Profile

`Profile(profile_id, destination_id, database, massive_api_key, mongodb_uri,
provider="massive", destination="atlas", declared_plan="unknown")` is immutable.
Identifiers match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. Only Massive → Atlas is
supported. The URI must have a mongodb/mongodb+srv scheme and hostname; the API
key must be nonblank. These checks validate syntax, not connectivity.

`load_profile(Path(...))` loads a TOML file whose `massive_api_key_env` and
`mongodb_uri_env` name environment variables. See the credential-free
[example profile](../../profiles/mvp.example.toml).

Public representation, with a placeholder fingerprint:

```json
{
  "profile_id": "mvp",
  "provider": "massive",
  "destination": "atlas",
  "destination_id": "atlas-mvp",
  "database": "centauro_bridge_mvp",
  "destination_fingerprint": "<64-character-sha256>",
  "declared_plan": "unknown"
}
```

## 5 Internal Python contracts

| Callable | Input | Output and failure contract |
| --- | --- | --- |
| Coordinator(state_dir=None) | Optional Path identifying one local installation | Coordinator with State; all callers must share this location |
| Coordinator.start(profile, request) | Validated Profile, Request | Receipt dict: accepted, busy, or error; accepted is asynchronous |
| Coordinator.resume(job_id, profile) | Failed/interrupted job ID and same public profile | New receipt; invalid eligibility raises InputError; new job preserves request and extraction identity |
| State.status(job_id=None) | Optional job ID | One job dict or None; without ID, newest-first list of job dicts; may reconcile a confirmed dead worker |
| probe_atlas(profile) | Profile | confirmed with scope atlas_ping, write_access unknown, checked_at; otherwise unknown with safe diagnostic |
| probe_massive(profile, request) | One-day Request | confirmed for the tested operation with data_status and checked_at, exact_plan unknown; otherwise unknown/diagnostic; no persistence or pagination |
| read_extraction(profile, job) | Matching profile and stored job document | Immutable CanonicalDataset, or ReadingError with safe code; no writes |
| dataset_frame(dataset, start=None, end=None) | Dataset and optional Python date boundaries | pandas DataFrame filtered inclusively on UTC calendar dates |
| price_chart(frame) | The same filtered frame shown in the table | Plotly candlestick and volume figure |

The Massive probe has a 10-second timeout and no redirects; it does not use the
ingestion retry loop. A confirmed probe proves only that particular request.
`CanonicalDataset` contains `extraction_id`, `request`,
`destination_fingerprint`, `bars`, `captures`, `exact_duplicates`, `read_at`,
`snapshot_id`, and `provider`. `bar_count` is computed from reconstructed bars.
It is a Python object, not an automatically exposed HTTP JSON response.

## 6 CLI input and JSON output

Run from the repository after installing the locked Python 3.11 environment.
Credentials must already be configured privately. Global `--state-dir` belongs
before the subcommand; omit it to use the installation default.

```sh
uv run centauro-bridge start --profile profiles/mvp.example.toml AAPL 2024-01-02 2024-01-05
uv run centauro-bridge status JOB_ID
uv run centauro-bridge jobs
uv run centauro-bridge resume JOB_ID --profile profiles/mvp.example.toml
```

`start` also accepts `--unadjusted`. Substitute permitted dates/ticker; these
commands are documented examples, not a request to execute a live extraction.

Receipt shapes (IDs abbreviated with placeholders):

```json
{"status":"accepted","job_id":"<uuid-hex>","extraction_id":"<sha256>"}
```

```json
{"status":"busy","job_id":null}
```

```json
{"status":"error","diagnostic":{"code":"worker_start_unknown","message":"The worker did not acknowledge; query jobs before retrying.","http_status":null}}
```

The final error message above is illustrative; callers should branch on the
stable code, not compare prose. Busy may instead include the known active ID.
`status` returns the job object; `jobs` returns an array. Job fields and state
values are defined in [the SQLite/job contract](data-design.md#4-sqlite-schema-and-job-document).

| Exit code | Meaning |
| --- | --- |
| 0 | Accepted operation or successful query; a successful query may describe a failed job |
| 1 | Operational error |
| 2 | Invalid input |
| 3 | Installation busy |

A verified `result` contains mode, verified=true, data_status (empty/present/
unknown), bar_count=null, observed_pages (integer or null), and capability.
Mode is new/resumed/reused/recovered. Capability is confirmed only for an
actually completed new/resumed request, otherwise unknown; exact_plan remains
unknown. The canonical reader computes its own count without rewriting history.

## 7 Diagnostic and recovery contract

| Category | Codes/examples | User action |
| --- | --- | --- |
| Configuration and lifecycle | invalid_input, invalid_resume, worker_start, local_state | Correct syntax/eligibility or local permissions; do not expose rejected secrets |
| Uncertain startup | worker_start_unknown | Query jobs before preparing another attempt |
| External access | credentials, access_restricted, connection, rate_limited, provider_http | Check the relevant credential, permission, network, or wait for quota recovery |
| Job integrity | verification_failed, engine_failed | Inspect safe job state and stored evidence before retrying |
| Reader integrity | selection_mismatch, provenance_mismatch, missing_fragment, invalid_evidence, invalid_bar, bar_conflict, evidence_changed | Block viewing; correct selection/evidence or re-read after activity stops |
| Reader connection | read_failed | Check authorized connectivity and read access |

General job diagnostics contain code, safe message, and optional/null HTTP
status. Probe and reader diagnostics may contain only a code. Do not depend on
all fields being present. Avoid logging environment variables or raw error
objects in future changes.
