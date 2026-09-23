# Preview on the Unraid server (iglc.drevland.net)

A password-protected preview of the new site, for showing it to the IGLC before switch-over.
It runs as two containers (`iglc-web` and `iglc-db`) behind SWAG. Paper PDFs stay in Azure blob storage.
This is a preview, not the production home of iglc.net.

## 1. Copy the project to the server

Copy the project folder to `/mnt/user/appdata/iglc/src` (for example through the `appdata` share,
`\\<server>\appdata\iglc\src`). Leave out `.venv`, `db.sqlite3` and `inventory`.
Once the code is on GitHub, `git clone` there instead.

Put the database export in `/mnt/user/appdata/iglc/import/`:
`iglc_db-2026-9-23-18-7.bacpac`.

## 2. Settings

In `/mnt/user/appdata/iglc/src`, copy `.env.prod.example` to `.env.prod` and fill in:

- `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`: two different long random strings, for example from
  `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
- `PROXY_NETWORK`: the Docker network SWAG is on. Find it with `docker inspect swag --format '{{json .NetworkSettings.Networks}}'`.

## 3. Build and start

In the Unraid terminal (needs `docker compose`, for example from the Compose Manager plugin):

```sh
cd /mnt/user/appdata/iglc/src
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

The web container runs the database migrations each time it starts.

## 4. Load the data (first time only)

```sh
docker exec -it iglc-web python manage.py import_legacy /import/iglc_db-2026-9-23-18-7.bacpac
docker exec -it iglc-web python manage.py import_legacy_pages
docker exec -it iglc-web python manage.py createsuperuser
```

## 5. SWAG

1. Make sure `iglc` is covered by SWAG's certificate: add it to `SUBDOMAINS` in the SWAG container settings
   (not needed with a wildcard certificate), and point `iglc.drevland.net` at your home IP like the other subdomains.
2. Copy `deploy/unraid/iglc.subdomain.conf` to SWAG's `/config/nginx/proxy-confs/`.
3. Create the preview login (you are asked for a password):
   `docker exec -it swag htpasswd -c /config/nginx/.htpasswd-iglc iglc`
4. Restart SWAG.

Then open https://iglc.drevland.net and log in with `iglc` and the password. Give that login to whoever should see the preview.
The site admin is at `/manage/` and the CMS at `/cms/`, with the account from `createsuperuser`.

## Updating

Copy the new code over `src` (or `git pull`), then run the `up -d --build` command again.

## Backups

The database lives in `/mnt/user/appdata/iglc/postgres` and uploaded files in `/mnt/user/appdata/iglc/media`;
an appdata backup covers both. For a portable copy of the database:
`docker exec iglc-db pg_dump -U iglc iglc > iglc-backup.sql`.
