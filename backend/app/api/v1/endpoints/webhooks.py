"""GitHub push webhook: start the scheduled refresh's incremental run for the pushed branch now."""

import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.repository import Repository
from app.services.github_service import parse_repository_url
from app.services.repository_service import RepositoryBusyError, start_processing

logger = structlog.get_logger(__name__)

router = APIRouter()


def signature_is_valid(secret: str, body: bytes, signature: str | None) -> bool:
    """GitHub signs the raw body: X-Hub-Signature-256 is sha256=<hex HMAC-SHA256 with the secret>"""
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(signature.encode(), expected.encode())


# No API key: GitHub can't send one, so the signature is this endpoint's authentication
@router.post("/github", status_code=202)
async def github_push(
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict:
    secret = get_settings().github_webhook_secret
    if not secret:
        raise HTTPException(status_code=404, detail="The GitHub webhook is off; set GITHUB_WEBHOOK_SECRET")
    body = await request.body()
    if not signature_is_valid(secret, body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Hub-Signature-256")
    if x_github_event != "push":
        # GitHub sends a ping when the webhook is created
        return {"detail": f"Ignored '{x_github_event}' event", "started": []}

    try:
        payload = json.loads(body)
        ref = payload["ref"]
        host, path, _ = parse_repository_url(payload["repository"]["html_url"])
        default_branch = payload["repository"].get("default_branch")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="Not a GitHub push payload") from e
    if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
        return {"detail": f"Ignored push to {ref}, not a branch", "started": []}
    branch = ref.removeprefix("refs/heads/")

    started, busy = [], []
    # The same repositories the scheduled refresh considers: completed, with an indexed commit
    for repository in (
        db.query(Repository)
        .filter(Repository.status == "completed", Repository.commit_sha.isnot(None))
        .order_by(Repository.id)
    ):
        repo_host, repo_path, _ = parse_repository_url(repository.url)
        if (repo_host, repo_path.lower()) != (host, path.lower()):
            continue
        if (repository.branch or default_branch) != branch or payload.get("after") == repository.commit_sha:
            continue
        try:
            start_processing(repository.id, force_reprocess=True, incremental=True)
        except RepositoryBusyError:
            # shortcut: this push isn't queued; the next push or the scheduled refresh picks it up
            busy.append(repository.id)
            continue
        started.append(repository.id)
    logger.info("GitHub push webhook", repository=path, branch=branch, started=started, busy=busy)
    return {"started": started, "busy": busy}
