# High-Level Sequence Diagrams

These diagrams describe the current local MVP. Arrows to Atlas may represent
several driver operations; they do not imply one atomic transaction.

## 1 Submit, reject overlap, and observe completion

```mermaid
sequenceDiagram
    actor User
    participant Caller as Dashboard or CLI
    participant Core as Coordinator
    participant Worker
    participant Local as Lock and SQLite
    participant Engine as Adapter and ingestion engine
    participant Massive
    participant Atlas
    User->>Caller: Submit fixed profile and request
    Caller->>Core: start(profile, request)
    Core->>Worker: Spawn with public input and explicit<br/>secret environment
    Worker->>Local: Try nonblocking installation lock
    alt Lock unavailable or active owner still visible
        Worker-->>Core: busy, active job ID when known
        Core-->>Caller: Busy receipt
    else Lock acquired and no active owner
        Worker->>Local: Recover dead jobs, save new preparing<br/>job
        Worker-->>Core: accepted, job_id, extraction_id
        Core-->>Caller: Receipt, not completion
        Worker->>Engine: execute(request, progress)
        Engine->>Local: executing
        loop Each required page for a new or resumed extraction
            Engine->>Massive: Authenticated HTTPS GET
            Massive-->>Engine: Validated page and optional next URL
            Engine->>Atlas: Upsert raw fragments, register ledger,<br/>save checkpoint
        end
        Engine->>Local: verifying, execution completed
        Engine->>Atlas: Verify stored extraction evidence
        alt Evidence valid
            Engine-->>Worker: verified result
            Worker->>Local: verified, result, finished_at
        else Error or invalid evidence
            Worker->>Local: failed and safe diagnostic
        end
        Worker->>Local: Release lock when worker exits
    end
    User->>Caller: Refresh status
    Caller->>Local: Read/reconcile state
    Local-->>Caller: Current job document
```

[SVG](diagrams/submission.svg) · [Mermaid source](diagrams/submission.mmd)

The caller receives acceptance before extraction finishes. The detached worker
continues after the caller closes. The worker holds the same installation lock
through the job. Dashboard submission tokens prevent reruns from resubmitting;
the core lock also covers competing CLI processes. A missing receipt after the
Coordinator's wait produces `worker_start_unknown`, not proof of failure: query
jobs before trying again. The loop depicts new/resumed fetching; a completed
request can follow the reuse path below without a new provider download.

## 2 Resume, reuse, and recovery

```mermaid
sequenceDiagram
    actor User
    participant Core as Coordinator and State
    participant Worker
    participant Engine
    participant Atlas
    User->>Core: Query status after interruption
    Core->>Core: Acquire lock and check PID, creation<br/>time, token
    alt Worker confirmed dead
        Core->>Core: Mark active attempt interrupted
    else Alive or visibility unknown
        Core-->>User: Preserve active state, do not overlap
    end
    User->>Core: resume(job_id, original profile)
    Core->>Core: Require failed/interrupted and matching<br/>public target
    Core->>Worker: Spawn using original request and<br/>resumed_from
    Worker->>Worker: Lock, recheck eligibility, create new<br/>job ID
    Worker->>Engine: Execute same extraction ID
    Engine->>Atlas: Read run and checkpoint
    alt Completed checkpoint
        Engine->>Atlas: Verify evidence and reconcile run when<br/>needed
        Note over Engine,Atlas: Reused or recovered mode, provider<br/>access remains unknown
    else Partial progress or no checkpoint
        Engine->>Engine: Continue ingestion from recorded<br/>progress
        Engine->>Atlas: Persist remaining evidence and verify
    end
    alt Valid evidence
        Worker->>Core: Persist verified outcome
    else Inconsistent evidence or operational failure
        Worker->>Core: Persist failed outcome and safe<br/>diagnostic
    end
    Core-->>User: New attempt linked to the original
```

[SVG](diagrams/recovery.svg) · [Mermaid source](diagrams/recovery.mmd)

Resume creates a new attempt with the same extraction identity and fixed
request. Renewed credentials are permitted only when the public target still
matches. The engine determines mode from Atlas evidence. An ordinary repeated
`start` for a completed request reaches the same completed-checkpoint branch;
it does not require `resume`. Verification failure is never silently repaired
by declaring success; investigate the evidence before retrying.

## 3 Open verified data and filter both views

```mermaid
sequenceDiagram
    actor User
    participant UI as Dashboard
    participant Reader as Canonical reader
    participant Atlas
    participant Verify as Pure verifier and reconstruction
    participant Frame as Filtered DataFrame
    User->>UI: Select extraction and verify/open
    UI->>Reader: read_extraction(profile, job)
    Reader->>Reader: Validate profile and extraction<br/>identity
    alt Selection mismatch
        Reader-->>UI: ReadingError(selection_mismatch)
        UI-->>User: Safe diagnostic, no dataset
    else Selection valid
        Reader->>Atlas: Read run and ordered page ledger
        Reader->>Atlas: Read only canonical IDs for this<br/>extraction
        Reader->>Verify: Verify exact evidence, reconstruct and<br/>validate bars
        alt Missing, altered, invalid, or conflicting evidence
            Verify-->>Reader: Stable diagnostic code
            Reader-->>UI: ReadingError
            UI-->>User: Block data view
        else Valid evidence
            Reader->>Atlas: Read run and ledger again
            alt Metadata changed during read
                Reader-->>UI: ReadingError(evidence_changed)
            else Evidence unchanged
                Reader-->>UI: Immutable CanonicalDataset
                User->>UI: Set inclusive UTC dates
                UI->>Frame: dataset_frame(dataset, start, end)
                Frame-->>UI: Same rows for chart and table
                UI-->>User: Candles, volume and table, or valid<br/>empty state
            end
        end
    end
```

[SVG](diagrams/verified-read.svg) · [Mermaid source](diagrams/verified-read.mmd)

The dashboard clears the prior dataset when opening another job or starting a
new read. Driver/connection failures map to `read_failed`; no raw exception or
credentials reach the view. A historical verified job still needs a fresh
reader check. The reader does not write data or refresh historical bar counts.
An empty but valid result returns an empty dataset with provenance, not an error.
