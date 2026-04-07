# APAS Prod Image — Build & Publish

This document describes how the **APAS production image** for Open WebUI is built, published, and updated. The image is designed for deployment on RunPod GPU pods with bundled Ollama and CUDA 12.8 support.

See also: `APAS_OpenWebUI_RunPod_Proposal.docx` (proposal) and `OPERATIONS.md` (legacy DO deployment).

---

## Overview

| Item | Value |
|---|---|
| Workflow file | `.github/workflows/apas-prod-build.yaml` |
| Dockerfile | `./Dockerfile` (upstream, unmodified) |
| Registry | `ghcr.io/apas-ai/open-webui-regos` |
| Platform | `linux/amd64` only (RunPod GPUs are amd64) |
| Trigger | Push to `main` or `regos-anmol-dev`, or manual `workflow_dispatch` |
| Cache | GitHub Actions cache, scoped `apas-prod` |

### Why a separate workflow?

The upstream `docker-build.yaml` builds several variants (`main`, `cuda`, `cuda126`, `ollama`, `slim`) but **none combines CUDA + Ollama**, which is exactly what we need for the bundled-Ollama-on-GPU production image. A separate workflow also:

- Keeps our customization out of the upstream-merge path — pulling from upstream never conflicts.
- Lets us tag independently (`:apas-prod` vs upstream's `:latest`, `:cuda`, etc.).
- Uses its own GHA cache scope so our builds and upstream builds don't fight over cache slots.

---

## Build arguments

| Arg | Value | Rationale |
|---|---|---|
| `USE_CUDA` | `true` | GPU acceleration. This is the Dockerfile's GPU switch (there is no separate `USE_GPU` arg). |
| `USE_CUDA_VER` | `cu128` | CUDA 12.8 — matches RunPod's current driver baseline. |
| `USE_OLLAMA` | `true` | Bundles the Ollama binary inside the image so a single container serves both Open WebUI and local Ollama. |
| `USE_SLIM` | `false` | Keep full image — we rely on bundled poppler / libreoffice / etc. for document processing. |
| `USE_PERMISSION_HARDENING` | `false` | Deferred — revisit after first deploy. |
| `USE_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Default. |
| `USE_AUXILIARY_EMBEDDING_MODEL` | `TaylorAI/bge-micro-v2` | Default. |
| `BUILD_HASH` | `${{ github.sha }}` | Stamped into the image for traceability. |

---

## Tags produced

| Tag | When | Purpose |
|---|---|---|
| `apas-prod` | Push to `main` | Rolling production tag — pod can point here for auto-update on restart. |
| `apas-prod-dev` | Push to `regos-anmol-dev` | Rolling dev tag — for test pods. |
| `apas-prod-git-<sha>` | Every build | Immutable pin — use for production pods so restarts don't silently upgrade. |

**Recommendation:** production pods should always point at an immutable `apas-prod-git-<sha>` tag, not the rolling `apas-prod` tag. Rolling tags are convenient for dev but make rollbacks ambiguous.

---

## Triggering a build

### Automatic (on push)

Any push to `main` or `regos-anmol-dev` that touches one of these paths triggers a build:

- `Dockerfile`
- `backend/**`
- `src/**`
- `package.json`, `package-lock.json`
- `pyproject.toml`
- `.github/workflows/apas-prod-build.yaml`

### Manual

From GitHub UI: **Actions → APAS Prod Image (CUDA + Ollama) → Run workflow**.

From the CLI:

```bash
gh workflow run apas-prod-build.yaml -R APAS-ai/open-webui-regos --ref main
```

### Watch the run

```bash
gh repo set-default APAS-ai/open-webui-regos   # once per clone
gh run watch
# or
gh run list --limit 5
gh run view <run-id> --log
```

---

## Expected build timings

| Build | Duration | Notes |
|---|---|---|
| Cold (no cache) | 15–25 min | First build ever, or after cache eviction. |
| Warm (cache hit) | 3–5 min | Typical subsequent builds. |
| Code-only change | 4–8 min | Frontend rebuild dominates. |
| Dependency change | 10–15 min | pip wheels + Ollama binary re-download. |

The GHA cache is scoped `apas-prod` and stored via `cache-to: type=gha,scope=apas-prod,mode=max`. Cache evicts after ~7 days of inactivity per GitHub's retention policy.

---

## Updating the image later

The update loop is:

1. Commit to `main` in `APAS-ai/open-webui-regos`.
2. GitHub Actions rebuilds and pushes (~5 min with cache).
3. Bump the pod's image tag in RunPod:
   - **For rolling:** just restart the pod (it pulls the new `:apas-prod` digest).
   - **For pinned:** edit the pod's image to the new `:apas-prod-git-<newsha>` tag, then restart.
4. On first boot, Open WebUI runs any Alembic migrations against the database on the network volume. User data (chats, configs, uploads, vectors) persists because it lives on the volume, not in the image.

### Rolling back

Point the pod at the previous `apas-prod-git-<oldsha>` tag and restart. Because the network volume is separate, downgrading the image doesn't lose data.

**Caveat:** if a database migration ran on upgrade, a downgrade can fail. For any upgrade crossing a migration boundary, **snapshot the RunPod network volume first** via RunPod's UI.

---

## Troubleshooting

<details>
<summary><b>Build fails with "no space left on device" on ubuntu-latest</b></summary>

CUDA wheels plus the Ollama binary are large. Add a cleanup step at the top of the build job:

```yaml
- name: Free disk space
  run: |
    sudo rm -rf /usr/share/dotnet /opt/ghc /usr/local/lib/android
    sudo docker system prune -af
    df -h
```
</details>

<details>
<summary><b>GHCR push fails with 403 permission denied</b></summary>

Check repo settings:

- **Settings → Actions → General → Workflow permissions** → must be "Read and write permissions".
- **Settings → Actions → General → Fork pull request workflows** → should not be required if you're pushing to your own branch.

If the package already exists, verify **Packages → open-webui-regos → Package settings → Manage Actions access** includes this repository with `write` role.
</details>

<details>
<summary><b>Image is private; RunPod can't pull</b></summary>

Two options:

1. **Make the package public** (image only — repo stays private). Packages → open-webui-regos → Package settings → Change visibility → Public. This is the simplest path and is what we're using.
2. **Use RunPod container registry credentials.** Create a classic PAT with `read:packages` scope, add it in RunPod → Settings → Container Registry Auth, then pod pulls authenticated.
</details>

<details>
<summary><b>Workflow didn't trigger on push</b></summary>

The workflow has a `paths:` filter. If your commit only touches docs, tests, or unrelated files, it won't trigger. Either run it manually via `workflow_dispatch`, or add your touched path to the filter list.
</details>

<details>
<summary><b>Cache keeps missing</b></summary>

GHA cache is scoped by branch. Pushes to `main` and `regos-anmol-dev` share the `apas-prod` scope, but cache is only written once the build succeeds. If the first run failed, the second run is also cold. Let one build succeed first, then subsequent runs will be fast.
</details>

---

## Package visibility

The GHCR package at `ghcr.io/apas-ai/open-webui-regos` should be **public** for the image (source repo remains private). This lets RunPod pull without needing registry credentials while keeping our code private.

To change visibility:

1. `https://github.com/orgs/APAS-ai/packages/container/open-webui-regos/settings`
2. **Danger Zone → Change visibility → Public**

---

## File locations

```
.github/workflows/apas-prod-build.yaml   # the CI workflow
Dockerfile                                # upstream — unmodified
docs/APAS_PROD_BUILD.md                   # this file
APAS_OpenWebUI_RunPod_Proposal.docx       # deployment proposal
OPERATIONS.md                             # legacy DO deployment notes
```

---

## Next steps

After the first successful build:

1. Make the GHCR package public (see above).
2. Create the RunPod template pointing at `ghcr.io/apas-ai/open-webui-regos:apas-prod-git-<sha>`.
3. Author `start.sh` for first-boot symlinks, Ollama bring-up, and idempotent regos-installer invocation.
4. Provision the pod, attach network volume, inject secrets via RunPod secret manager.
5. Validate: healthcheck, login, each of the three LLM backend modes, Function installation.
