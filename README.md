# Telegram → Rclone Union (Render Free)

This repo deploys **two free services on Render**:

1. **rclone WebUI (web service)** – browse a single virtual drive that **unifies many free cloud accounts** (Google Drive, Dropbox, OneDrive, Box, pCloud, Koofr, Icedrive, Proton Drive, …). Auth via `RCLONE_USER` / `RCLONE_PASS`.
2. **Telegram Bot (worker)** – listens to a private group and **uploads every new file** straight into your **rclone union** remote.

No Docker needed. Rclone is downloaded automatically at build time.

---

## 0) Make (or reuse) free cloud accounts

Create accounts for the services you want to combine. Some popular options:

- **Google** (for Google Drive)  
- **Microsoft** (for OneDrive)  
- **Dropbox**  
- **Box** (Personal)  
- **pCloud**  
- **Icedrive**  
- **Koofr**  
- **Proton** (Proton Mail account gives access to **Proton Drive**)  
- **MEGA** (optional)

> You can add **multiple accounts of the same provider** (e.g., `gdrive1`, `gdrive2`, …) in one `rclone.conf`.

See “Provider signup links” below.

---

## 1) Create a Telegram Bot & get your Group ID

1. In Telegram, talk to **@BotFather** → ` /newbot ` → name your bot and copy the **token**.  
2. Create a **private group**, add your bot, and make it **admin** (so it can see all messages).  
3. Get the **chat ID** (a negative number). Easiest: add **@RawDataBot** to the group temporarily and read the `chat.id`, or run this repo locally once and check logs.

---

## 2) Configure rclone on your laptop (one-time)

Install rclone: https://rclone.org/install/  
Then, for each provider you want:

```bash
rclone config
# n (new remote) → name like gdrive1 / dropbox1 / onedrive1 / box1 / pcloud1 / koofr1 / proton1 / icedrive1 (webdav)
# pick the right "type" and follow the OAuth/login prompts (headless flows are supported)
```

Tips:
- **Google Drive:** creating your **own OAuth client** avoids shared API limits. See rclone’s Drive docs.  
- **Icedrive:** enable **WebDAV** in your account and use those credentials (user/pass).  
- **Proton Drive:** requires a recent rclone with the **protondrive** backend.

Now create the **union** remote that merges them all:

```bash
# In rclone config, add a new remote "free_union" of type "union"
# Set "upstreams" to the remotes you created, e.g.:
# gdrive1: dropbox1: onedrive1: box1: pcloud1: koofr1: icedrive1:
# Policies:
#   create_policy = mfs  (send new files to the remote with the most free space)
#   action_policy  = epff (modify the first remote where the path exists)
#   search_policy  = ff   (read from all; fastest-first)
```

Finally, **open** your `~/.config/rclone/rclone.conf` and **copy everything** into a safe place.

---

## 3) Deploy to Render (Free)

1. **Fork** this repo to your GitHub.  
2. On **Render → New + → Blueprint**, choose your fork. Render detects `render.yaml` and creates:  
   - **Web Service**: `rclone-webui` (serves the Web UI on a public URL)  
   - **Background Worker**: `telegram-bot-worker` (listens for files)  
3. Set environment variables (Render → each service → Environment):  
   - `RCLONE_CONFIG_CONTENT` → **paste your whole `rclone.conf`** content  
   - `RCLONE_USER` / `RCLONE_PASS` → WebUI login (web service only)  
   - `TELEGRAM_BOT_TOKEN` / `TELEGRAM_GROUP_ID` → (worker only)  
   - (Optional) `RCLONE_DEST` → default `free_union:/telegram`
4. Deploy. The Web UI will appear at your service URL. Log in with `RCLONE_USER` / `RCLONE_PASS`.

> Free plan note: the bot runs as a **worker**, which doesn’t sleep for inactivity like web services might. Keep both services on the free plan.

---

## 4) How it works

- The **worker** polls Telegram. When a file arrives, it downloads to a temp folder, then runs:
  ```bash
  rclone move /app/downloads/YYYY/MM/DD/filename  free_union:/telegram/…
  ```
  Rclone’s **union** backend spreads uploads across the remotes according to your policy (`create_policy = mfs`).  
- The **web service** runs `rclone rcd --rc-web-gui --rc-addr 0.0.0.0:$PORT` with basic auth, letting you **browse all files** online as a single drive.

---

## Provider signup links (official)

```
Google Account:        https://accounts.google.com/
OneDrive (free):       https://www.microsoft.com/en-us/microsoft-365/onedrive/free-online-cloud-storage
Dropbox Basic:         https://www.dropbox.com/basic
Box Personal:          https://account.box.com/signup/personal
pCloud:                https://www.pcloud.com/
Icedrive:              https://icedrive.net/
Koofr:                 https://koofr.eu/
Proton (for Drive):    https://account.proton.me/login  (Create account → access Proton Drive)
MEGA:                  https://mega.nz/register
```
(You can use any combination of these in your union.)

---

## Maximizing free space (and sanity)

- Add **multiple accounts** of the same provider: e.g., `gdrive1`, `gdrive2`, … each is a separate remote in `rclone.conf`.
- Use `create_policy = mfs` on the union so new files go to the remote with **most free space**.
- Keep an eye on provider **bandwidth / API limits**; if Google Drive throttles, set envs:
  ```
  RCLONE_TPSLIMIT=3
  RCLONE_TRANSFERS=2
  RCLONE_CHECKERS=4
  ```
- For Google Drive, set your **own** `client_id`/`client_secret` in the remote to avoid shared limits.
- Periodically run `rclone about <remote>:` to check free space.

---

## Security & backups

- Treat `RCLONE_CONFIG_CONTENT` like a **password**. Keep your repo private or store the config only in Render **Environment**.
- Enable **2FA** on your cloud accounts.
- Consider creating a **read-only** account for browsing in the WebUI (use a separate union with `:ro` or mount flags if needed).

---

## Local development

```
# Create a virtualenv, install deps
pip install -r requirements.txt

# Put your rclone.conf next to app.py or set RCLONE_CONFIG_PATH
cp ~/.config/rclone/rclone.conf ./rclone.conf

# Download rclone locally (optional; or install system-wide)
bash scripts/setup.sh

# Start both (WebUI + bot)
python app.py --mode all
```

---

## FAQ

**Can I add more Google Drive accounts in one `rclone.conf`?**  
Yes. Create multiple remotes (`gdrive1`, `gdrive2`, …) – each with its own OAuth token. Add them all to the union’s `upstreams`.

**Do I need Docker on Render?**  
No. This repo uses the Python runtime and a small build script to fetch the rclone binary.

**Where’s my data stored?**  
In your own cloud accounts. Render only hosts the bot & Web UI; its disk is ephemeral.
