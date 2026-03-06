"""
Ductan Kids - Full Auto Pipeline (with retry & error handling)
Fetch emails -> Extract images -> Build site -> Commit & Push
Called by weekly_fetch.bat via Task Scheduler (Wed + Fri 4 PM)
"""
import subprocess
import sys
import time
import shutil
import logging
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_DIR = SCRIPT_DIR / "logs"
BACKUP_DIR = SCRIPT_DIR / "backups"
LOG_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

PYTHON = sys.executable

# Setup logging to both file and console
log_path = LOG_DIR / "weekly_fetch.log"
err_path = LOG_DIR / "errors.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("pipeline")


def run_step(name, script, retries=3, delay=60, critical=True):
    """Run a Python script with retries. Returns True on success."""
    for attempt in range(1, retries + 1):
        log.info(f"[{name}] Attempt {attempt}/{retries}")
        try:
            result = subprocess.run(
                [PYTHON, script],
                cwd=str(SCRIPT_DIR),
                capture_output=True,
                text=True,
                timeout=300,
            )
            log.info(result.stdout.strip() if result.stdout.strip() else "(no output)")
            if result.stderr.strip():
                log.warning(f"stderr: {result.stderr.strip()}")
            if result.returncode == 0:
                log.info(f"[{name}] OK")
                return True
            else:
                log.error(f"[{name}] Exit code {result.returncode}")
        except subprocess.TimeoutExpired:
            log.error(f"[{name}] Timed out after 300s")
        except Exception as e:
            log.error(f"[{name}] Exception: {e}")

        if attempt < retries:
            log.info(f"[{name}] Retrying in {delay}s...")
            time.sleep(delay)

    level = "FAILED" if critical else "WARNING"
    msg = f"[{name}] {level} after {retries} attempts"
    log.error(msg)
    with open(err_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")
    return False


def git_commit_push(retries=3):
    """Stage changes, commit, and push with retry."""
    log.info("[Git] Staging changes...")
    subprocess.run(
        ["git", "add", "data/", "socds/socds_events.json", "docs/index.html"],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
    )

    # Check if there are staged changes
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
    )
    if result.returncode == 0:
        log.info("[Git] No new changes to push")
        return True

    # Commit
    date_str = datetime.now().strftime("%Y-%m-%d")
    commit_msg = f"Auto-update: {date_str}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error(f"[Git] Commit failed: {result.stderr}")
        return False
    log.info(f"[Git] Committed: {commit_msg}")

    # Push with retry
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            ["git", "push"],
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("[Git] Pushed to GitHub")
            return True
        log.error(f"[Git] Push attempt {attempt} failed: {result.stderr.strip()}")
        if attempt < retries:
            time.sleep(30)

    msg = "[Git] FAILED: push after 3 attempts (commit saved locally)"
    log.error(msg)
    with open(err_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} {msg}\n")
    return False


def backup_site():
    """Backup current built site before overwriting."""
    src = SCRIPT_DIR / "docs" / "index.html"
    if src.exists():
        date_str = datetime.now().strftime("%Y%m%d")
        dest = BACKUP_DIR / f"index_{date_str}.html"
        shutil.copy2(src, dest)
        log.info(f"[Backup] Saved {dest.name}")
        # Keep only last 10 backups
        backups = sorted(BACKUP_DIR.glob("index_*.html"), reverse=True)
        for old in backups[10:]:
            old.unlink()


def main():
    log.info("=" * 60)
    log.info("Starting Ductan Kids pipeline")
    log.info("=" * 60)

    # Step 1 & 2: Fetch emails (critical - retry 3x with 60s delay)
    run_step("Maya Fetch", "fetch_email.py", retries=3, delay=60, critical=True)
    run_step("Isaac Fetch", "fetch_socds.py", retries=3, delay=60, critical=True)

    # Step 3: Extract images (non-critical - 1 attempt)
    run_step("Extract Images", "extract_socds_images.py", retries=1, critical=False)

    # Step 4: Upload to Drive (non-critical - 2 attempts)
    run_step("Drive Upload", "upload_to_drive.py", retries=2, delay=30, critical=False)

    # Step 5: Backup current site
    backup_site()

    # Step 6: Build site (critical - retry 2x)
    build_ok = run_step("Build Site", "build_site.py", retries=2, delay=10, critical=True)

    if not build_ok:
        log.error("Build failed - skipping deploy")
        return

    # Step 7: Commit & push
    git_commit_push()

    log.info("Pipeline complete")
    log.info("")


if __name__ == "__main__":
    main()
