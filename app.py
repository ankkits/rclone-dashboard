#!/usr/bin/env python3
import asyncio
import os
import sys
import shutil
import subprocess
import argparse
import tempfile
from datetime import datetime
from pathlib import Path

# --- Helpers ---


import os

HERE = Path(__file__).parent.resolve()
BIN_DIR = HERE / "bin"
RCLONE_PATH = str(BIN_DIR / "rclone")
RCLONE_CONFIG_PATH = os.environ.get("RCLONE_CONFIG_PATH", str(HERE / "rclone.conf"))
RCLONE_DEST = os.environ.get("RCLONE_DEST", "free_union:/telegram")
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", str(HERE / "downloads")))

# Telegram config
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # matches Render var TELEGRAM_TOKEN
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID")  # e.g. "-1001234567890"

# Rclone config
RCLONE_USER = os.environ.get("RCLONE_RC_USER", "admin")      # matches Render var RCLONE_RC_USER
RCLONE_PASS = os.environ.get("RCLONE_RC_PASS", "changeme")   # matches Render var RCLONE_RC_PASS

# Render port (Render assigns PORT automatically)
PORT = int(os.environ.get("PORT", "8080"))

def ensure_rclone_config_file():
    """Write RCLONE_CONFIG_CONTENT env to file if provided and file missing."""
    content = os.environ.get("RCLONE_CONFIG_CONTENT")
    if content and not Path(RCLONE_CONFIG_PATH).exists():
        Path(RCLONE_CONFIG_PATH).write_text(content, encoding="utf-8")
        print(f"[init] Wrote rclone config to {RCLONE_CONFIG_PATH}")
    else:
        if Path(RCLONE_CONFIG_PATH).exists():
            print(f"[init] Using existing rclone config at {RCLONE_CONFIG_PATH}")
        else:
            print("[warn] No rclone config found and RCLONE_CONFIG_CONTENT not set. Using template, uploads will fail until configured.")
            template = (HERE / "rclone.conf.template")
            if template.exists():
                shutil.copy(template, RCLONE_CONFIG_PATH)

def rclone_exists() -> bool:
    return Path(RCLONE_PATH).exists() and os.access(RCLONE_PATH, os.X_OK)

def require_rclone():
    if not rclone_exists():
        print("[fatal] rclone binary not found. Did the build step run scripts/setup.sh?")
        sys.exit(1)

def start_rclone_rcd():
    """Start rclone remote control with WebUI, bound to Render's $PORT."""
    require_rclone()
    ensure_rclone_config_file()

    cmd = [
        RCLONE_PATH, "rcd",
        "--rc-web-gui",
        "--rc-user", RCLONE_USER,
        "--rc-pass", RCLONE_PASS,
        "--rc-addr", f"0.0.0.0:{PORT}",
        "--config", RCLONE_CONFIG_PATH,
        "--use-mmap",
        "--log-level", os.environ.get("RCLONE_LOG_LEVEL", "INFO"),
        "--log-file", str(HERE / "rclone.log"),
    ]

    print("[rclone] starting rcd + WebUI:", " ".join(cmd))
    # Use Popen so we can run concurrently with other tasks (if needed in --mode all)
    return subprocess.Popen(cmd)

async def run_bot():
    """Start the Telegram bot that listens to files in a group and moves them to the union remote."""
    if not TELEGRAM_BOT_TOKEN:
        print("[fatal] TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    if not TELEGRAM_GROUP_ID:
        print("[fatal] TELEGRAM_GROUP_ID not set")
        sys.exit(1)

    # Lazy import to keep webui mode light
    from telegram import Update
    from telegram.constants import ChatType
    from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    require_rclone()
    ensure_rclone_config_file()

    def sanitize_filename(name: str) -> str:
        bad = '<>:"/\\|?*'
        for ch in bad:
            name = name.replace(ch, "_")
        return name.strip()

    async def save_and_upload(file_obj, filename_hint: str, subdir: str):
        # Build dated path to keep things tidy: YYYY/MM/DD
        today = datetime.utcnow()
        rel = Path(str(today.year)) / f"{today.month:02d}" / f"{today.day:02d}"
        local_dir = DOWNLOAD_DIR / rel
        local_dir.mkdir(parents=True, exist_ok=True)

        if not filename_hint:
            filename_hint = f"{file_obj.file_unique_id}.bin"
        filename = sanitize_filename(filename_hint)
        local_path = local_dir / filename

        # Download from Telegram
        tg_file = await file_obj.get_file()
        await tg_file.download_to_drive(str(local_path))
        print(f"[bot] downloaded to {local_path} ({local_path.stat().st_size} bytes)")

        # Build destination path within union remote
        dest = f"{RCLONE_DEST}/{subdir}/{rel.as_posix()}/"
        # Move the file via rclone
        cmd = [
            RCLONE_PATH, "move",
            str(local_path),
            dest,
            "--config", RCLONE_CONFIG_PATH,
            "--transfers", os.environ.get("RCLONE_TRANSFERS", "2"),
            "--checkers", os.environ.get("RCLONE_CHECKERS", "4"),
            "--retries", os.environ.get("RCLONE_RETRIES", "5"),
            "--low-level-retries", os.environ.get("RCLONE_LOW_LEVEL_RETRIES", "10"),
            "--tpslimit", os.environ.get("RCLONE_TPSLIMIT", "5"),
            "--stats", "10s",
            "--create-empty-src-dirs",
        ]
        print("[rclone] ", " ".join(cmd))
        res = subprocess.run(cmd, capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            # If move failed, keep the local file for troubleshooting
            return False
        return True

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat is None:
            return
        # Only accept from the configured group
        if str(update.effective_chat.id) != str(TELEGRAM_GROUP_ID):
            return

        msg = update.effective_message
        if not msg:
            return

        tasks = []

        # Documents (includes most file types)
        if msg.document:
            tasks.append(save_and_upload(msg.document, msg.document.file_name or "file.bin", "documents"))

        # Photos (largest size)
        if msg.photo:
            photo = msg.photo[-1]
            tasks.append(save_and_upload(photo, "photo.jpg", "photos"))

        # Videos
        if msg.video:
            tasks.append(save_and_upload(msg.video, msg.video.file_name or "video.mp4", "videos"))

        # Voice / audio
        if msg.voice:
            tasks.append(save_and_upload(msg.voice, "voice.ogg", "audio"))
        if msg.audio:
            tasks.append(save_and_upload(msg.audio, msg.audio.file_name or "audio", "audio"))

        # Animations (GIF as mp4)
        if msg.animation:
            tasks.append(save_and_upload(msg.animation, msg.animation.file_name or "animation.mp4", "animations"))

        # Stickers are skipped by default

        if tasks:
            await asyncio.gather(*tasks)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handler))

    print("[bot] starting...")
    await app.run_polling(close_loop=False)

async def run_all():
    # Launch rclone webui AND telegram bot in one process (useful for local dev)
    rclone_proc = start_rclone_rcd()
    try:
        await run_bot()
    finally:
        rclone_proc.terminate()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["webui", "bot", "all"], default="webui")
    args = parser.parse_args()

    if args.mode == "webui":
         proc = start_rclone_rcd()
         proc.communicate()
    elif args.mode == "bot":
        asyncio.run(run_bot())
    else:
        asyncio.run(run_all())

if __name__ == "__main__":
    main()
