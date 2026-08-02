# Hotfix V3.7.2 — Railway shadow service ID

## Cause

The web deployment succeeds, then the shadow deployment fails with `Service not found`.
The project, token and environment are accepted; the cron service target is not.

This hotfix stops relying on the display name `shadow-cron` and requires the exact
Railway service ID through the GitHub repository variable:

`RAILWAY_CRON_SERVICE_ID`

## Browser-only setup

1. Open the Railway project.
2. Select the service that runs the shadow cron.
3. Press `Ctrl + K`.
4. Choose `Copy Service ID`.
5. In GitHub open:
   `Settings > Secrets and variables > Actions > Variables`.
6. Create the repository variable:
   - Name: `RAILWAY_CRON_SERVICE_ID`
   - Value: the copied Railway service ID.
7. Replace the three workflow files from this archive.
8. Commit with:
   `Fix Railway shadow service targeting v3.7.2`
9. Start a new `Deploy production` workflow run.

Do not modify `RAILWAY_TOKEN`, PostgreSQL, or application variables.
