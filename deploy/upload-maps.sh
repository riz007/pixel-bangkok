#!/usr/bin/env bash
# Upload published maps (apps/web/public/maps) to a Cloudflare R2 bucket with rclone.
#
# Usage: deploy/upload-maps.sh <rclone-remote> <bucket> [area ...]
#   e.g. deploy/upload-maps.sh r2 pixel-bangkok-maps            # every published area
#        deploy/upload-maps.sh r2 pixel-bangkok-maps bangkok    # one area plus index.json
#
# The rclone remote is an S3 remote with provider Cloudflare and your R2 access keys
# (`rclone config`); this script never reads or stores credentials.
# Tile, overlay and thumbnail URLs carry a content version (?v=), so they are cached for a
# year; index.json, manifest.json and pois.json point at the current version and get 5 minutes.
set -euo pipefail

remote="${1:?rclone remote name}"
bucket="${2:?bucket name}"
shift 2
root="$(cd "$(dirname "$0")/.." && pwd)/apps/web/public/maps"
areas=("$@")
if [ ${#areas[@]} -eq 0 ]; then
  areas=($(cd "$root" && ls -d */ | tr -d /))
fi

long="Cache-Control: public, max-age=31536000, immutable"
short="Cache-Control: public, max-age=300"

for area in "${areas[@]}"; do
  echo "== $area"
  rclone sync "$root/$area" "$remote:$bucket/$area" \
    --exclude "manifest.json" --exclude "pois.json" \
    --header-upload "$long" --transfers 32 --checkers 32 --fast-list --progress
  rclone copy "$root/$area" "$remote:$bucket/$area" \
    --include "manifest.json" --include "pois.json" \
    --header-upload "$short" --header-upload "Content-Type: application/json"
done
rclone copyto "$root/index.json" "$remote:$bucket/index.json" \
  --header-upload "$short" --header-upload "Content-Type: application/json"
echo "== uploaded ${areas[*]}"
