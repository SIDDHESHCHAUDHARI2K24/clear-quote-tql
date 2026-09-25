# Backlog index

One folder per item: `spec.md` (human-approved scope and acceptance criteria), `plan.md` (agent plan), `handoff.md` (context handoffs), `post-dev.md` (results and evidence). Templates are in `_templates/`. Kaneo project **Clear Quote TQL** mirrors each row; Kaneo's own task number matches the backlog id (CQ-001 is Kaneo task CQ-1).

Status here is updated by the agent at stage 8 and by the human at merge.

| ID | Item | Phase | Depends on | Status |
| --- | --- | --- | --- | --- |
| [CQ-001](CQ-001-agent-tooling/spec.md) | Agent tooling & process | P0 | — | In Review |
| [CQ-002](CQ-002-monorepo-scaffold/spec.md) | Monorepo scaffold | P0 | CQ-001 | In Review |
| [CQ-003](CQ-003-local-infra/spec.md) | Local infrastructure | P0 | CQ-002 | In Review |
| [CQ-004](CQ-004-backend-skeleton/spec.md) | Backend skeleton | P0 | CQ-003 | In Review |
| [CQ-005](CQ-005-frontend-skeleton/spec.md) | Frontend skeleton & design system | P0 | CQ-002 | In Review |
| [CQ-006](CQ-006-ci/spec.md) | CI | P0 | CQ-004, CQ-005 | In Review |
| [CQ-007](CQ-007-data-model/spec.md) | Data model & migrations | P1 | CQ-004 | In Review |
| [CQ-008](CQ-008-quote-engine/spec.md) | Quote engine | P1 | CQ-004 | In Review |
| [CQ-009](CQ-009-mock-integrations/spec.md) | Mock integrations | P1 | CQ-007 | In Review |
| [CQ-010](CQ-010-seed-data/spec.md) | Seed data & demo reset | P1 | CQ-008, CQ-009 | In Review |
| [CQ-011](CQ-011-temporal-pipeline/spec.md) | Temporal pipeline | P1 | CQ-009, CQ-012, CQ-013 | In Review |
| [CQ-012](CQ-012-verification-rules/spec.md) | Verification rules | P1 | CQ-007 | In Review |
| [CQ-013](CQ-013-pricing-service/spec.md) | Pricing service & API | P1 | CQ-008, CQ-009 | In Review |
| [CQ-014](CQ-014-staff-auth/spec.md) | Staff auth | P2 | CQ-004, CQ-007 | In Review |
| [CQ-015](CQ-015-borrower-auth/spec.md) | Borrower auth | P2 | CQ-014 | In Review |
| [CQ-016](CQ-016-application-workspace/spec.md) | Application workspace shell | P3 | CQ-014, CQ-011 | In Review |
| [CQ-017](CQ-017-pricing-panel/spec.md) | Pricing panel | P3 | CQ-016, CQ-013 | In Review |
| [CQ-018](CQ-018-quote-builder/spec.md) | Quote builder | P3 | CQ-017 | To Do |
| [CQ-019](CQ-019-send-tab/spec.md) | Send tab & preview | P3 | CQ-018, CQ-021 | To Do |
| [CQ-020](CQ-020-letter-and-send/spec.md) | Letter PDF & send workflow | P3 | CQ-019, CQ-015 | To Do |
| [CQ-021](CQ-021-report-components/spec.md) | Shared report components | P4 | CQ-005, CQ-008 | In Review |
| [CQ-022](CQ-022-borrower-report/spec.md) | Borrower report page | P4 | CQ-021, CQ-015 | To Do |
| [CQ-023](CQ-023-property-matches/spec.md) | Property matches | P4 | CQ-022, CQ-013 | To Do |
| [CQ-024](CQ-024-borrower-actions/spec.md) | Borrower actions | P4 | CQ-022 | To Do |
| [CQ-025](CQ-025-dashboard/spec.md) | Dashboard | P5 | CQ-016 | To Do |
| [CQ-026](CQ-026-clients/spec.md) | Clients | P5 | CQ-016 | To Do |
| [CQ-027](CQ-027-applications-list/spec.md) | Applications list | P5 | CQ-016 | To Do |
| [CQ-028](CQ-028-verification-tabs/spec.md) | Verification tabs | P5 | CQ-016, CQ-012 | To Do |
| [CQ-029](CQ-029-timeline-outbox-panel/spec.md) | Timeline, Outbox, Integration panel | P5 | CQ-016, CQ-009 | To Do |
| [CQ-030](CQ-030-stale-quote-job/spec.md) | Stale quote job | P5 | CQ-011 | To Do |
| [CQ-031](CQ-031-borrower-home/spec.md) | Borrower home & status | P6 | CQ-015 | To Do |
| [CQ-032](CQ-032-apply-wizard/spec.md) | Apply wizard | P6 | CQ-031, CQ-011 | To Do |
| [CQ-033](CQ-033-hard-pull-consent/spec.md) | Hard-pull consent | P6 | CQ-031, CQ-028 | To Do |
| [CQ-034](CQ-034-support-form/spec.md) | Support form | P6 | CQ-031 | To Do |
| [CQ-035](CQ-035-railway-deploy/spec.md) | Railway deployment | P7 | CQ-020, CQ-024, CQ-025, CQ-026, CQ-027, CQ-028, CQ-029, CQ-030, CQ-032, CQ-033, CQ-034 | To Do |
| [CQ-036](CQ-036-e2e-demo/spec.md) | E2E & demo script | P7 | CQ-035 | To Do |
