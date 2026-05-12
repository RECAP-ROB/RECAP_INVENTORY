# PostgreSQL Local Development Setup Guide

This guide walks you through setting up PostgreSQL for local development of the RECAP Inventory system.

## Quick Start (macOS / Ubuntu)

### 1. Install PostgreSQL locally (alternative to Docker)

**macOS (Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install postgresql-15 postgresql-contrib-15
sudo systemctl start postgresql
```

### 2. Create the recap database and user

```bash
# Connect to PostgreSQL as the default postgres user
sudo -u postgres psql

# Inside the psql prompt:
postgres=# CREATE USER recap WITH PASSWORD 'recap_pass';
postgres=# CREATE DATABASE recap OWNER recap;
postgres=# GRANT ALL PRIVILEGES ON DATABASE recap TO recap;
postgres=# \q
```

### 3. Verify connection

```bash
psql -U recap -h 127.0.0.1 -d recap -c "SELECT version();"
```

Expected output: PostgreSQL version string (e.g., PostgreSQL 15.x on x86_64-pc-linux-gnu, compiled by ...)

### 4. Set environment variables

**Option A: Export in your shell session (temporary)**
```bash
export POSTGRES_DB=recap
export POSTGRES_USER=recap
export POSTGRES_PASSWORD=recap_pass
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
```

**Option B: Create a `.env` file (persistent)**
```bash
cp .env.postgres.example .env
# Edit .env to match your PostgreSQL setup
```

If using `.env`, ensure you have `python-dotenv` installed:
```bash
pip install python-dotenv
```

### 5. Run Django migrations

```bash
cd /home/osteen/RECAP/INVENTORY
source recap/bin/activate
python manage.py migrate
```

Expected output:
```
Operations to perform:
  Apply all migrations: admin, auth, api, ...
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  ...
```

### 6. Create a superuser (optional)

```bash
python manage.py createsuperuser
```

### 7. Test the connection

```bash
python manage.py shell
>>> from django.db import connection
>>> cursor = connection.cursor()
>>> cursor.execute("SELECT 1")
>>> print(cursor.fetchone())
(1,)
```

---

## Docker Alternative (if you have Docker installed)

### 1. Start PostgreSQL container

```bash
cd /home/osteen/RECAP/INVENTORY

# Try docker compose first
docker compose -f docker-compose.postgres.yml up -d

# If that fails, use docker directly (requires docker socket permissions):
docker run -d \
  --name recap-postgres \
  -e POSTGRES_DB=recap \
  -e POSTGRES_USER=recap \
  -e POSTGRES_PASSWORD=recap_pass \
  -p 5432:5432 \
  -v pgdata:/var/lib/postgresql/data \
  postgres:15
```

### 2. Wait for Postgres to be ready

```bash
# Check logs
docker logs recap-postgres

# Test connection (once ready)
psql -U recap -h 127.0.0.1 -d recap -c "SELECT 1;"
```

### 3. Run migrations (same as above)

```bash
export POSTGRES_DB=recap
export POSTGRES_USER=recap
export POSTGRES_PASSWORD=recap_pass
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432

python manage.py migrate
```

### 4. Stop the container when done

```bash
docker compose -f docker-compose.postgres.yml down
# or
docker stop recap-postgres && docker rm recap-postgres
```

---

## Switching Between SQLite and PostgreSQL

### To use SQLite (default):
```bash
# Unset Postgres environment variables
unset POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT
# or remove DATABASE_URL if set

# Django will automatically use sqlite3
python manage.py runserver
```

### To use PostgreSQL:
```bash
# Set environment variables (or use .env)
export POSTGRES_DB=recap
export POSTGRES_USER=recap
export POSTGRES_PASSWORD=recap_pass
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432

# Django will automatically detect and use PostgreSQL
python manage.py runserver
```

---

## Troubleshooting

### Connection refused (port 5432)

```bash
# Check if Postgres is running
psql -U recap -h 127.0.0.1 -d recap -c "SELECT 1;"

# If error: "connection refused", start Postgres:
# macOS: brew services start postgresql@15
# Ubuntu: sudo systemctl start postgresql
# Docker: docker start recap-postgres
```

### Authentication failed

```bash
# Verify credentials match your .env or environment variables
# Check psql can connect with the same credentials
psql -U recap -h 127.0.0.1 -d recap

# If auth fails, reset the password:
sudo -u postgres psql
postgres=# ALTER USER recap WITH PASSWORD 'recap_pass';
postgres=# \q
```

### Database already exists

```bash
# Drop and recreate (careful: loses all data)
psql -U postgres -c "DROP DATABASE IF EXISTS recap;"
psql -U postgres -c "CREATE DATABASE recap OWNER recap;"
```

### Django says "No module named psycopg2"

```bash
# Install the driver
pip install psycopg2-binary
# or for production:
pip install psycopg2
```

### Migrations fail

```bash
# Check migration status
python manage.py showmigrations

# If stuck, you may need to roll back:
python manage.py migrate api 0009  # Go back to a known good state
python manage.py migrate  # Re-apply migrations
```

---

## Performance Tips

- **Indexes:** Django will create indexes automatically for foreign keys and fields marked as `db_index=True`.
- **Connection pooling:** In production, use pgbouncer. For dev, `CONN_MAX_AGE` (in settings.py) defaults to 600 seconds.
- **Large data imports:** If loading > 1GB, consider using `psycopg2` with `COPY` instead of ORM:
  ```python
  from psycopg2.extras import execute_values
  cursor = connection.cursor()
  execute_values(cursor, "INSERT INTO api_product (name, price) VALUES %s", rows)
  connection.commit()
  ```

---

## Next Steps

- Follow the [POSTGRES_MIGRATION_CHECKLIST.md](./POSTGRES_MIGRATION_CHECKLIST.md) for full migration.
- Commit these changes to Git: `git add -A && git commit -m "Add PostgreSQL support"`
- Test against a copy of your production data before migration.

---

**Questions?**
- Django DB docs: https://docs.djangoproject.com/en/5.2/ref/settings/#databases
- PostgreSQL docs: https://www.postgresql.org/docs/15/
- psycopg2 docs: https://www.psycopg.org/psycopg2/docs/
