# Stage 3 — Technical Documentation

**Project:** Centauro Bridge · **Prepared:** 23 October 2026

This submission translates the [Stage 2 charter](../stage_2/PROJECT_CHARTER.md)
into a technical plan for a local daily-market-data MVP. All Stage 3 documents
are written in English. The current dashboard uses Spanish labels; the mockups
use English translations for the assignment.

Start with the [complete technical document](TECHNICAL_DOCUMENTATION.md).
For the explicitly listed Task 0, submit
[0-user_stories_and_mockups.md](0-user_stories_and_mockups.md).

| Required deliverable | Document |
| --- | --- |
| Prioritized user stories and main screens | [Task 0: stories and mockups](0-user_stories_and_mockups.md) |
| System architecture and component responsibilities | [Technical documentation](TECHNICAL_DOCUMENTATION.md) |
| Classes, collection structures, relationships, indexes | [Data and component design](data-design.md) |
| Key interactions, errors, and recovery | [Sequence diagrams](sequence-diagrams.md) |
| External services and internal input/output contracts | [API specifications](api-specifications.md) |
| Source control, QA, acceptance evidence | [SCM and QA plan](scm-and-qa.md) |
| Technical choices and tradeoffs | [Technical documentation, section 7](TECHNICAL_DOCUMENTATION.md#7-technical-justifications) |

## Mockups

The three static mockups are design artifacts with synthetic values, not
screenshots of a successful service connection. Open the HTML files in a browser
to navigate between screens. They make no API calls and collect no credentials.

| Screen | Preview | Editable source |
| --- | --- | --- |
| Connections | [PNG](mockups/01-connections.png) | [HTML](mockups/01-connections.html) |
| Extractions | [PNG](mockups/02-extractions.png) | [HTML](mockups/02-extractions.html) |
| Verified data | [PNG](mockups/03-data.png) | [HTML](mockups/03-data.html) |

Diagrams are embedded as Mermaid in the documents. Their editable `.mmd` files
and rendered SVGs are in [diagrams](diagrams/). Markdown text explains each
diagram for readers who cannot use the visual version.

## Status and boundaries

This is a complete documentation submission prepared for team/mentor review.
Implementation descriptions refer to public `main` at
[`4909630`](https://github.com/anthocab2/Centauro-Bridge/commit/4909630a22d72b7a77990a0e7ac598777f4bf08c).
The application code is not changed by this submission. Plans and acceptance
targets are labeled separately from existing behavior. Live Massive + Atlas
acceptance and the two volunteer sessions remain pending; synthetic mockups
and earlier automated tests do not establish that those milestones passed.
