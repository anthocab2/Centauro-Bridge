# Source Control Management and Quality Assurance

This is the proposed MVP maintenance and acceptance process. It does not claim
branch protections, CI jobs, reviewer assignments, or live tests were enabled
or completed by the documentation submission.

## 1 Source control plan

The canonical repository is
[anthocab2/Centauro-Bridge](https://github.com/anthocab2/Centauro-Bridge), with
`main` as the shared integration branch. Keep the local checkout and origin in
sync before starting changes. Use one issue per story or defect, labeled with
its US ID and MoSCoW priority.

1. Create a short-lived branch such as `feat/us-08-date-filter`,
   `fix/reader-missing-fragment`, or `docs/stage-3` from current main.
2. Make small commits with a clear problem/behavior description. Include tests
   for changed behavior and documentation for changed contracts. Commit `uv.lock`
   with intentional dependency updates.
3. Open a pull request linking the story, its acceptance criteria, a concise
   change description, and validation evidence. One change should not silently
   expand the approved scope.
4. Request peer/mentor review when available. Anthony is initially responsible
   for implementation and checks; the independent reviewer is to be confirmed.
   If working alone, record self-review honestly and request academic review
   before claiming team acceptance.
5. Resolve failures and review comments, merge after required checks, and remove
   the merged feature branch when no longer needed. Never force-push shared main.
6. Tag an accepted milestone, for example `mvp-validated-v1`, only after the
   corresponding acceptance evidence exists. Link the release to the evidence.

Proposed repository controls: require pull requests, passing automated checks,
and a review when a reviewer is available. These need configuration and are not
implied by this document. A future CI job should install Python 3.11 with the
locked dependencies and run the no-service checks below; external-service tests
must not run on untrusted contributions with secrets.

Use the existing `.gitignore` for `.env`, local profiles, virtual environments,
caches, and SQLite state. Check staged files for credentials and unrelated
artifacts before committing. Examples use environment-variable names and
synthetic values. Store real credentials outside Git and avoid echoing them in
shell history or CI output.

Rollback uses a normal revert commit plus validation, preserving shared history.
If storage contracts change, test migration and compatibility before release;
reverting code alone may not reverse persisted changes. Do not delete the
database or local job history to hide migration failures.

## 2 Quality assurance plan

### Reproducible automated checks

Use a clean local environment with no live-service credentials loaded. The
explicit ignore keeps the first command group independent of real Atlas tests:

```sh
uv sync --locked --python 3.11
uv run pytest -q --ignore=tests/integration
uv run ruff check .
git diff --check
```

Keep synthetic tests deterministic: mock provider responses, use temporary
state directories, and isolate MongoDB behavior with the project's test doubles.
Coordinator tests use subprocess fixtures to exercise actual locking and
recovery behavior. Streamlit AppTest exercises forms/reruns; visual and keyboard
checks still require manual review. No percentage-coverage result is asserted.

### Coverage and acceptance matrix

| ID / stories | Level and existing test area | Acceptance evidence required |
| --- | --- | --- |
| QA-01 / US-01, US-02 | Unit: tests/application/test_models.py; dashboard/test_connections.py | Valid and invalid request/profile cases, no secrets in public serialization; activation does not imply connectivity |
| QA-02 / US-02, US-03 | Unit: tests/unit/test_massive_validation.py, test_massive_pagination.py, test_http_client.py; application/test_adapter.py | Ordered pages, invalid responses, retry policy, separate execution/storage/verification states |
| QA-03 / US-04 | Process: tests/application/test_coordination.py; dashboard/test_app.py | Two overlapping requests produce exactly one accepted ingestion; other returns busy; reruns add no job |
| QA-04 / US-05 | Process and engine: application/test_coordination.py; unit/test_massive_resume.py, test_massive_completion_recovery.py | Controlled interruption, status reconciliation, new attempt linked to original request, successful recovery without duplicate fragments |
| QA-05 / US-06 | Engine: unit/test_raw_ingestion.py, test_page_ledger.py, test_massive_completion_recovery.py | Record raw IDs/counts before/after repeating a completed request; verified reuse and no duplicate inserts |
| QA-06 / US-07 | Unit: tests/reading/test_canonical.py; unit/test_verification.py, test_verification_provenance.py | Missing/corrupted/conflicting evidence blocked; valid empty data accepted; changed run/ledger during read rejected |
| QA-07 / US-08 | Unit/UI: tests/dashboard/test_presentation.py, test_app.py | Chart traces and table share filtered timestamps/OHLCV; reversed and empty ranges handled; UTC labels visible |
| QA-08 / US-09–US-11 | UI/probe: tests/dashboard/test_connections.py, test_app.py; application tests | Limited probes, safe diagnostics, CLI consistency, demo without network/jobs |
| QA-09 / charter objective 1 | Explicit live acceptance | Two permitted, distinct tickers, at most five trading days each; final verified jobs and Atlas evidence; at least one nonempty |
| QA-10 / charter objective 2 | Manual usability | Two volunteers independently open/filter from the guide in at most ten minutes after setup; record time and obstacles |
| QA-11 / charter objective 3 | Controlled acceptance on disposable fixtures/destination | Busy, interrupted resume, verified completed reuse, and corrupted/incomplete-read rejection demonstrated with recorded outcomes |

Paths in the test column are relative to `tests/` except when explicitly prefixed
with `tests/`. They identify existing coverage to retain and extend, not a claim
that every acceptance item already passed on live services.

### External-service validation

During Week 1, the authorized operator selects accessible dates/tickers and a
dedicated MVP database. Confirm network reachability and actual required
permissions. Never use a production/research database for destructive fixtures.

The integration fixture requires `CENTAURO_REAL_ATLAS=1`, `MONGODB_URI`, and
`MONGODB_DATABASE`. Without the explicit gate it skips these tests; missing
credentials after requesting a real run are a failure, not a pass. In a prepared
environment, run `uv run pytest -q tests/integration` and record results. Inspect
each test's writes and cleanup before enabling it. These database tests alone
do not prove a real Massive download.

For end-to-end acceptance, follow the [user guide](../user-guide.md) and
[existing validation procedure](../validation.md) with a valid Massive key and
dedicated Atlas destination. Execute the two small requests, reopen each through
the canonical reader, and compare the table/chart under a date filter. Record
IDs, request parameters, timestamps, final states, and redacted verification
results. Use an isolated copy/fixture for corruption and interruption scenarios;
do not alter valuable captures.

### Evidence record

For each scenario record: QA/story ID, source commit, Python/OS, synthetic or
real environment, safe destination alias, input, expected result, actual result,
pass/fail/blocked, UTC time, reviewer, and redacted artifact link. Use
`pending` before execution. A skipped test or unavailable service is not a pass.
Never include API keys, credential-bearing URIs, or raw connection exceptions.

### Definition of done

- Every Must Have story meets its acceptance criteria and the three charter
  objectives have recorded evidence.
- Relevant no-service tests and lint pass on the declared Python version.
- The live two-request path and both volunteer sessions are recorded.
- No unresolved defect blocks a Must Have story, leaks credentials, or allows
  invalid evidence to appear verified.
- README, user guide, diagrams, and interface contracts match the accepted code;
  an independent reviewer is identified or the missing review is openly recorded.

Anthony owns implementation and initial QA evidence. The mentor/peer reviews
acceptance; the two volunteers perform usability sessions once confirmed.
Week 1 checks setup/contracts, Week 2 proves the small data path, Week 3 checks
exploration/usability, and Week 4 checks resilience and handover.

## 3 Validation status at this documentation baseline

The repository's previous HBT-CEN-002 report records **190 passed, 6 skipped** on
Windows with Ruff passing. That is historical evidence, not a fresh run for
Stage 3. Live Massive + Atlas acceptance and volunteer sessions are still
pending. This change adds documentation and static assets only; its own checks
are listed in [validation.md](validation.md).
