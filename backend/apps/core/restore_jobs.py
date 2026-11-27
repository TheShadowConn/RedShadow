"""One restore at a time, handed from the web application to the maintenance service through the staging folder."""

import json
import logging
import shutil

from apps.audit import service as audit

from . import backup

log = logging.getLogger(__name__)
BUSY = ("queued", "running")


def _root():
    return backup.staging_dir() / "restore"


def status() -> dict:
    try:
        return json.loads((_root() / "status.json").read_text())
    except (OSError, ValueError):
        return {"state": "idle", "message": ""}


def set_status(state: str, message: str = "", **extra) -> None:
    _root().mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = _root() / "status.tmp"
    temporary.write_text(json.dumps({"state": state, "message": message, **extra}))
    temporary.replace(_root() / "status.json")


def queue(uploaded, passphrase: str, actor_label: str) -> None:
    """Check the file and passphrase now, so mistakes are reported at once, then leave it for the agent."""
    data = _root() / "data"
    shutil.rmtree(data, ignore_errors=True)
    data.mkdir(parents=True, mode=0o700)
    try:
        manifest = backup.unpack(uploaded, passphrase, data)
        backup.check_compatible(manifest)
    except Exception:
        shutil.rmtree(data, ignore_errors=True)
        raise
    set_status("queued", created_at=manifest.get("created_at"), requested_by=actor_label)


def run_pending() -> bool:
    """Maintenance service: carry out a queued restore. Returns whether there was one."""
    job = status()
    if job["state"] != "queued":
        return False
    data = _root() / "data"
    set_status("running")
    try:
        manifest = json.loads((data / "manifest.json").read_text())
        backup.load(data, manifest)
        audit.record(
            "system.restore_completed",
            actor_label=job.get("requested_by", ""),
            entity_type="system",
            entity_label="Restore",
            metadata={"backup_created_at": manifest.get("created_at"), "version": manifest.get("version")},
        )
        set_status("done", "Restore complete. Sign in with an account from the backup.")
    except backup.BackupError as exc:
        set_status("failed", str(exc))
    except Exception:  # noqa: BLE001 - the web page must learn that it failed
        log.exception("restore failed")
        set_status("failed", "The restore failed and nothing was changed. See the maintenance service log.")
    finally:
        shutil.rmtree(data, ignore_errors=True)
    return True
