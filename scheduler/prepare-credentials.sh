#!/usr/bin/env bash
set -euo pipefail

private_dir="$(cd "$(dirname "$0")/.." && pwd)/.private"
umask 077
mkdir -p "$private_dir"

for entry in 'Cloudflare API token:cloudflare_api_token' 'GitHub Actions token:github_dispatch_token'; do
  label="${entry%%:*}"
  filename="${entry#*:}"
  read -r -s -p "$label " token
  printf '\n'
  if [[ -z "$token" ]]; then
    printf 'No token entered; stopping.\n' >&2
    exit 1
  fi
  printf '%s' "$token" > "$private_dir/$filename"
  unset token
done

printf 'Deployment tokens saved in .private/ with private file permissions.\n'
