# Development

## CI/CD

### GitHub Actions Workflows

The project includes automated CI/CD pipelines:

#### Docker Build and Push
- **Workflow**: `.github/workflows/docker-publish.yml`
- **Triggers**:
  - Push to `main` branch
  - New version tags (`v*`)
  - Pull requests (build only, no push)
  - Manual workflow dispatch
- **Features**:
  - Multi-platform builds (amd64, arm64)
  - Automatic tagging strategy (latest, semver, sha)
  - Docker Hub description sync
  - GitHub Actions cache for faster builds

**Required Secrets**:
- `DOCKER_HUB_USERNAME`: Docker Hub username
- `DOCKER_HUB_TOKEN`: Docker Hub access token

#### Linting
- **Workflow**: `.github/workflows/lint.yml`
- **Triggers**: Push and pull requests affecting app code
- **Tools**: Ruff (Python linter and formatter)

### Setting Up Secrets

1. Create a Docker Hub access token:
   - Go to [Docker Hub Account Settings](https://hub.docker.com/settings/security)
   - Click "New Access Token"
   - Name it (e.g., "github-actions") and copy the token

2. Add secrets to your GitHub repository:
   - Go to repository Settings > Secrets and variables > Actions
   - Add `DOCKER_HUB_USERNAME` with your Docker Hub username
   - Add `DOCKER_HUB_TOKEN` with the access token

### Using the Docker Image

Pull the pre-built image from Docker Hub:

**For production:**
```bash
docker pull nakamasato/gha-vm-self-hosted-runner:latest
```

**For development/testing:**
```bash
docker pull nakamasato/gha-vm-self-hosted-runner-dev:latest
```

**Available tags:**

*PROD (`nakamasato/gha-vm-self-hosted-runner`):*
- `latest`: Latest release version
- `v1.0.0`, `v1.0`, `v1`: Semantic version tags (from git tags)

*DEV (`nakamasato/gha-vm-self-hosted-runner-dev`):*
- `latest`: Latest build from main branch
- `main`: Main branch builds
- `main-<sha>`: Commit-specific builds
- `pr-<number>`: Pull request builds

## Development

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality:

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

The pre-commit configuration includes:
- **Ruff**: Python linter with auto-fix
- **Ruff Format**: Python code formatter
- **Standard hooks**: Trailing whitespace, end-of-file-fixer, YAML checks, etc.
