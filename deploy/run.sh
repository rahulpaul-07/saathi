#!/bin/sh
# The commands used on the Azure VM (see docs/DEPLOY.md). Run them one at a time from the
# repository root; this is a record of the deployment, not an installer.
#
# Once only: the network create and the caddy run. Caddy keeps the certificate in the caddy-data
# volume and reads ~/Caddyfile, a copy of deploy/Caddyfile.
#
# Redeploying the app: git pull, docker build, docker rm -f saathi, then the saathi run line again.
# The models and the daily budget counter survive in the saathi-models and saathi-data volumes.
#
# ~/saathi.env holds the environment, one NAME=value per line. Names only, no values here:
#   GNANI_API_KEY               Gnani key
#   HF_TOKEN                    Hugging Face read token (the translation models are gated)
#   SAATHI_TRUSTED_PROXIES      the address of the caddy container on saathi-net
#   SAATHI_DAILY_GNANI_BUDGET   Gnani HTTP attempts per UTC day
#   SAATHI_PUBLIC_BASE_URL      the public origin, so the room QR code carries https
# Other names in .env.example are optional; the image already sets SAATHI_PUBLIC=1.
# ~/saathi-demo holds the demo clips and bundle, mounted read-only at /demo.

docker network create --subnet 172.30.0.0/24 saathi-net

docker build -t saathi:latest .

docker run -d --name saathi --restart unless-stopped --network saathi-net --env-file ~/saathi.env -v saathi-models:/models -v saathi-data:/data -v ~/saathi-demo:/demo:ro --memory 3500m saathi:latest

docker run -d --name caddy --restart unless-stopped --network saathi-net --ip 172.30.0.10 -p 80:80 -p 443:443 -v ~/Caddyfile:/etc/caddy/Caddyfile:ro -v caddy-data:/data -v caddy-config:/config caddy:2
