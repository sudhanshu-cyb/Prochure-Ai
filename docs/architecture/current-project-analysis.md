# Current Project Analysis

## Existing Architecture

PROCUREAI is a Flask application with a JSON persistence layer and a migration-ready PostgreSQL/Prisma schema. The domain engines live in `services/`: vendor scoring, risk analysis, approval rules, AI explanations, and Odoo integration. Purchase requests currently run through `data/purchase_requests.json` and `data/db.py`; the Prisma schema defines the target relational source of truth.

The original UI was server-rendered Jinja templates using Bootstrap, Font Awesome, Chart.js, and inline JavaScript. A first modernization introduced a lightweight SPA in `static/js/app.js` and `static/css/app.css`, while retaining legacy routes and templates for compatibility.

## Implemented Product Areas

- Session authentication and demo RBAC roles
- Purchase request creation and persistence
- Vendor scoring and recommendation
- Procurement risk evaluation
- Approval and rejection workflows
- Mock/live Odoo purchase-order integration
- Vendor performance data
- Dashboard metrics and request history
- AI explanation fallback behavior

## Legacy Problems

- Route orchestration, authentication, and view-model construction were concentrated in `app.py`.
- Page routes and JSON actions were mixed together.
- The presentation depended on multiple legacy templates and duplicated workflow JavaScript.
- There was no public product entry point or stable frontend API boundary.
- Demo persistence and integrations remain intentionally lightweight and are not production database infrastructure.

## Refactoring Strategy

1. Preserve the service engines, data shape, session roles, and legacy endpoints.
2. Add explicit JSON API endpoints for the SPA: auth, dashboard, requests, comparison, approvals, and vendor performance.
3. Make `/` public and use it for the ProcureAI marketing experience; move the authenticated command center to `/dashboard`.
4. Keep legacy Jinja routes operational while users migrate to the SPA.
5. Isolate the new design system in `app.css` and `landing.css`.
6. Validate Python compilation, JavaScript syntax, route responses, and the existing regression suite after each milestone.

## Current Technology Decision

A dependency-light vanilla JavaScript SPA is used instead of introducing React/Vite during this incremental migration. This matches the existing Flask deployment, avoids a second build pipeline, and keeps the product runnable with the current Python environment. The frontend is structured around API-backed route views and can be migrated to React later without changing the API contract.
