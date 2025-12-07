import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from github import Auth, GithubIntegration
from google.cloud import compute_v1, tasks_v2
from google.cloud.logging import Client

# Configure logging based on environment
# K_SERVICE is automatically set by Cloud Run
IS_CLOUD_RUN = os.getenv("K_SERVICE") is not None
if IS_CLOUD_RUN:
    # Cloud Run: Use Cloud Logging
    client = Client()
    client.setup_logging()
else:
    # Local development: Use local logging
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI()

# Environment variables
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
CLOUD_TASK_LOCATION = os.getenv("CLOUD_TASK_LOCATION")
CLOUD_TASK_QUEUE_NAME = os.getenv("CLOUD_TASK_QUEUE_NAME")
VM_INACTIVE_MINUTES = int(os.getenv("VM_INACTIVE_MINUTES", "3"))
CLOUD_RUN_SERVICE_URL = os.getenv("CLOUD_RUN_SERVICE_URL")
RUNNER_MANAGER_SECRET = os.getenv("RUNNER_MANAGER_SECRET")

# GitHub App configuration (for checking running jobs)
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY")
GITHUB_APP_INSTALLATION_ID = os.getenv("GITHUB_APP_INSTALLATION_ID")

# Runner configuration (JSON array)
# Format: [{"repo": "owner/repo", "labels": ["self-hosted"], "vm_instance_name": "...", "vm_instance_zone": "..."}]
RUNNER_CONFIG_STR = os.getenv("RUNNER_CONFIG", "[]")
try:
    RUNNER_CONFIG = json.loads(RUNNER_CONFIG_STR)
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid RUNNER_CONFIG JSON: {e}") from e

# Validate required environment variables
required_vars = {
    "GCP_PROJECT_ID": GCP_PROJECT_ID,
    "CLOUD_TASK_LOCATION": CLOUD_TASK_LOCATION,
    "CLOUD_TASK_QUEUE_NAME": CLOUD_TASK_QUEUE_NAME,
    "CLOUD_RUN_SERVICE_URL": CLOUD_RUN_SERVICE_URL,
    "RUNNER_MANAGER_SECRET": RUNNER_MANAGER_SECRET,
    "GITHUB_APP_ID": GITHUB_APP_ID,
    "GITHUB_APP_PRIVATE_KEY": GITHUB_APP_PRIVATE_KEY,
    "GITHUB_APP_INSTALLATION_ID": GITHUB_APP_INSTALLATION_ID,
    "RUNNER_CONFIG": RUNNER_CONFIG_STR,
}

missing_vars = [name for name, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# GCP clients
tasks_client = tasks_v2.CloudTasksClient()
compute_client = compute_v1.InstancesClient()

# GitHub App authentication
github_auth = Auth.AppAuth(int(GITHUB_APP_ID), GITHUB_APP_PRIVATE_KEY)
github_integration = GithubIntegration(auth=github_auth)


def find_matching_vm(repo_full_name: str, job_labels: list[str]) -> dict | None:
    """Find a VM configuration that matches the repository and job labels.

    Args:
        repo_full_name: Repository full name (e.g., "owner/repo")
        job_labels: List of job labels (e.g., ["self-hosted", "linux"])

    Returns:
        VM configuration dict if found, None otherwise
    """
    for vm_config in RUNNER_CONFIG:
        # Check if repo matches
        if vm_config.get("repo") != repo_full_name:
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


def verify_github_signature(payload: bytes, signature_header: str) -> bool:
    """Verify GitHub webhook signature using HMAC SHA256.

    Args:
        payload: Raw request body bytes
        signature_header: Value from X-Hub-Signature-256 header

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature_header:
        logger.warning("Missing X-Hub-Signature-256 header")
        return False

    if not RUNNER_MANAGER_SECRET:
        logger.error("RUNNER_MANAGER_SECRET not configured")
        return False

    # GitHub sends signature as "sha256=<hash>"
    try:
        hash_algorithm, signature = signature_header.split("=")
    except ValueError:
        logger.warning("Invalid signature header format")
        return False

    if hash_algorithm != "sha256":
        logger.warning(f"Unsupported hash algorithm: {hash_algorithm}")
        return False

    # Calculate expected signature
    mac = hmac.new(RUNNER_MANAGER_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    expected_signature = mac.hexdigest()

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_signature, signature)

    if not is_valid:
        logger.warning("Invalid webhook signature")

    return is_valid


def verify_runner_secret(secret_header: str | None) -> bool:
    """Verify runner control secret (uses same secret as GitHub webhook).

    Args:
        secret_header: Value from X-Runner-Secret header

    Returns:
        True if secret is valid

    Raises:
        HTTPException: If secret is missing or invalid
    """
    if not secret_header:
        logger.warning("Missing X-Runner-Secret header")
        raise HTTPException(status_code=401, detail="Missing X-Runner-Secret header")

    if not RUNNER_MANAGER_SECRET:
        logger.error("RUNNER_MANAGER_SECRET not configured")
        raise HTTPException(status_code=500, detail="Server configuration error")

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(RUNNER_MANAGER_SECRET, secret_header)

    if not is_valid:
        logger.warning("Invalid runner control secret")
        raise HTTPException(status_code=401, detail="Invalid secret")

    logger.info("Runner control secret verified")
    return is_valid


async def check_runner_busy(vm_config: dict) -> bool:
    """Check if the self-hosted runner is currently busy.

    Args:
        vm_config: VM configuration dict containing repo and vm_instance_name

    Returns:
        True if runner is busy, False if idle or not found
    """
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
        # On error, assume not busy to allow VM stop (fail open)
        return False


async def start_runner_if_needed(vm_config: dict):
    """Start the runner VM if it's not already running.

    Args:
        vm_config: VM configuration dict containing vm_instance_name and vm_instance_zone
    """
    try:
        vm_instance_name = vm_config.get("vm_instance_name")
        vm_instance_zone = vm_config.get("vm_instance_zone")

        instance = compute_client.get(
            project=GCP_PROJECT_ID, zone=vm_instance_zone, instance=vm_instance_name
        )

        if instance.status != "RUNNING":
            logger.info(f"Starting VM instance: {vm_instance_name}")
            operation = compute_client.start(
                project=GCP_PROJECT_ID, zone=vm_instance_zone, instance=vm_instance_name
            )
            logger.info(f"VM start operation initiated: {operation.name}")
        else:
            logger.info(f"VM instance {vm_instance_name} is already running")

    except Exception as e:
        logger.error(f"Error starting VM: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start VM: {str(e)}") from e


@app.post("/github/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    """GitHub Webhookを受信"""
    body = await request.body()

    # Webhook検証
    if not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event")

    logger.info(f"Received GitHub event: {event}, action: {payload.get('action')}")

    # Only handle workflow_job events
    if event != "workflow_job":
        return {"status": "ok"}

    workflow_job = payload.get("workflow_job", {})
    action = payload.get("action")
    repository = payload.get("repository", {})
    repo_full_name = repository.get("full_name")
    job_labels = workflow_job.get("labels", [])

    # Find matching VM configuration
    vm_config = find_matching_vm(repo_full_name, job_labels)
    if not vm_config:
        logger.info(
            f"Skipping: no matching VM found for repo={repo_full_name}, labels={job_labels}"
        )
        return {"status": "ok"}

    # Handle matching jobs
    if action == "queued":
        # VM起動（必要なら）
        await start_runner_if_needed(vm_config)

    elif action == "completed":
        # Schedule stop task after job completion
        await schedule_stop_task(vm_config)

    return {"status": "ok"}


@app.post("/runner/start")
async def start_runner(request: Request, x_runner_secret: str = Header(None)):
    """VMを起動"""
    # Verify runner control secret (from Cloud Tasks or manual)
    verify_runner_secret(x_runner_secret)

    try:
        body = await request.json()
        vm_instance_name = body.get("vm_instance_name")
        vm_instance_zone = body.get("vm_instance_zone")

        if not vm_instance_name or not vm_instance_zone:
            raise HTTPException(
                status_code=400,
                detail="vm_instance_name and vm_instance_zone are required in request body",
            )

        logger.info(f"Start endpoint called for VM: {vm_instance_name}")
        instance = compute_client.get(
            project=GCP_PROJECT_ID, zone=vm_instance_zone, instance=vm_instance_name
        )

        if instance.status != "RUNNING":
            logger.info(f"Starting VM instance: {vm_instance_name}")
            operation = compute_client.start(
                project=GCP_PROJECT_ID, zone=vm_instance_zone, instance=vm_instance_name
            )
            return {"status": "starting", "operation": operation.name}

        logger.info(f"VM instance {vm_instance_name} is already running")
        return {"status": "already_running"}

    except Exception as e:
        logger.error(f"Error in start_runner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start VM: {str(e)}") from e


@app.post("/runner/stop")
async def stop_runner(request: Request, x_runner_secret: str = Header(None)):
    """VMを停止（runnerがbusyでない場合のみ）"""
    # Verify runner control secret (from Cloud Tasks or manual)
    verify_runner_secret(x_runner_secret)

    try:
        body = await request.json()
        vm_instance_name = body.get("vm_instance_name")
        vm_instance_zone = body.get("vm_instance_zone")

        if not vm_instance_name or not vm_instance_zone:
            raise HTTPException(
                status_code=400,
                detail="vm_instance_name and vm_instance_zone are required in request body",
            )

        logger.info(f"Stop endpoint called for VM: {vm_instance_name}")

        # Find vm_config from RUNNER_CONFIG to check runner busy status
        vm_config = None
        for config in RUNNER_CONFIG:
            if (
                config.get("vm_instance_name") == vm_instance_name
                and config.get("vm_instance_zone") == vm_instance_zone
            ):
                vm_config = config
                break

        if not vm_config:
            logger.warning(
                f"VM config not found for {vm_instance_name} in {vm_instance_zone}, skipping runner busy check"
            )
        else:
            # Check if the runner is busy
            is_busy = await check_runner_busy(vm_config)
            if is_busy:
                logger.info(f"Skipping VM stop: runner '{vm_instance_name}' is busy")
                return {
                    "status": "skipped",
                    "reason": "runner_busy",
                }

        instance = compute_client.get(
            project=GCP_PROJECT_ID, zone=vm_instance_zone, instance=vm_instance_name
        )

        if instance.status == "RUNNING":
            logger.info(f"Stopping VM instance: {vm_instance_name}")
            operation = compute_client.stop(
                project=GCP_PROJECT_ID, zone=vm_instance_zone, instance=vm_instance_name
            )
            return {"status": "stopping", "operation": operation.name}

        logger.info(f"VM instance {vm_instance_name} is already stopped")
        return {"status": "already_stopped"}

    except Exception as e:
        logger.error(f"Error in stop_runner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop VM: {str(e)}") from e


async def schedule_stop_task(vm_config: dict):
    """Job完了後の指定時間後にstopを実行するCloud Taskを作成

    Args:
        vm_config: VM configuration dict containing vm_instance_name and vm_instance_zone
    """
    try:
        vm_instance_name = vm_config.get("vm_instance_name")
        vm_instance_zone = vm_config.get("vm_instance_zone")

        # タスク作成の準備（タイムスタンプでユニークなIDを生成）
        parent = tasks_client.queue_path(GCP_PROJECT_ID, CLOUD_TASK_LOCATION, CLOUD_TASK_QUEUE_NAME)
        timestamp = int(datetime.now(timezone.utc).timestamp())
        task_name = f"{parent}/tasks/stop-{vm_instance_name}-{timestamp}"
        schedule_time = datetime.now(timezone.utc) + timedelta(minutes=VM_INACTIVE_MINUTES)

        # Task payload with VM information
        payload = json.dumps(
            {"vm_instance_name": vm_instance_name, "vm_instance_zone": vm_instance_zone}
        ).encode()

        task = {
            "name": task_name,
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{CLOUD_RUN_SERVICE_URL}/runner/stop",
                "headers": {
                    "X-Runner-Secret": RUNNER_MANAGER_SECRET,
                    "Content-Type": "application/json",
                },
                "body": payload,
            },
            "schedule_time": schedule_time,
        }

        tasks_client.create_task(parent=parent, task=task)
        logger.info(f"Scheduled stop task for {vm_instance_name} at {schedule_time.isoformat()}")
        return {"scheduled_at": schedule_time.isoformat()}

    except Exception as e:
        logger.error(f"Error scheduling stop task: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to schedule stop task: {str(e)}"
        ) from e


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run"""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint with basic info"""
    return {
        "service": "GitHub Runner Manager",
        "inactive_minutes": VM_INACTIVE_MINUTES,
        "runner_configs": [
            {
                "repo": config.get("repo"),
                "labels": config.get("labels"),
                "vm_instance_name": config.get("vm_instance_name"),
                "vm_instance_zone": config.get("vm_instance_zone"),
            }
            for config in RUNNER_CONFIG
        ],
    }
