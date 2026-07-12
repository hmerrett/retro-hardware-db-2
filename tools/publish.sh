#!/usr/bin/env bash
#
# Build the public static site from the REST API and publish it to GitHub Pages.
#
# The API is LAN-only, so GitHub's CI can't build it -- the build runs here and
# the result is pushed into the old retro-hardware-database repo, whose Action
# deploys the committed site/ to the existing Pages URL. That keeps every QR
# label already in the wild resolving.
#
#   RHDB_API=http://192.168.1.2:8000 ./publish.sh
#   ./publish.sh "Add Amiga 1200"          # custom commit message
#
set -euo pipefail

cd "$(dirname "$0")"
HERE="$(pwd)"

# Where the Pages-hosting repo is checked out. Override with RHDB_SITE_REPO.
SITE_REPO="${RHDB_SITE_REPO:-$HERE/../../retro-hardware-database}"

# Python with the tool deps (the venv if present, else system python3).
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

if [ ! -d "$SITE_REPO/.git" ]; then
  echo "No git repo at $SITE_REPO -- set RHDB_SITE_REPO to the Pages repo." >&2
  exit 1
fi

echo "==> Building site from the API"
"$PY" build_site.py

echo "==> Syncing into $SITE_REPO/site"
rm -rf "$SITE_REPO/site"
cp -r site "$SITE_REPO/site"

echo "==> Committing + pushing the Pages repo"
cd "$SITE_REPO"
git add site
if git diff --cached --quiet; then
  echo "No site changes to publish."
else
  MSG="${*:-Publish site from API ($(date '+%Y-%m-%d %H:%M'))}"
  git commit -m "$MSG"
  git push
  echo "==> Pushed. GitHub Actions will deploy the site shortly."
fi
