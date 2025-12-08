# TODO: Support Organization-Level Self-Hosted Runners

## Current Limitation

The runner manager currently supports **repository-level self-hosted runners only**. It checks the busy status of a specific runner registered to a repository using the GitHub API.

**Organization-level self-hosted runners** are not yet implemented in the current version.

## What Needs to Change

### 1. Runner Configuration Format

Add a `scope` field to the runner configuration to specify whether the runner is repository-level or organization-level:

**Current format:**
```json
[
  {
    "repo": "owner/repo",
    "labels": ["self-hosted"],
    "vm_instance_name": "github-runner",
    "vm_instance_zone": "asia-northeast1-a"
  }
]
```

**Proposed format:**
```json
[
  {
    "scope": "repository",  // or "organization"
    "repo": "owner/repo",   // for repository-level runners
    "org": "owner",         // for organization-level runners
    "labels": ["self-hosted"],
    "vm_instance_name": "github-runner",
    "vm_instance_zone": "asia-northeast1-a"
  }
]
```

### 2. Code Changes in `app.py`

#### 2.1. Update `check_runner_busy()` function (lines 178-219)

**Current implementation (repository-level only):**
```python
async def check_runner_busy(vm_config: dict) -> bool:
    """Check if the self-hosted runner is currently busy."""
    try:
        vm_instance_name = vm_config.get("vm_instance_name")
        repo_full_name = vm_config.get("repo")

        # Get installation access token
        access_token = github_integration.get_access_token(int(GITHUB_APP_INSTALLATION_ID)).token

        # Create GitHub client with installation token
        from github import Github
        github_client = Github(access_token)

        # Get repository
        repo = github_client.get_repo(repo_full_name)

        # Get all self-hosted runners
        runners = repo.get_self_hosted_runners()

        # Find our specific runner by name
        for runner in runners:
            if runner.name == vm_instance_name:
                is_busy = runner.busy
                logger.info(f"Runner '{vm_instance_name}': status={runner.status}, busy={is_busy}")
                return is_busy

        # Runner not found - safe to stop VM
        logger.warning(f"Runner '{vm_instance_name}' not found in GitHub")
        return False

    except Exception as e:
        logger.error(f"Error checking runner status: {e}")
        return False
```

**Proposed implementation (supporting both repository and organization):**
```python
async def check_runner_busy(vm_config: dict) -> bool:
    """Check if the self-hosted runner is currently busy."""
    try:
        vm_instance_name = vm_config.get("vm_instance_name")
        scope = vm_config.get("scope", "repository")  # Default to repository for backward compatibility

        # Get installation access token
        access_token = github_integration.get_access_token(int(GITHUB_APP_INSTALLATION_ID)).token

        # Create GitHub client with installation token
        from github import Github
        github_client = Github(access_token)

        # Get runners based on scope
        if scope == "organization":
            org_name = vm_config.get("org")
            if not org_name:
                logger.error("Organization name not provided for organization-level runner")
                return False
            org = github_client.get_organization(org_name)
            runners = org.get_self_hosted_runners()
        else:  # repository scope
            repo_full_name = vm_config.get("repo")
            if not repo_full_name:
                logger.error("Repository name not provided for repository-level runner")
                return False
            repo = github_client.get_repo(repo_full_name)
            runners = repo.get_self_hosted_runners()

        # Find our specific runner by name
        for runner in runners:
            if runner.name == vm_instance_name:
                is_busy = runner.busy
                logger.info(f"Runner '{vm_instance_name}': status={runner.status}, busy={is_busy}")
                return is_busy

        # Runner not found - safe to stop VM
        logger.warning(f"Runner '{vm_instance_name}' not found in GitHub")
        return False

    except Exception as e:
        logger.error(f"Error checking runner status: {e}")
        return False
```

#### 2.2. Update `find_matching_vm()` function (lines 75-102)

Add support for matching organization-level runners:

```python
def find_matching_vm(repo_full_name: str, job_labels: list[str]) -> dict | None:
    """Find a VM configuration that matches the repository and job labels."""
    for vm_config in RUNNER_CONFIG:
        scope = vm_config.get("scope", "repository")

        # For repository-level runners, match repo name
        if scope == "repository":
            if vm_config.get("repo") != repo_full_name:
                continue

        # For organization-level runners, match organization
        elif scope == "organization":
            org_name = vm_config.get("org")
            repo_org = repo_full_name.split("/")[0]  # Extract org from "org/repo"
            if org_name != repo_org:
                continue

        # Check if all target labels are present in job labels
        target_labels = vm_config.get("labels", [])
        if not all(label in job_labels for label in target_labels):
            continue

        logger.info(
            f"Found matching VM: {vm_config.get('vm_instance_name')} "
            f"for repo={repo_full_name}, labels={job_labels}"
        )
        return vm_config

    logger.info(f"No matching VM found for repo={repo_full_name}, labels={job_labels}")
    return None
```

### 3. GitHub App Permissions

Ensure the GitHub App has the necessary permissions:

**For organization-level runners:**
- Organization permissions > Self-hosted runners: Read-only

**Current (repository-level runners):**
- Repository permissions > Administration: Read-only

### 4. Documentation Updates

Update the following documentation:
- README.md: Update IMPORTANT section and Limitations section
- terraform/github-runner-manager/README.md: Add organization-level configuration examples
- app/runner-manager/README.md: Update runner configuration documentation

### 5. Terraform Variables

Add optional organization configuration to `terraform.tfvars`:

```hcl
runner_config = <<-EOT
[
  {
    "scope": "organization",
    "org": "your-org",
    "labels": ["self-hosted"],
    "vm_instance_name": "github-runner",
    "vm_instance_zone": "asia-northeast1-a"
  }
]
EOT
```

## Testing Plan

1. Test repository-level runners continue to work (backward compatibility)
2. Test organization-level runner registration and busy status check
3. Test webhook matching for organization-level runners
4. Verify GitHub App permissions are sufficient

## API References

- [GitHub REST API - List self-hosted runners for a repository](https://docs.github.com/en/rest/actions/self-hosted-runners?apiVersion=2022-11-28#list-self-hosted-runners-for-a-repository)
- [GitHub REST API - List self-hosted runners for an organization](https://docs.github.com/en/rest/actions/self-hosted-runners?apiVersion=2022-11-28#list-self-hosted-runners-for-an-organization)
- [GitHub REST API - Get a self-hosted runner for an organization](https://docs.github.com/en/rest/actions/self-hosted-runners?apiVersion=2022-11-28#get-a-self-hosted-runner-for-an-organization)

## Notes

- Organization-level runners can be assigned to jobs from different repositories within the organization
- The `busy` field is available in the GitHub API for both repository-level and organization-level runners
- Need to ensure proper webhook configuration at organization level to receive `workflow_job` events
