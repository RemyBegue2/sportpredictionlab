# Hotfix V4.1.2 — readiness recovery and test isolation

## Cause

The V4.1.1 startup logging regression test deliberately injected database and model startup failures but did not restore the process-wide `STARTUP_STATE`. A later webapp test then saw those stale diagnostics and received HTTP 503 from `/api/ready`, despite live database and model checks succeeding.

The same latch could affect production after a transient startup failure: readiness stayed blocked even after dependencies recovered.

## Fix

- `/api/ready` now treats current live dependency checks as the source of truth.
- Stale startup errors are cleared when database connectivity and model integrity are healthy.
- The startup logging test restores global state in `finally`.
- A regression test verifies recovery from stale startup diagnostics.

No database schema, prediction logic, evidence gate or provider-consumption logic changed.
