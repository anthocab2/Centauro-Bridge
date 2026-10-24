# Centauro Bridge Project Charter

**Stage:** 2 — Project Charter Development

**Version:** 1.0

**Prepared:** 23 October 2026

**Project owner:** Anthony (`anthocab2`)

**Status:** Prepared for team and mentor review

This charter defines the purpose, boundaries, responsibilities, risks, and
completion criteria of the Centauro Bridge minimum viable product (MVP). It
supports the Holberton project planning assignment and gives the project owner
and reviewers a common basis for deciding whether the MVP is ready.

The existing project already includes a command-line interface and a local
dashboard. The plan below focuses on completing and demonstrating the agreed
workflow, including validation with real services. Existing code is a starting
point, not evidence that every objective has been achieved.

## 1 Project objectives

### Purpose

Centauro Bridge helps students and data researchers collect, check, and explore
daily market data through a local application. It connects the Massive data
provider to MongoDB Atlas storage, tracks each extraction, and presents verified
results in a table and chart. The project reduces the manual work involved in
running separate scripts and makes it clearer whether a request is still
running, has failed, or has produced data that can be trusted for further study.

### SMART objectives

SMART means specific, measurable, achievable, relevant, and time-bound. The
targets below use a proposed four-week validation and delivery period. Week 1
begins on the start date agreed by the project owner and academic reviewer;
calendar dates are not yet assigned.

1. **Complete a verified data workflow by the end of Week 2.** Run two small
   daily-data extractions for two distinct supported ticker symbols, each
   covering no more than five trading days. Both jobs must finish with verified
   results stored in the dedicated MVP database, and at least one must contain
   data. Record the request, final status, and verification outcome for each job.
   Select symbols and dates during Week 1 according to the available data access.

2. **Demonstrate usable data exploration by the end of Week 3.** After setup,
   two volunteer users must each open a verified extraction and apply a date
   filter using the written guide, without live assistance, within ten minutes.
   For both sessions, confirm that the table and chart show the same filtered
   records. Record completion time and any difficulties, and correct issues that
   prevent either user from finishing.

3. **Demonstrate reliable recovery and handover by the end of Week 4.** Pass
   four documented acceptance scenarios: a second simultaneous request is
   rejected as busy; an interrupted job can be resumed; repeating a completed
   request reuses its data without adding duplicate stored records; and altered
   or incomplete data is blocked from normal viewing. Deliver the user guide,
   test results, and a demonstration with no unresolved defect that prevents
   these scenarios or the two objectives above.

These targets are achievable within a small MVP because the application core
and dashboard already exist, requests are deliberately small, and there is one
provider and one storage destination. They remain dependent on valid service
access and the availability of two volunteer reviewers. Synthetic demonstrations
help development but do not count as completion of the real-data objective.

## 2 Stakeholders and roles

### Stakeholders

| Stakeholder | Interest and expected contribution |
| --- | --- |
| Anthony, project owner (`anthocab2`) | Sets priorities, maintains the repository, coordinates work, and reviews whether the MVP meets this charter. |
| Holberton mentor or academic reviewer | Reviews the assignment, gives feedback, and assesses the submitted work. Individual reviewer not yet assigned. |
| Student and research users | Need a clear way to request and inspect data. Two volunteers will participate in the usability check; names are not yet confirmed. |
| Development contributors | Implement agreed changes, document decisions, and review each other's work. Additional contributors have not been confirmed. |
| Owner of the MVP Atlas environment | Provides the authorized database destination and the necessary access for the application; assists with connection problems. Individual contact to be confirmed. |
| Massive and MongoDB Atlas | External service providers whose availability, access limits, and account permissions affect the workflow. They are dependencies, not project team members. |

### Team responsibilities

| Role | Responsibility | Initial assignment |
| --- | --- | --- |
| Project coordinator and product owner | Maintain priorities, track milestones, resolve scope questions, and arrange reviews. | Anthony |
| Application developer | Maintain extraction, storage, job tracking, recovery, and verification behavior. | Anthony initially |
| Dashboard and user documentation lead | Keep the interface and guide clear; prepare the usability sessions. | Anthony initially |
| Quality reviewer | Check acceptance evidence, report defects, and independently review the demonstration. | Peer or mentor to be confirmed |

One person may perform several roles. This is an initial working arrangement,
not a claim that other people have accepted assignments. The owner will confirm
the reviewer and volunteer users in Week 1. Contributors should review progress
weekly and record scope decisions in the repository so that feedback remains
visible to the group.

## 3 Scope

### In scope

- A local application for one user and one active extraction per installation.
- Daily market data from Massive for supported symbols and permitted dates.
- A dedicated MongoDB Atlas database as the storage destination.
- A dashboard and command-line entry point for starting jobs and checking status.
- Clear distinctions between accepted, running, failed, interrupted, and verified
  work, so accepting a request is not mistaken for completing it.
- Resuming interrupted work and reusing an already completed extraction.
- Verification before displaying stored results, including rejection of altered
  or incomplete data.
- A table and chart with consistent date filtering of daily open, high, low,
  close, and volume values, commonly called OHLCV.
- A user guide, acceptance evidence, and a small demonstration of real service
  integration. Synthetic data remains available for demonstrations without access.

### Out of scope

- Trading execution, broker connections, investment recommendations, or profit
  predictions.
- Artificial intelligence models, automated strategies, or advanced analytics.
- Real-time streaming, intraday data, additional data providers, or new datasets.
- A public hosted service, multiple user accounts, or coordination across machines.
- A job queue, automatic scheduling, or cancellation of running jobs.
- Large historical downloads or a redesign of the existing extraction engine.
- Publishing private research data, credentials, or provider data that cannot be
  redistributed under the applicable access terms.

The Stage 2 deliverable is this planning document. It does not authorize new
subscriptions or claim that the future implementation and acceptance work has
already been completed.

## 4 Risks and mitigation

Likelihood and impact are preliminary planning estimates, not measured incident
rates. The coordinator will revisit them at each weekly review.

| Risk | Likelihood / impact | Mitigation and response | Responsible role |
| --- | --- | --- | --- |
| Missing credentials, database permissions, or unstable connectivity delay real-data validation. | High / High | Check a small provider request and the intended database access in Week 1. Resolve access with the environment owner. Use synthetic data to continue interface work, but keep real-data acceptance pending. | Application developer and Atlas environment owner |
| Provider limits or unavailable historical dates prevent the chosen requests. | Medium / High | Choose two small, permitted requests early. Record observed restrictions and select supported dates or symbols; do not infer access from the account's plan label alone. | Application developer |
| Interrupted jobs, duplicate requests, or damaged stored data produce misleading results. | Medium / High | Keep verification and recovery in scope; run the four reliability scenarios and block normal viewing when evidence is invalid. | Application developer and quality reviewer |
| Credentials or private data appear in logs, screenshots, or Git commits. | Medium / High | Use protected local inputs, synthetic examples in public documentation, and review staged files and demonstration evidence before publishing. | Project coordinator |
| New feature requests make the MVP too large. | Medium / High | Compare requests with the out-of-scope list. Put optional ideas in a later backlog and document any approved effect on the current objectives or timeline. | Product owner |
| Limited contributor time or unavailable volunteers delay feedback. | Medium / Medium | Confirm availability in Week 1, review progress weekly, and arrange a substitute reviewer if necessary. Raise a schedule change if the two-user check cannot be completed. | Project coordinator |

If service access remains unresolved at the end of Week 1, the owner will record
the blocker and agree a revised validation date with the academic reviewer.
The project must not replace a missing real-data result with a claim of success.

## 5 High level plan

This is a proposed four-week plan from an agreed start date. The course deadline
and team availability must be confirmed before converting it into calendar dates.

| Phase | Timing | Main work | Exit evidence |
| --- | --- | --- | --- |
| Confirm the charter and prerequisites | Week 1 | Review purpose and scope, confirm roles and volunteers, inspect the existing implementation, and check service access for the two small requests. | Reviewed charter, named reviewers, selected requests, and an access readiness record or documented blocker. |
| Validate the data workflow | Week 2 | Complete the two small extractions, check storage and final verification, and resolve blocking integration defects. | Both jobs meet Objective 1 with recorded evidence. |
| Validate exploration and usability | Week 3 | Check the table and chart, run the two volunteer sessions, and improve the guide or interface where needed. | Both sessions meet Objective 2 and show consistent filtered data. |
| Check reliability and deliver | Week 4 | Run the four acceptance scenarios, resolve blocking defects, review public evidence, and demonstrate the MVP. | Objective 3 passes; guide, results, and demonstration are ready for review. |

### Resources and assumptions

The plan uses the existing repository and local development environment, the
Massive account, and an authorized Atlas destination. Service access, account
limits, contributor availability, and any financial budget are to be confirmed;
this charter makes no new spending commitment. The owner coordinates technical
delivery, while the academic reviewer determines assessment requirements.

### Review and changes

The owner and available contributors review the charter before adopting its
schedule. Record reviewer names, review date, requested changes, and the agreed
start date in a subsequent version. No team meeting, mentor approval, or user
test is claimed by this document. Changes affecting scope or success criteria
must update the charter and explain their effect on the remaining milestones.

### References

- [Centauro Bridge overview](../../README.md),
  [architecture](../architecture.md), and
  [user guide](../user-guide.md): existing product scope and behavior.
- [Atlassian project charter template](https://www.atlassian.com/software/confluence/templates/project-charter): charter structure.
- [Atlassian SMART goals guide](https://www.atlassian.com/blog/teamwork/how-to-write-smart-goals): objective-setting criteria.
