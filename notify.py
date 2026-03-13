"""
Telegram notifications for the Ductan Kids pipeline.
Uses the same bot/chat as SwingLowPro Trader.
"""
import os
import urllib.request
import urllib.parse
import json


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send(message, silent=False):
    """Send a Telegram message. Returns True on success."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[Telegram] No credentials configured, skipping notification")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_notification": str(silent).lower(),
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"[Telegram] Send failed: {e}")
        return False


def pipeline_success(maya_result, isaac_result, pushed):
    """Send a success summary."""
    parts = ["🏫 <b>Ductan Kids — Pipeline OK</b>"]
    if maya_result:
        parts.append(f"📄 Maya: {maya_result}")
    else:
        parts.append("📄 Maya: no new email")
    if isaac_result:
        parts.append(f"📝 Isaac: {isaac_result}")
    else:
        parts.append("📝 Isaac: no new email")
    if pushed:
        parts.append("✅ Site updated & pushed to GitHub")
    else:
        parts.append("ℹ️ No new changes to push")
    send("\n".join(parts), silent=True)


def pipeline_failure(step, error):
    """Send a failure alert (not silent — want notification)."""
    send(
        f"🚨 <b>Ductan Kids — Pipeline FAILED</b>\n"
        f"Step: <code>{step}</code>\n"
        f"Error: {error}"
    )
