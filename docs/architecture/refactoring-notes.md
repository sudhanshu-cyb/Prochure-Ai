# Refactoring Notes

## Completed

- Added a public landing route at `/`.
- Moved the authenticated dashboard entry point to `/dashboard`.
- Added an API boundary for auth, dashboard, requests, analysis, comparison, approvals, rejection, and vendor performance.
- Added a responsive SPA shell and a separate premium landing visual system.
- Added reduced-motion handling and scroll-triggered workflow reveals.
- Added a relational Prisma schema for procurement, vendor location, assistant chat, search results, and AI audit records.
- Added an opt-in PostgreSQL request repository; the current `.env` selects `DATABASE_BACKEND=postgres`, while `DATABASE_BACKEND=json` remains available for isolated tests/offline development.
- Preserved legacy routes, service engines, Odoo adapter, JSON data, and existing response semantics.

## Compatibility

The legacy Jinja routes remain available so existing links, tests, and integrations do not break while the SPA is adopted. New UI actions use the explicit `/api/purchase-requests/...` endpoints. Existing `/api/approve/...` and `/api/reject/...` endpoints remain supported.

## Follow-up Migration

- Move route orchestration into Flask blueprints by domain (`auth`, `requests`, `vendors`, `approvals`, `dashboard`).
- Migrate the remaining assistant, vendor, PO, and audit repositories to normalized PostgreSQL tables and apply a reviewed Prisma migration; the request payload table is already active, and no destructive remote migration has been performed.
- Persist purchase orders and immutable audit events.
- Add CSRF protection and stronger production session configuration.
- Add automated browser tests for public landing, login, request creation, analysis, approval, rejection, and responsive breakpoints.
- Remove legacy templates only after browser parity is confirmed.
