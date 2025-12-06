import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from google.cloud import compute_v1, tasks_v2

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Environment variables
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
ZONE = os.getenv("GCP_ZONE")
INSTANCE_NAME = os.getenv("VM_INSTANCE_NAME")
LOCATION = os.getenv("GCP_LOCATION")
QUEUE_NAME = os.getenv("QUEUE_NAME")
INACTIVE_MINUTES = int(os.getenv("INACTIVE_MINUTES", "15"))
SERVICE_URL = os.getenv("SERVICE_URL")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# Validate required environment variables
required_vars = {
    "GCP_PROJECT_ID": PROJECT_ID,
    "GCP_ZONE": ZONE,
    "VM_INSTANCE_NAME": INSTANCE_NAME,
    "GCP_LOCATION": LOCATION,
    "QUEUE_NAME": QUEUE_NAME,
    "SERVICE_URL": SERVICE_URL,
    "GITHUB_WEBHOOK_SECRET": GITHUB_WEBHOOK_SECRET,
}

missing_vars = [name for name, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# GCP clients
tasks_client = tasks_v2.CloudTasksClient()
compute_client = compute_v1.InstancesClient()


def verify_signature(payload: bytes, signature_header: str) -> bool:
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

    if not GITHUB_WEBHOOK_SECRET:
        logger.error("GITHUB_WEBHOOK_SECRET not configured")
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
    mac = hmac.new(GITHUB_WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256)
    expected_signature = mac.hexdigest()

    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(expected_signature, signature)

    if not is_valid:
        logger.warning("Invalid webhook signature")

    return is_valid


async def start_runner_if_needed():
    """Start the runner VM if it's not already running."""
    try:
        instance = compute_client.get(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)

        if instance.status != "RUNNING":
            logger.info(f"Starting VM instance: {INSTANCE_NAME}")
            operation = compute_client.start(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)
            logger.info(f"VM start operation initiated: {operation.name}")
        else:
            logger.info(f"VM instance {INSTANCE_NAME} is already running")

    except Exception as e:
        logger.error(f"Error starting VM: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start VM: {str(e)}") from e


@app.post("/github/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    """GitHub Webhookを受信"""
    body = await request.body()

    # Webhook検証
    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event")

    logger.info(f"Received GitHub event: {event}, action: {payload.get('action')}")

    if event == "workflow_job" and payload.get("action") == "queued":
        # VM起動（必要なら）
        await start_runner_if_needed()

        # 古いstopタスクを削除して新しいタスクをスケジュール
        await schedule_stop_task()

    return {"status": "ok"}


@app.post("/runner/start")
async def start_runner():
    """VMを起動"""
    try:
        logger.info(f"Start endpoint called for VM: {INSTANCE_NAME}")
        instance = compute_client.get(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)

        if instance.status != "RUNNING":
            logger.info(f"Starting VM instance: {INSTANCE_NAME}")
            operation = compute_client.start(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)
            return {"status": "starting", "operation": operation.name}

        logger.info(f"VM instance {INSTANCE_NAME} is already running")
        return {"status": "already_running"}

    except Exception as e:
        logger.error(f"Error in start_runner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start VM: {str(e)}") from e


@app.post("/runner/stop")
async def stop_runner():
    """VMを停止"""
    try:
        logger.info(f"Stop endpoint called for VM: {INSTANCE_NAME}")
        instance = compute_client.get(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)

        if instance.status == "RUNNING":
            logger.info(f"Stopping VM instance: {INSTANCE_NAME}")
            operation = compute_client.stop(project=PROJECT_ID, zone=ZONE, instance=INSTANCE_NAME)
            return {"status": "stopping", "operation": operation.name}

        logger.info(f"VM instance {INSTANCE_NAME} is already stopped")
        return {"status": "already_stopped"}

    except Exception as e:
        logger.error(f"Error in stop_runner: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop VM: {str(e)}") from e


async def schedule_stop_task():
    """15分後にstopを実行するCloud Taskを作成（古いタスクは削除）"""
    try:
        parent = tasks_client.queue_path(PROJECT_ID, LOCATION, QUEUE_NAME)
        task_name = f"{parent}/tasks/stop-{INSTANCE_NAME}"

        # 既存のタスクを削除（存在すれば）
        try:
            tasks_client.delete_task(name=task_name)
            logger.info(f"Deleted existing stop task: {task_name}")
        except Exception as e:
            logger.debug(f"No existing task to delete: {e}")

        # 15分後のタスクを作成
        schedule_time = datetime.now(timezone.utc) + timedelta(minutes=INACTIVE_MINUTES)

        task = {
            "name": task_name,
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{SERVICE_URL}/runner/stop",
                "oidc_token": {
                    "service_account_email": f"runner-controller@{PROJECT_ID}.iam.gserviceaccount.com"
                },
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
        "instance": INSTANCE_NAME,
        "zone": ZONE,
        "inactive_minutes": INACTIVE_MINUTES,
    }
