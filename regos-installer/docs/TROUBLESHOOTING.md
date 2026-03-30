# Troubleshooting

## Common Issues

### "No running container matching 'open-webui'"

The installer can't find your Docker container. Check:

```bash
docker ps  # List running containers
```

If your container has a different name, use:

```bash
./install.sh --container <your-container-name>
```

### "neo4j not installed" after container restart

The `neo4j` pip package is installed inside the container's runtime filesystem. When the container restarts, it may be lost. Re-run:

```bash
./install.sh --step 02
```

Or manually:

```bash
docker exec -it open-webui pip install neo4j
```

### "OPENWEBUI_TOKEN is required"

Steps 05-07 need an API token. Get one from:

1. Open WebUI → click your profile icon → **Settings** → **Account** → **API Keys**
2. Create a new key and copy it

Then set it:

```bash
export OPENWEBUI_TOKEN=sk-...
./install.sh --step 05
```

### Functions registered but not working

1. Go to **Admin** → **Functions** in Open WebUI
2. Verify all 3 filters show as "Enabled" (toggle them on if not)
3. Check that `graphrag_filter` has **higher priority** than `audit_logger`
4. Verify Neo4j credentials are set in `graphrag_filter` Valves

### Threshold evaluation returns empty results

The `regulatory_thresholds.json` file may not be in the container. Verify:

```bash
docker exec open-webui ls -la /app/backend/data/regulatory_thresholds.json
```

If missing, re-run:

```bash
./install.sh --step 03
```

### API returns 401 Unauthorized

Your token may have expired. Generate a new one from Open WebUI Settings → Account → API Keys.

### API returns 403 Forbidden

Your user account may not have admin privileges. The installer requires an admin account to register functions and create models.

## Getting Help

- Check the install log: `regos-install.log`
- Run with verbose output: `./install.sh --verbose`
- Run verification only: `./install.sh --step 08`
