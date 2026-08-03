# Hotfix V4.1.3 — Railway detached deployments

## Incident

Railway accepted the source upload and started the deployment, but the Railway CLI failed while opening the build-log stream:

```text
Failed to stream build logs: Failed to retrieve build log
```

Because every production workflow used `railway up --ci`, this observability failure returned exit code 1 and stopped GitHub Actions even when the deployment itself succeeded.

## Correction

Every production workflow now uses `railway up --detach`.

Detached mode returns after Railway has accepted and queued the deployment. Web deployments remain strictly verified by `scripts.post_deploy_verify`, which waits for:

- `/api/ready` to report `ready`;
- the expected application version;
- the exact expected source commit;
- the expected model SHA-256;
- responsible-use invariants.

The correction is applied to:

- Deploy production;
- Run evidence campaign;
- Run historical sample;
- Recompute latest evidence;
- Rebuild fresh football model;
- Rollback production.

Two regression tests prohibit a return to `railway up --ci` and require exact public release verification in every web-deployment workflow.
