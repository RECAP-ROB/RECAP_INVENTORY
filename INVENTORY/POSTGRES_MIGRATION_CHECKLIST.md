# PostgreSQL Integration Checklist

## Pre-Migration (Local Development)

- [ ] **Install Python dependencies:**
  ```bash
  pip install psycopg2-binary dj-database-url  # or psycopg2 for production
  pip install -r requirements.txt
  ```

- [ ] **Start local PostgreSQL:**
  - Option A: Docker (if available)
    ```bash
    docker compose -f docker-compose.postgres.yml up -d
    ```
  - Option B: Manual docker run (requires sudo/docker permissions)
    ```bash
    docker run -d --name recap-postgres \
      -e POSTGRES_DB=recap \
      -e POSTGRES_USER=recap \
      -e POSTGRES_PASSWORD=recap_pass \
      -p 5432:5432 \
      -v pgdata:/var/lib/postgresql/data \
      postgres:15
    ```
  - Option C: Local Postgres installation (if not using Docker)
    ```bash
    # macOS: brew install postgresql@15
    # Ubuntu: sudo apt install postgresql-15
    # Then create the recap user and database
    psql -U postgres -c "CREATE USER recap WITH PASSWORD 'recap_pass';"
    psql -U postgres -c "CREATE DATABASE recap OWNER recap;"
    ```

- [ ] **Verify Postgres connectivity:**
  ```bash
  psql -U recap -h 127.0.0.1 -d recap -c "SELECT 1;"
  # Expected output: 1
  ```

## Migration from SQLite to PostgreSQL (Development)

- [ ] **Backup existing SQLite database:**
  ```bash
  cp db.sqlite3 db.sqlite3.backup
  ```

- [ ] **Export data from SQLite:**
  ```bash
  python manage.py dumpdata \
    --natural-primary \
    --natural-foreign \
    --exclude auth.permission \
    --exclude contenttypes \
    --exclude sessions \
    --indent 2 > data.json
  ```

- [ ] **Switch Django to use PostgreSQL:**
  ```bash
  # Option 1: Set environment variables
  export POSTGRES_DB=recap
  export POSTGRES_USER=recap
  export POSTGRES_PASSWORD=recap_pass
  export POSTGRES_HOST=127.0.0.1
  export POSTGRES_PORT=5432

  # Option 2: Create/edit .env file (auto-loaded by django-extensions or similar)
  cp .env.postgres.example .env
  # Edit .env with your PostgreSQL credentials
  ```

- [ ] **Run Django migrations on PostgreSQL:**
  ```bash
  python manage.py migrate
  ```

- [ ] **Load exported data into PostgreSQL:**
  ```bash
  python manage.py loaddata data.json
  ```

- [ ] **Verify data integrity:**
  ```bash
  # Check row counts
  python manage.py shell
  >>> from api.models import Product, Order, RestockItem
  >>> print(f"Products: {Product.objects.count()}")
  >>> print(f"Orders: {Order.objects.count()}")
  >>> print(f"RestockItems: {RestockItem.objects.count()}")
  ```

- [ ] **Run tests against PostgreSQL:**
  ```bash
  python manage.py test api
  pytest tests/
  ```

## Production Deployment (PostgreSQL Managed Service)

- [ ] **Choose a managed DB provider:**
  - AWS RDS PostgreSQL
  - Google Cloud SQL
  - DigitalOcean Managed PostgreSQL
  - Azure Database for PostgreSQL
  - Heroku Postgres

- [ ] **Provision database and get connection string:**
  ```
  DATABASE_URL=postgres://username:password@hostname:5432/dbname
  ```

- [ ] **Set environment variables in production:**
  - Use secrets manager or environment variable service
  - Never commit credentials; use `.env` or CI/CD secrets
  - Example for Heroku:
    ```bash
    heroku config:set DATABASE_URL="postgres://..."
    ```

- [ ] **Backup production SQLite before migration (if needed):**
  ```bash
  mysqldump or pg_dump your_old_db > old_db_backup.sql
  ```

- [ ] **Deploy Django app pointing to new PostgreSQL:**
  ```bash
  git push heroku main
  # or: kubectl apply -f deployment.yaml (for K8s)
  ```

- [ ] **Run migrations in production:**
  ```bash
  heroku run python manage.py migrate
  # or: kubectl exec -it <pod-name> -- python manage.py migrate
  ```

- [ ] **Load data (if needed):**
  ```bash
  heroku run python manage.py loaddata data.json
  # or: kubectl exec -it <pod-name> -- python manage.py loaddata data.json
  ```

- [ ] **Monitor and verify:**
  - Check application logs for errors
  - Verify API endpoints return expected data
  - Monitor database metrics (connections, CPU, disk usage)
  - Set up automated backups (provider usually handles this)

## Configuration Best Practices

- [ ] **Connection pooling (PgBouncer for production):**
  - Use transaction pooling mode for stateless web apps
  - Example config: `pgbouncer.ini`
    ```ini
    [databases]
    recap = host=db.example.com dbname=recap
    [pgbouncer]
    pool_mode = transaction
    max_client_conn = 1000
    default_pool_size = 25
    min_pool_size = 5
    reserve_pool_size = 5
    ```

- [ ] **Set CONN_MAX_AGE in Django settings:**
  ```python
  CONN_MAX_AGE = 600  # Keep connections for 10 minutes
  ```

- [ ] **Enable SSL/TLS for remote connections:**
  - Update `DATABASE_URL` or settings to use `sslmode=require`
  - Example: `postgres://user:pass@host:5432/db?sslmode=require`

- [ ] **Configure Django for safe transactions:**
  ```python
  # api/celery_tasks.py
  from django.db import transaction

  @shared_task
  def my_task(pk):
      # Ensure task is enqueued AFTER database commit
      pass

  # In your view:
  transaction.on_commit(lambda: my_task.delay(product_id))
  ```

## Monitoring & Maintenance

- [ ] **Set up automated backups:**
  - Managed DB: Provider usually handles snapshots
  - Self-hosted: Use `pg_dump` with cron or backup service
  - Example cron: `0 2 * * * pg_dump -U recap recap | gzip > /backups/recap_$(date +%Y%m%d).sql.gz`

- [ ] **Monitor database performance:**
  ```sql
  -- Active connections
  SELECT count(*) FROM pg_stat_activity;

  -- Largest tables
  SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

  -- Index usage
  SELECT schemaname, tablename, indexname FROM pg_indexes ORDER BY tablename;
  ```

- [ ] **Tune autovacuum settings:**
  - Monitor for bloat using `pgstattuple` extension
  - Adjust vacuum frequency for high-volume tables

- [ ] **Set up alerting:**
  - CPU usage > 80%
  - Disk usage > 85%
  - Connection count > threshold
  - Replication lag (if using replicas)

## Rollback Plan

- [ ] **If migration fails, revert to SQLite:**
  ```bash
  # Stop Django app
  python manage.py migrate --noinput  # Run pending SQLite migrations
  # Restore from backup: cp db.sqlite3.backup db.sqlite3
  # Restart Django app
  ```

- [ ] **Keep old SQLite database and backups for ~30 days after successful migration**

- [ ] **Document any schema differences or data loss during migration**

## Helpful Commands

```bash
# Check Django ORM compatibility with PostgreSQL
python manage.py sqlall api | head -50

# Run database shell
python manage.py dbshell

# Show current database engine
python manage.py shell
>>> from django.conf import settings
>>> print(settings.DATABASES['default']['ENGINE'])

# Create a superuser (after migration)
python manage.py createsuperuser

# Verify Celery can connect to DB
celery -A main worker -l info  # Should show no DB connection errors
```

---

**Estimated Timeline:**
- **Development:** 30 min to 1 hour (local setup + migration)
- **Staging:** 1–2 hours (with testing and verification)
- **Production:** 2–4 hours (depending on data size and downtime tolerance)

**Risks & Mitigations:**
| Risk | Mitigation |
|------|-----------|
| Data loss during migration | Backup SQLite, validate counts post-migration |
| Connection exhaustion | Use connection pooling (pgbouncer) |
| Slow queries | Create indexes on frequently filtered columns |
| Long downtime | Use online/zero-downtime migration patterns |
| Credential exposure | Use secrets manager; never commit to git |
