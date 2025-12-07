import hashlib
import hmac
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
VM_INSTANCE_ZONE = os.getenv("VM_INSTANCE_ZONE")
VM_INSTANCE_NAME = os.getenv("VM_INSTANCE_NAME")
CLOUD_TASK_LOCATION = os.getenv("CLOUD_TASK_LOCATION")
CLOUD_TASK_QUEUE_NAME = os.getenv("CLOUD_TASK_QUEUE_NAME")
VM_INACTIVE_MINUTES = int(os.getenv("VM_INACTIVE_MINUTES", "3"))
CLOUD_RUN_SERVICE_URL = os.getenv("CLOUD_RUN_SERVICE_URL")
RUNNER_MANAGER_SECRET = os.getenv("RUNNER_MANAGER_SECRET")

# GitHub App configuration (for checking running jobs)
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY")
GITHUB_INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # Format: "owner/repo"

# Target labels for runner filtering (comma-separated)
# Example: "self-hosted,linux" or "self-hosted"
TARGET_LABELS_STR = os.getenv("TARGET_LABELS", "self-hosted")
TARGET_LABELS = [label.strip() for label in TARGET_LABELS_STR.split(",") if label.strip()]

# Validate required environment variables
required_vars = {
    "GCP_PROJECT_ID": GCP_PROJECT_ID,
    "VM_INSTANCE_ZONE": VM_INSTANCE_ZONE,
    "VM_INSTANCE_NAME": VM_INSTANCE_NAME,
    "CLOUD_TASK_LOCATION": CLOUD_TASK_LOCATION,
    "CLOUD_TASK_QUEUE_NAME": CLOUD_TASK_QUEUE_NAME,
    "CLOUD_RUN_SERVICE_URL": CLOUD_RUN_SERVICE_URL,
    "RUNNER_MANAGER_SECRET": RUNNER_MANAGER_SECRET,
    "GITHUB_APP_ID": GITHUB_APP_ID,
    "GITHUB_APP_PRIVATE_KEY": GITHUB_APP_PRIVATE_KEY,
    "GITHUB_INSTALLATION_ID": GITHUB_INSTALLATION_ID,
    "GITHUB_REPO": GITHUB_REPO,
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


async def check_running_jobs() -> int:
    """Check how many workflow runs are currently running/queued on GitHub.

    Returns:
        Number of running/queued workflow runs
    """
    try:
        # Get installation access token
        installation_id = int(GITHUB_INSTALLATION_ID)
        access_token = github_integration.get_access_token(installation_id).token

        # Create GitHub client with installation token
        from github import Github

        github_client = Github(access_token)

        # Parse owner/repo
        owner, repo_name = GITHUB_REPO.split("/")
        repo = github_client.get_repo(f"{owner}/{repo_name}")

        # Get workflow runs that are queued, in_progress, or waiting
        runs = repo.get_workflow_runs(status="queued")
        queued_count = runs.totalCount

        runs = repo.get_workflow_runs(status="in_progress")
        in_progress_count = runs.totalCount

        total_running = queued_count + in_progress_count

        logger.info(
            f"GitHub workflow runs: queued={queued_count}, "
            f"in_progress={in_progress_count}, total={total_running}"
        )

        return total_running

    except Exception as e:
        logger.error(f"Error checking GitHub workflow runs: {e}")
        # On error, return 0 to allow VM stop (fail open)
        return 0


def should_handle_job(workflow_job: dict) -> bool:
    """Check if this job matches our target labels.

    Args:
        workflow_job: workflow_job object from GitHub webhook payload

    Returns:
        True if all target labels are present in job labels, False otherwise
    """
    job_labels = workflow_job.get("labels", [])
    has_all_target_labels = all(label in job_labels for label in TARGET_LABELS)

    logger.info(
        f"Job labels: {job_labels}, Target labels: {TARGET_LABELS}, "
        f"Match: {has_all_target_labels}, Runner: {workflow_job.get('runner_name', 'N/A')}"
    )

    return has_all_target_labels


async def start_runner_if_needed():
    """Start the runner VM if it's not already running."""
    try:
        instance = compute_client.get(
            project=GCP_PROJECT_ID, zone=VM_INSTANCE_ZONE, instance=VM_INSTANCE_NAME
        )

        if instance.status != "RUNNING":
            logger.info(f"Starting VM instance: {VM_INSTANCE_NAME}")
            operation = compute_client.start(
                project=GCP_PROJECT_ID, zone=VM_INSTANCE_ZONE, instance=VM_INSTANCE_NAME
            )
            logger.info(f"VM start operation initiated: {operation.name}")
        else:
            logger.info(f"VM instance {VM_INSTANCE_NAME} is already running")

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

    # Check if this job matches our target labels
    if not should_handle_job(workflow_job):
        logger.info(f"Skipping: job labels do not match target labels {TARGET_LABELS}")
        return {"status": "ok"}

    # Handle matching jobs
    if action == "queued":
        # VM起動（必要なら）
        await start_runner_if_needed()

    elif action == "completed":
        # Schedule stop task after job completion
        await schedule_stop_task()

    return {"status": "ok"}


@app.post("/runner/start")
async def start_runner(x_runner_secret: str = Header(None)):
    """VMを起動"""
    # Verify runner control secret (from Cloud Tasks or manual)
    verify_runner_secret(x_runner_secret)

    try:
        logger.info(f"Start endpoint called for VM: {VM_INSTANCE_NAME}")
        instance = compute_client.get(
            project=GCP_PROJECT_ID, zone=VM_INSTANCE_ZONE, instance=VM_INSTANCE_NAME
        )

        if instance.status != "RUNNING":
            logger.info(f"Starting VM instance: {VM_INSTANCE_NAME}")
            operation = compute_client.start(
                project=GCP_PROJECT_ID, zone=VM_INSTANCE_ZONE, instance=VM_INSTANCE_NAME
            )
            return {"status": "starting", "operation": operation.name}

        logger.info(f"VM instance {VM_INSTANCE_NAME} is already running")
        return {"status": "already_running"}

    except Exception as e:
        logger.error(f"Error in start_runner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start VM: {str(e)}") from e


@app.post("/runner/stop")
async def stop_runner(x_runner_secret: str = Header(None)):
    """VMを停止（実行中のジョブがない場合のみ）"""
    # Verify runner control secret (from Cloud Tasks or manual)
    verify_runner_secret(x_runner_secret)

    try:
        logger.info(f"Stop endpoint called for VM: {VM_INSTANCE_NAME}")

        # Check if there are any running/queued jobs
        running_jobs = await check_running_jobs()
        if running_jobs > 0:
            logger.info(f"Skipping VM stop: {running_jobs} workflow runs still running/queued")
            return {
                "status": "skipped",
                "reason": "jobs_running",
                "count": running_jobs,
            }

        instance = compute_client.get(
            project=GCP_PROJECT_ID, zone=VM_INSTANCE_ZONE, instance=VM_INSTANCE_NAME
        )

        if instance.status == "RUNNING":
            logger.info(f"Stopping VM instance: {VM_INSTANCE_NAME}")
            operation = compute_client.stop(
                project=GCP_PROJECT_ID, zone=VM_INSTANCE_ZONE, instance=VM_INSTANCE_NAME
            )
            return {"status": "stopping", "operation": operation.name}

        logger.info(f"VM instance {VM_INSTANCE_NAME} is already stopped")
        return {"status": "already_stopped"}

    except Exception as e:
        logger.error(f"Error in stop_runner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop VM: {str(e)}") from e


async def schedule_stop_task():
    """Job完了後の指定時間後にstopを実行するCloud Taskを作成"""
    try:
        # タスク作成の準備（タイムスタンプでユニークなIDを生成）
        parent = tasks_client.queue_path(GCP_PROJECT_ID, CLOUD_TASK_LOCATION, CLOUD_TASK_QUEUE_NAME)
        timestamp = int(datetime.now(timezone.utc).timestamp())
        task_name = f"{parent}/tasks/stop-{VM_INSTANCE_NAME}-{timestamp}"
        schedule_time = datetime.now(timezone.utc) + timedelta(minutes=VM_INACTIVE_MINUTES)

        task = {
            "name": task_name,
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{CLOUD_RUN_SERVICE_URL}/runner/stop",
                "headers": {"X-Runner-Secret": RUNNER_MANAGER_SECRET},
            },
            "schedule_time": schedule_time,
        }

        tasks_client.create_task(parent=parent, task=task)
        logger.info(f"Scheduled stop task at {schedule_time.isoformat()}")
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
        "instance": VM_INSTANCE_NAME,
        "zone": VM_INSTANCE_ZONE,
        "inactive_minutes": VM_INACTIVE_MINUTES,
        "target_labels": TARGET_LABELS,
    }
