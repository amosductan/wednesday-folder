"""
Ductan Kids - Full Auto Pipeline (with retry, error handling & alerts)
Fetch emails -> Process PDFs -> Auto-curate events -> Extract images ->
Build site -> Commit & Push -> Telegram notification

Called by weekly_fetch.bat via Task Scheduler (Wed + Fri 4 PM)
"""
import subprocess
import sys
import time
import shutil
import json
import logging
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_DIR = SCRIPT_DIR / "logs"
BACKUP_DIR = SCRIPT_DIR / "backups"
PDF_DIR = SCRIPT_DIR / "pdfs"
DATA_DIR = SCRIPT_DIR / "data"
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

# Track pipeline results for notification
pipeline_results = {
    "maya": None,
    "isaac": None,
    "pushed": False,
    "errors": [],
}


def run_step(name, cmd, retries=3, delay=60, critical=True):
    """Run a command with retries. Returns (success, stdout)."""
    for attempt in range(1, retries + 1):
        log.info(f"[{name}] Attempt {attempt}/{retries}")
        try:
            if isinstance(cmd, str):
                cmd_list = [PYTHON, cmd]
            else:
                cmd_list = cmd

            result = subprocess.run(
                cmd_list,
                cwd=str(SCRIPT_DIR),
                capture_output=True,
                text=True,
                timeout=300,
            )
            stdout = result.stdout.strip() if result.stdout else ""
            if stdout:
                log.info(stdout)
            if result.stderr.strip():
                log.warning(f"stderr: {result.stderr.strip()}")
            if result.returncode == 0:
                log.info(f"[{name}] OK")
                return True, stdout
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
    if critical:
        pipeline_results["errors"].append(f"{name}: failed after {retries} attempts")
    return False, ""


def find_unprocessed_pdfs():
    """Find PDFs in pdfs/ that don't have a corresponding data/YYYY-MM-DD.json."""
    unprocessed = []
    for pdf in sorted(PDF_DIR.glob("*_wednesday_folder.pdf")):
        # Extract date from filename
        date_str = pdf.name.split("_wednesday_folder")[0]
        data_file = DATA_DIR / f"{date_str}.json"
        if not data_file.exists():
            unprocessed.append((date_str, str(pdf)))
    return unprocessed


def process_pdfs():
    """Process any unprocessed PDFs and auto-curate events."""
    unprocessed = find_unprocessed_pdfs()
    if not unprocessed:
        log.info("[PDF Process] No unprocessed PDFs")
        return False

    any_processed = False
    for date_str, pdf_path in unprocessed:
        log.info(f"[PDF Process] Processing {date_str}")
        ok, stdout = run_step(
            f"PDF Extract ({date_str})",
            [PYTHON, "process_pdf.py", pdf_path, "--date", date_str],
            retries=1,
            critical=False,
        )
        if ok:
            any_processed = True
            pipeline_results["maya"] = f"New PDF processed: {date_str}"

    if any_processed:
        # Auto-curate all unprocessed dates into events.json
        ok, stdout = run_step(
            "Auto Curate",
            "auto_curate.py",
            retries=1,
            critical=False,
        )
        if ok:
            log.info("[Auto Curate] Events auto-generated from PDF text")

    return any_processed


def git_commit_push(retries=3):
    """Stage changes, commit, and push with retry."""
    log.info("[Git] Staging changes...")
    subprocess.run(
        ["git", "add",
         "data/",
         "socds/socds_events.json",
         "socds/data/",
         "docs/index.html"],
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
        pipeline_results["errors"].append(f"Git commit failed: {result.stderr[:100]}")
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
            pipeline_results["pushed"] = True
            return True
        log.error(f"[Git] Push attempt {attempt} failed: {result.stderr.strip()}")
        if attempt < retries:
            time.sleep(30)

    msg = "[Git] FAILED: push after 3 attempts (commit saved locally)"
    log.error(msg)
    pipeline_results["errors"].append("Git push failed after 3 attempts")
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


def send_notification():
    """Send Telegram notification with pipeline results."""
    try:
        import notify

        if pipeline_results["errors"]:
            for err in pipeline_results["errors"]:
                notify.pipeline_failure("Pipeline", err)
        else:
            notify.pipeline_success(
                pipeline_results["maya"],
                pipeline_results["isaac"],
                pipeline_results["pushed"],
            )
    except Exception as e:
        log.warning(f"[Telegram] Notification failed: {e}")


def main():
    log.info("=" * 60)
    log.info("Starting Ductan Kids pipeline")
    log.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 60)

    # Step 1: Fetch Maya email + download PDF (critical - retry 3x)
    maya_ok, maya_out = run_step(
        "Maya Fetch", "fetch_email.py", retries=3, delay=60, critical=True
    )
    if maya_ok and "Saved PDF" in maya_out:
        pipeline_results["maya"] = "New email fetched"

    # Step 2: Fetch Isaac email (critical - retry 3x)
    isaac_ok, isaac_out = run_step(
        "Isaac Fetch", "fetch_socds.py", retries=3, delay=60, critical=True
    )
    if isaac_ok and "downloaded" in isaac_out.lower():
        pipeline_results["isaac"] = "New newsletter fetched"

    # Step 3: Process any unprocessed Maya PDFs → raw text → auto-curate events
    process_pdfs()

    # Step 4: Extract SOCDS images (non-critical - 1 attempt)
    run_step("Extract Images", "extract_socds_images.py", retries=1, critical=False)

    # Step 5: Upload to Drive (non-critical - 2 attempts)
    run_step("Drive Upload", "upload_to_drive.py", retries=2, delay=30, critical=False)

    # Step 6: Backup current site
    backup_site()

    # Step 7: Build site (critical - retry 2x)
    build_ok, _ = run_step(
        "Build Site", "build_site.py", retries=2, delay=10, critical=True
    )

    if not build_ok:
        log.error("Build failed - skipping deploy")
        pipeline_results["errors"].append("Site build failed")
    else:
        # Step 8: Commit & push
        git_commit_push()

    # Step 9: Send Telegram notification
    send_notification()

    log.info("Pipeline complete")
    log.info("")


if __name__ == "__main__":
    main()
