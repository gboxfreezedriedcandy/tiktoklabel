# TikTok Shop Automation — v5.4
Login → Filter Orders → Select All → Arrange → (Combine orders modal) → Edit Weight → Print

**Use Python 3.8+**

## Setup
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # Fill TT_USERNAME / TT_PASSWORD
python main.py --weight 0.65
```
> The app falls back to `/tmp/tiktok_artifacts` if `/var/task/artifacts` is read-only; setting `TT_ARTIFACTS_DIR` keeps the location predictable across environments.

### Env examples
```env
TT_USERNAME=your_email@example.com
TT_PASSWORD=your_password
TT_HEADLESS=0
TT_LOGIN_URL=https://seller-us.tiktok.com/account/login
TT_SELLER_ORIGIN=https://seller-us.tiktok.com
# Optional Chrome profile (helps keep login sessions)
# TT_USER_DATA_DIR=/path/to/Chrome/User Data
# TT_PROFILE_DIR=Profile 1
```

Artifacts (screenshots, cookies) go to `artifacts/`.

### What’s new in v5.4
- Loads `.env` automatically (via `python-dotenv`).
- Keeps all robustness fixes for navigation, combine-orders modal, and clearing the weight input before typing.

## Docker
Build the image (installs Python, Chromium, and dependencies):
```bash
docker build -t tiktok-shop .
```

Run the automation once, reusing the existing `.env` values, mounting `artifacts/` and `downloads/` so PDFs and credentials persist:
```bash
docker run --rm \
  --env-file .env \
  -e TT_HEADLESS=1 \
  -e CHROME_BINARY=/usr/bin/chromium \
  -e CHROMEDRIVER_BINARY=/usr/bin/chromedriver \
  -v "$(pwd)/artifacts:/app/artifacts" \
  -v "$(pwd)/downloads:/app/downloads" \
  tiktok-shop --weight 0.65
```
> Update any absolute paths in `.env` (e.g., `GD_OAUTH_CLIENT_SECRETS`, `GD_TOKEN_PATH`) so they point inside the container, such as `/app/artifacts/...`.

`CHROME_BINARY` points Selenium at the Chromium binary shipped in the image, and `CHROMEDRIVER_BINARY` reuses the matching driver from the OS package. If you package a different browser build, adjust these paths (and optionally set `CHROMEDRIVER_VERSION` to reuse a cached driver when offline).

To watch the browser session, disable headless mode and expose the built-in VNC server (no password by default):
```bash
docker run --rm \
  --env-file .env \
  -e TT_HEADLESS=1 \
  -e VNC_PORT=5900 \
  -e CHROME_BINARY=/usr/bin/chromium \
  -e CHROMEDRIVER_BINARY=/usr/bin/chromedriver \
  -p 5900:5900 \
  -v "$(pwd)/artifacts:/app/artifacts" \
  -v "$(pwd)/downloads:/app/downloads" \
  tiktok-shop --product G-BOX-FD-STRAWBERRY-SHORTCAKE-M --weight 0.25
```
To watch the browser session, disable headless mode and expose the built-in VNC server (no password by default):
```bash
docker run --rm \
  --env-file .env \
  -e TT_HEADLESS=1 \
  -e VNC_PORT=5900 \
  -e CHROME_BINARY=/usr/bin/chromium \
  -e CHROMEDRIVER_BINARY=/usr/bin/chromedriver \
  -p 5900:5900 \
  -v "$(pwd)/artifacts:/app/artifacts" \
  -v "$(pwd)/downloads:/app/downloads" \
  tiktok-shop --product G-BOX-FD-STRAWBERRY-SHORTCAKE-L --weight 0.5
```
To watch the browser session, disable headless mode and expose the built-in VNC server (no password by default):
```bash
docker run --rm \
  --env-file .env \
  -e TT_HEADLESS=1 \
  -e VNC_PORT=5900 \
  -e CHROME_BINARY=/usr/bin/chromium \
  -e CHROMEDRIVER_BINARY=/usr/bin/chromedriver \
  -p 5900:5900 \
  -v "$(pwd)/artifacts:/app/artifacts" \
  -v "$(pwd)/downloads:/app/downloads" \
  tiktok-shop --product G-BOX-FD-ICE-CREAM-CUBES-VANILLA-M --weight 0.25
```
To watch the browser session, disable headless mode and expose the built-in VNC server (no password by default):
```bash
docker run --rm \
  --env-file .env \
  -e TT_HEADLESS=1 \
  -e VNC_PORT=5900 \
  -e CHROME_BINARY=/usr/bin/chromium \
  -e CHROMEDRIVER_BINARY=/usr/bin/chromedriver \
  -p 5900:5900 \
  -v "$(pwd)/artifacts:/app/artifacts" \
  -v "$(pwd)/downloads:/app/downloads" \
  tiktok-shop --product G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L --weight 0.5
```
Connect with a VNC viewer to `vnc://localhost:5900` to observe the Chromium window. Adjust `VNC_PORT`, resolution (`XVFB_W`/`XVFB_H`) or add `x11vnc` flags as needed for your setup.

Alternatively, start the service with Docker Compose (uses the included `docker-compose.yml`):
```bash
docker compose up --build
```
Override the automation arguments by appending them to the command, e.g. `docker compose run --rm tiktok-shop --weight 0.75`.

### AWS Lambda container image
Build the Lambda-friendly image (uses the official Lambda Python runtime and bundles headless Chromium) with the alternate Dockerfile:
```bash
docker build -f Dockerfile.lambda -t tiktok-shop-lambda .
```

Run it locally by supplying the handler and event payload. The Lambda base image expects the handler name first:
```bash
docker run --rm \
  --env-file .env \
  -e TT_ARTIFACTS_DIR=/tmp/tiktok_artifacts \
  -e TT_TMP_DIR=/tmp \
  -v "$(pwd)/artifacts:/var/task/artifacts" \
  -v "$(pwd)/downloads:/var/task/downloads" \
  tiktok-shop-lambda \
  main.lambda_handler \
  '{"weight":0.5,"product":"G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L"}'
```

To emulate the Lambda runtime API instead, expose port 9000 and POST the event:
```bash
docker run --rm -p 9000:8080 --env-file .env tiktok-shop-lambda
curl -s -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"weight":0.5,"product":"G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L"}'
```

Deploy to AWS by pushing the image to ECR and creating a Lambda function with handler `main.lambda_handler`. The `.env` values translate to Lambda environment variables (set them on the function) so credentials and toggles carry over.

```bash
docker run --rm tiktok-shop-lambda
curl -s -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"weight":0.5,"product":"G-BOX-FD-ICE-CREAM-CUBES-VANILLA-L"}'
```