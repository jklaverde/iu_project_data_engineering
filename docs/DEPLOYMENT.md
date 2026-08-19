# VPS Deployment Guide

This guide walks through deploying this project's existing `docker compose` stack (the
same one used for local development — see the root `README.md`) onto a single Linux
VPS, so it's reachable from the internet instead of just `localhost`. See
`docs/ARCHITECTURE.md` first if you want to understand what you're deploying before you
deploy it.

> **Scope note.** `REQUIREMENTS.md` §4.1 describes a larger production target — three
> VPS running k3s, with Kafka/Cassandra replicated across nodes. That is Phase 6 of the
> project roadmap and has not been built yet. This guide covers the deployment that
> *does* exist today: the same single-host Docker Compose stack, hardened enough to sit
> on a public VPS safely. It's a legitimate, complete way to run this project for real
> users — just not the eventual multi-node target.

## 1. Choose and size a VPS

Any provider that gives you a plain Linux VM with root/sudo access works (Contabo,
Hetzner, DigitalOcean, etc.). Size the machine off `REQUIREMENTS.md` NFR-3:

| Use case | vCPU | RAM | Disk |
|---|---|---|---|
| Demo / walkthrough only (default 100 msg/s) | 4 | 8 GB | 40 GB |
| Sustained 100 msg/s, running indefinitely | 4 | 16 GB | 100 GB+ (grows unboundedly — NFR-4, no data retention/TTL) |
| 48-hour endurance run at 500 msg/s (§10) | 8 | 16 GB+ | 100 GB minimum, monitor growth live |

Use Ubuntu 22.04 or 24.04 LTS (or any current Debian-family distro — the steps below
assume `apt`). Point a DNS A record at the VPS's IP now if you plan to do the TLS step
in §6; it can take a while to propagate.

## 2. Initial server hardening

SSH in as root (or your provider's default user) and do this **before** opening any
application ports:

```bash
# Create a non-root sudo user (skip if your provider already gave you one)
adduser deploy
usermod -aG sudo deploy

# Copy your SSH public key to the new user, then test logging in as it
# BEFORE closing your root session, e.g.:
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

# Disable password auth and root login over SSH
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

# Firewall: default-deny inbound, only allow SSH for now
sudo apt update && sudo apt install -y ufw fail2ban unattended-upgrades
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable

# Fail2ban on SSH (sane defaults are fine) and unattended security updates
sudo systemctl enable --now fail2ban
sudo dpkg-reconfigure -plow unattended-upgrades
```

This matches `REQUIREMENTS.md` NFR-11's baseline expectations (key-only SSH, default-deny
firewall, fail2ban, automatic security updates) even though this guide is a
single-host deployment, not the full multi-VPS hardening in that section.

## 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
# log out and back in for the group change to take effect
docker compose version   # confirm the Compose plugin is present
```

## 4. Get the project onto the VPS

```bash
git clone https://github.com/<your-fork-or-org>/iu_project_data_engineering.git
cd iu_project_data_engineering
```

The Kaggle dataset (~62 MB, public) is **not** committed and needs no manual fetch
step — the `dataset-init` service in `docker-compose.yml` downloads it automatically
into a named volume the first time you run `docker compose up -d` (§7). Nothing to
install on the VPS itself for this; it runs inside its own container.

## 5. Configure secrets

```bash
cp .env.example .env
```

Edit `.env` and set real values for every credential — do not ship the example
placeholders to a public VPS:

- `GRAFANA_ADMIN_PASSWORD`
- `BACKEND_ADMIN_USERNAME` / `BACKEND_ADMIN_PASSWORD`
- `BACKEND_SESSION_SECRET` — generate with `openssl rand -hex 32`

If you're putting the app behind TLS (§6, recommended for any public-facing use), also
set `BACKEND_COOKIE_SECURE=true` — otherwise the session cookie won't get the `Secure`
flag and the login can be sent in cleartext.

All other `.env` values (rates, ports, watermarks) can stay at their defaults for a
first deployment. `KAGGLE_USERNAME`/`KAGGLE_KEY` can stay empty — the dataset is
public and `dataset-init` only needs them if Kaggle ever starts requiring auth for it.

## 6. Firewall: decide what's actually public

Everything in `docker-compose.yml` publishes a host port by default (that's what makes
local development convenient), but **not everything should be reachable from the
internet on a real VPS**. Following the same principle `REQUIREMENTS.md` NFR-11 uses
for the production k3s target ("only ingress ports open, everything else
cluster-internal"):

| Should be public | Port | Why |
|---|---|---|
| Web app (guided walkthrough) | 8000 (or your TLS reverse-proxy port, §6b) | This is the actual product |
| Grafana | 3000 (or via reverse proxy) | KPI dashboards for end users |

| Should stay internal-only | Port(s) |
|---|---|
| Kafka | 9092 |
| Cassandra | 9042, 7070 (JMX exporter) |
| Spark master/worker UI, driver UI | 7077, 8090, 8091, 4040 |
| Producer / Spark job `/state` | 8001, 8002 |
| Prometheus | 9090 |
| kafka-exporter, node-exporter | 9308, 9100 |
| kafka-ui (dev convenience only) | 8080 |

Do this with the host firewall — `ufw` — rather than editing every port mapping in
`docker-compose.yml` out of caution (Docker's own iptables rules can otherwise bypass
`ufw`; the explicit rules below close that gap):

```bash
# Only open what's actually meant to be public.
sudo ufw allow 8000/tcp    # web app (or skip this and only allow 443 - see §6b)
sudo ufw allow 3000/tcp    # Grafana (or skip this too if proxying both - see §6b)
sudo ufw reload
sudo ufw status verbose    # confirm nothing else is open
```

If you don't need `kafka-ui` in production, comment out its service in
`docker-compose.yml` entirely rather than just leaving its port firewalled — one less
container running as root-adjacent debug tooling on a public box.

### 6b. Recommended: put a TLS reverse proxy in front (optional, but do this for real use)

Plain HTTP means the login form for the web app and Grafana sends credentials in
cleartext over the public internet. `REQUIREMENTS.md`'s Phase-1 NFR-6 doesn't strictly
require TLS for the local-development stack, but for anything actually facing real
users on a public VPS, terminate TLS. [Caddy](https://caddyserver.com) is the lowest-effort
option — automatic Let's Encrypt certificates, one file, no manual renewal:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```caddyfile
app.your-domain.com {
    reverse_proxy localhost:8000
}

grafana.your-domain.com {
    reverse_proxy localhost:3000
}
```

```bash
sudo systemctl reload caddy
```

Then update the firewall to only expose Caddy, not the raw app ports:

```bash
sudo ufw delete allow 8000/tcp
sudo ufw delete allow 3000/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

Set `BACKEND_COOKIE_SECURE=true` in `.env` and restart the `backend` service (§8) once
this is in place.

## 7. Start the stack

```bash
docker compose up -d --build
```

First start builds the custom images (`producer`, `spark_job`/`spark-worker`,
`cassandra`, `grafana`, `backend`) and pre-warms Spark's dependency cache — expect this
to take several minutes. Watch it come up:

```bash
docker compose ps
```

Every long-running service should reach `healthy`; the `*-init`/`*-schema-init`
one-shot containers should show `Exited (0)` — that's success, not a crash (see
`docs/TROUBLESHOOTING.md` if anything looks different). Cold start details (baseline
recomputation, catching up on a backlog) are in `docs/PROGRESS.md`'s "Resuming
locally" section — the same behavior applies on first VPS start.

Then open (through your firewall/proxy from §6):
- `https://app.your-domain.com` (or `http://<vps-ip>:8000`) — log in with
  `BACKEND_ADMIN_USERNAME`/`PASSWORD` from `.env`.
- `https://grafana.your-domain.com` (or `http://<vps-ip>:3000`) — log in with
  `GRAFANA_ADMIN_USER`/`GRAFANA_ADMIN_PASSWORD`.

## 8. Make sure it survives a reboot

Every long-running service in `docker-compose.yml` is set to `restart: unless-stopped`,
so as long as the Docker daemon itself starts on boot, the whole stack comes back after
an unattended VPS reboot (provider maintenance, kernel update, etc.) with no manual
step — the `get.docker.com` installer already enables the `docker` systemd service by
default; confirm with:

```bash
systemctl is-enabled docker   # should print "enabled"
```

This satisfies `REQUIREMENTS.md` NFR-8 (recoverability) unattended, which is stronger
than the local-dev expectation of manually re-running `docker compose up -d`.

## 9. Backups

All stateful data lives in named Docker volumes: `kafka_data`, `cassandra_data`,
`prometheus_data`, `grafana_data`, `spark_checkpoints`, `kaggle_dataset`. Back up the
ones worth backing up with the volume stopped (or accept a slightly-inconsistent live
snapshot for a lower-stakes demo deployment):

```bash
docker compose stop
sudo tar czf backup-$(date +%F).tar.gz \
  -C /var/lib/docker/volumes \
  iu-sensor-pipeline_cassandra_data \
  iu-sensor-pipeline_grafana_data \
  iu-sensor-pipeline_prometheus_data
docker compose start
```

(Kafka's `kafka_data` and `spark_checkpoints` are consumer/checkpoint state, and
`kaggle_dataset` is a public dataset `dataset-init` re-fetches automatically if it's
ever missing — none of those three are worth backing up. Cassandra's data is the
actual sensor history and is worth backing up for real.) Copy the archive off
the VPS (`scp`/`rsync` to another machine, or your provider's snapshot feature on the
whole disk) — a backup that only lives on the box it's protecting against isn't a
backup.

## 10. Updating

```bash
cd iu_project_data_engineering
git pull
docker compose up -d --build
```

Compose only recreates containers whose image or config actually changed — this is
safe to run repeatedly. If a `pip-compile`d `requirements.txt` changed, `--require-hashes`
still applies automatically at build time (see `docs/ARCHITECTURE.md`'s supply-chain
section).

## 11. Monitoring, logs, and troubleshooting

```bash
docker compose ps                    # health at a glance
docker compose logs -f backend       # tail one service
docker compose logs --since 1h       # everything, last hour
```

Grafana's dashboards (KPI-1 through KPI-5) are the primary operational view once
running — see `REQUIREMENTS.md` §9. For anything that looks wrong at the
infrastructure level (a container crash-looping, an unexpected timing issue), check
`docs/TROUBLESHOOTING.md` first — most non-obvious issues hit during local development
apply identically on a VPS.

## 12. Tearing down

```bash
docker compose down        # stop everything, keep data (volumes survive)
docker compose down -v     # stop everything AND delete all data - irreversible
```
