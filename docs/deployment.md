# Deployment Guide

This document covers staging and production deployment of the Web Scraper application.

## Prerequisites

- SSH access to `saltrun-staging` or `saltrun-production`
- Docker and Docker Compose on the target host
- Caddy reverse proxy running (via `caddy-local` on nexus)
- Authentik instance at `auth.saltrun.net` (for SSO)

---

## Staging Deployment

**URL:** `https://web-scraper.staging.saltrun.net`

### 1. Scaffold check

```bash
ssh saltrun-staging "test -d /opt/web-scraper && echo exists || echo not-found"
```

If not found, create the project scaffold:

```bash
~/homelab/scripts/new-staging-project.sh web-scraper --port 8000 --minio
```

### 2. Set up environment

```bash
ssh saltrun-staging "cp /opt/web-scraper/.env.example /opt/web-scraper/.env"
```

Edit `/opt/web-scraper/.env` on staging and fill in all required secrets:

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@db:5432/web_scraper` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `SECRET_KEY` | Long random string (session signing) |
| `API_TOKEN_SECRET` | Long random string (API token HMAC key) |
| `OPERATOR_EMAIL` | Seed operator email |
| `OPERATOR_PASSWORD` | Seed operator password |
| `AUTHENTIK_CLIENT_ID` | From Authentik OAuth2 provider |
| `AUTHENTIK_CLIENT_SECRET` | From Authentik OAuth2 provider |
| `AUTHENTIK_BASE_URL` | `https://auth.saltrun.net` |
| `AUTHENTIK_APP_SLUG` | `web-scraper` |
| `S3_BUCKET_NAME` | MinIO bucket name |
| `S3_ACCESS_KEY_ID` | MinIO access key |
| `S3_SECRET_ACCESS_KEY` | MinIO secret key |
| `S3_ENDPOINT_URL` | MinIO endpoint URL |

Set `ENVIRONMENT=staging` in `.env`.

### 3. Set up app config

```bash
ssh saltrun-staging "cp /opt/web-scraper/config/app.yml.example /opt/web-scraper/config/app.yml"
```

Edit `config/app.yml` and set `features.sso_enabled: true` to enable the Authentik SSO button.

### 4. Deploy

```bash
ssh saltrun-staging "cd /opt/web-scraper && git pull && docker compose -f docker-compose.yml -f docker-compose.staging.yml pull && docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d"
```

### 5. Run migrations

```bash
ssh saltrun-staging "cd /opt/web-scraper && docker compose exec app alembic upgrade head"
```

### 6. Register Authentik OIDC client (one-time, manual)

In the Authentik admin UI at `https://auth.saltrun.net`:

1. **Create OAuth2/OpenID Provider:**
   - Name: `web-scraper-staging`
   - Authorization flow: `default-authorization-flow`
   - Client type: Confidential
   - Generate Client ID and Client Secret → copy both to staging `.env`
   - Redirect URIs: `https://web-scraper.staging.saltrun.net/auth/oidc/callback`
   - Signing Key: select your default key pair

2. **Create Application:**
   - Name: `web-scraper`
   - Slug: `web-scraper`
   - Provider: `web-scraper-staging`

3. After saving, restart the app container to reload the OIDC discovery document:
   ```bash
   ssh saltrun-staging "cd /opt/web-scraper && docker compose restart app"
   ```

### 7. Smoke test

```bash
# Health check
curl -s https://web-scraper.staging.saltrun.net/health

# Expected: {"status":"ok","db":"ok","redis":"ok"}
```

Then manually verify:
- [ ] Login with local operator credentials
- [ ] Login via SSO (Authentik → callback → `/`)
- [ ] Start a fixture connector job; confirm event log updates
- [ ] Export records as CSV; confirm download

---

## Production Deployment

**URL:** `https://web-scraper.saltrun.net` (not yet live)

Production follows the same steps as staging with these differences:

- Use `docker-compose.prod.yml` overlay instead of `docker-compose.staging.yml`
- Set `ENVIRONMENT=production` in `.env`
- Use a separate Authentik provider: `web-scraper-production`
- Redirect URI: `https://web-scraper.saltrun.net/auth/oidc/callback`
- Session cookies are `Secure=true` when `ENVIRONMENT=production`

```bash
ssh saltrun-production "cd /opt/web-scraper && git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
ssh saltrun-production "cd /opt/web-scraper && docker compose exec app alembic upgrade head"
```

---

## Rollback

To roll back to the previous image:

```bash
# On the target host
cd /opt/web-scraper
git log --oneline -5          # find the previous commit
git checkout <commit-hash>    # or use a tag
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
docker compose exec app alembic downgrade -1
```

Database rollbacks should be tested in staging before applying to production.

---

## Useful commands

```bash
# View app logs
docker compose logs -f app

# Check container status
docker compose ps

# Open a Python shell in the app container
docker compose exec app python -c "import app; print('ok')"

# Manually trigger a migration check
docker compose exec app alembic current
```
