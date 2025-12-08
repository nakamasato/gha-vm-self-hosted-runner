# TODO: Improve Self-Hosted Runner Registration Token Management

## Current Limitations

To register the self-hosted runner on the VM, you need to obtain a **runner registration token** from GitHub's web UI (Repository Settings > Actions > Runners > New self-hosted runner). This token must be stored in Secret Manager before deploying the VM, and has the following limitations:

### 1. Token Expiration

- **Registration tokens from GitHub UI**: Expire after **1 hour**
- When recreating VM instances, you need to obtain a new token from GitHub UI
- **Fine-Grained Personal Access Tokens (PATs)**: Expire after a maximum of 1 year
- **Classic PATs**: Can be set to never expire, but are less secure

### 2. Manual Token Rotation Required

- The token stored in Secret Manager must be manually updated before expiration
- No automatic token refresh mechanism is currently implemented
- Expired tokens will prevent new runner registrations

### 3. Recommended Approach (Current Workaround)

- Use **Fine-Grained PATs** with the minimum required permissions:
  - Repository-level runners: `Repository permissions > Administration: Read and write`
- Set token expiration to the maximum allowed period (1 year)
- Implement a process to rotate tokens before expiration

## Proposed Improvements

### Option 1: GitHub App Authentication

- Implement GitHub App authentication for automatic token refresh
- Provides better security and eliminates manual token rotation
- GitHub Apps can generate installation access tokens that automatically refresh

### Option 2: Automated Token Rotation with PAT

- Create a Cloud Function or Cloud Run job that periodically refreshes tokens
- Use GitHub API to generate new runner registration tokens
- Automatically update Secret Manager with new tokens

### Option 3: Just-in-Time Token Generation

- Generate runner registration tokens on-demand when VM starts
- Use GitHub App or PAT to call GitHub API from startup script
- Eliminates need to store long-lived tokens in Secret Manager

## Implementation Steps

TBD - Choose one of the above options and implement it.

## Related

- [GitHub REST API - Actions Self-hosted runners](https://docs.github.com/en/rest/actions/self-hosted-runners)
- [GitHub Apps - About GitHub Apps](https://docs.github.com/en/developers/apps/getting-started-with-apps/about-apps)
