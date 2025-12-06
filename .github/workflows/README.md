# GitHub Actions Workflows

This directory contains CI/CD workflows for the project.

## Workflows

### 1. Docker Build and Push (`docker-publish.yml`)

Automatically builds and publishes Docker images to Docker Hub with separate PROD and DEV repositories.

**Two Docker Hub Repositories:**
- **PROD**: `nakamasato/gha-vm-self-hosted-runner` (production releases only)
- **DEV**: `nakamasato/gha-vm-self-hosted-runner-dev` (development builds)

**Triggers:**
- **DEV builds** (to `-dev` repo):
  - Push to `main` branch (paths: `app/runner-manager/**`)
  - Pull requests (build only, no push)
  - Manual dispatch
- **PROD builds** (to prod repo):
  - New version tags (`v*`) only

**Image Tags:**

*DEV Repository (`nakamasato/gha-vm-self-hosted-runner-dev`):*
- `latest`: Latest build from main branch
- `main`: Main branch builds
- `main-<sha>`: Commit-specific builds from main branch
- `pr-<number>`: Pull request builds (not pushed)

*PROD Repository (`nakamasato/gha-vm-self-hosted-runner`):*
- `latest`: Latest release version
- `v1.0.0`, `v1.0`, `v1`: Semantic version tags (from git tags)

**Required Secrets:**
- `DOCKER_HUB_USERNAME`: Your Docker Hub username
- `DOCKER_HUB_TOKEN`: Docker Hub access token (create at https://hub.docker.com/settings/security)

**Features:**
- Multi-platform builds (linux/amd64, linux/arm64)
- Build cache using GitHub Actions cache
- Automatic README sync to Docker Hub
- Metadata extraction for proper tagging

**Manual Workflow Dispatch:**
You can manually trigger the workflow from the Actions tab:
1. Go to Actions > "Build and Push Docker Image"
2. Click "Run workflow"
3. Select branch and click "Run workflow"

### 2. Lint (`lint.yml`)

Runs code quality checks on the Python codebase.

**Triggers:**
- Push to `main` branch (paths: `app/runner-manager/**`)
- Pull requests

**Checks:**
- Ruff linting (code quality, imports, style)
- Ruff formatting (code formatting verification)

**No secrets required** - runs on public GitHub runners.

## Setup Instructions

### First-time Setup

1. **Create Docker Hub Access Token:**
   ```bash
   # Go to https://hub.docker.com/settings/security
   # Click "New Access Token"
   # Name: "github-actions"
   # Permissions: Read & Write
   # Copy the generated token
   ```

2. **Add GitHub Repository Secrets:**
   ```bash
   # Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions
   # Click "New repository secret"
   # Add the following secrets:
   # - Name: DOCKER_HUB_USERNAME, Value: your-dockerhub-username
   # - Name: DOCKER_HUB_TOKEN, Value: <paste-token-here>
   ```

3. **Verify Workflow Permissions:**
   - Go to repository Settings > Actions > General
   - Under "Workflow permissions", ensure:
     - "Read and write permissions" is selected
     - "Allow GitHub Actions to create and approve pull requests" is checked (optional)

### Development Workflow

**For development (DEV):**
1. Create a PR or push to main branch
2. Workflow automatically builds and pushes to `nakamasato/gha-vm-self-hosted-runner-dev`
3. Use `-dev` images for testing

**For production (PROD):**
1. Tag a release version:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```
2. Workflow automatically:
   - Builds multi-platform images
   - Pushes to `nakamasato/gha-vm-self-hosted-runner` (PROD)
   - Creates tags: `v1.0.0`, `v1.0`, `v1`, `latest`
   - Updates the README on Docker Hub

### Troubleshooting

**Issue**: Workflow fails with "unauthorized: authentication required"
**Solution**: Verify that `DOCKER_HUB_USERNAME` and `DOCKER_HUB_TOKEN` secrets are correctly set.

**Issue**: Workflow doesn't trigger on push
**Solution**: Ensure your changes are in the `app/runner-manager/` directory or workflow files.

**Issue**: Multi-platform build is slow
**Solution**: This is normal for the first build. Subsequent builds use GitHub Actions cache and are much faster.

**Issue**: README not syncing to Docker Hub
**Solution**: Verify `DOCKER_HUB_TOKEN` has "Read & Write" permissions (not just "Read").

## Summary: PROD vs DEV

| Aspect | PROD | DEV |
|--------|------|-----|
| **Docker Hub Repo** | `nakamasato/gha-vm-self-hosted-runner` | `nakamasato/gha-vm-self-hosted-runner-dev` |
| **Trigger** | Git tags (`v*`) only | Push to `main`, PRs |
| **Tags** | `latest`, `v1.0.0`, `v1.0`, `v1` | `latest`, `main`, `main-<sha>`, `pr-<number>` |
| **Purpose** | Stable production releases | Development and testing |
| **Frequency** | Manual (on version tags) | Automatic (on every push/PR) |

## Local Testing

Test the Docker build locally before pushing:

```bash
# Build for current platform
cd app/runner-manager
docker build -t test-image .

# Build for multiple platforms (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 -t test-image .

# Test the image
docker run --rm test-image python -c "import fastapi; print('OK')"
```

Test linting locally:

```bash
cd app/runner-manager
uv pip install ruff
ruff check .
ruff format --check .

# Auto-fix issues
ruff check --fix .
ruff format .
```
