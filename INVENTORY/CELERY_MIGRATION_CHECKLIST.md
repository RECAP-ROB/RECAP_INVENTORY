# Celery Integration: Migration Checklist

A step-by-step checklist for integrating Celery into your existing event-driven restock system.

---

## Phase 1: Setup & Configuration (1-2 hours)

### 1.1 Install Dependencies
```bash
# Install Celery and Redis
pip install celery redis

# Or with all extras
pip install celery[redis] redis

# Update requirements.txt
echo "celery==5.3.6" >> requirements.txt
echo "redis==5.0.1" >> requirements.txt

# Install Redis on your system
# Ubuntu/Debian:
sudo apt-get install redis-server

# macOS:
brew install redis

# Verify Redis works
redis-cli ping  # Should return PONG
```

### 1.2 Create Celery Configuration File

**File: `main/celery.py`** (NEW FILE)

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

app = Celery('recap_inventory')

# Load configuration from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

- [ ] Created `main/celery.py`

### 1.3 Update Django Init File

**File: `main/__init__.py`** (MODIFY)

```python
# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ('celery_app',) 
```

- [ ] Updated `main/__init__.py`

### 1.4 Add Celery Configuration to Django Settings

**File: `main/settings.py`** (APPEND TO END)

```python
# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Task execution settings
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_TASK_DEFAULT_RATE_LIMIT = '1000/s'  # 1000 tasks per second
CELERY_TASK_TRACK_STARTED = True  # Track when task starts
CELERY_TASK_TIME_LIMIT = 30 * 60  # Hard timeout: 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # Soft timeout: 25 minutes

# Worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Prefetch 1 task only
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Prevent memory leaks

# Broker settings
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'priority_steps': list(range(10)),  # 10 priority levels (0-9)
    'sep': ':',
    'queue_order_strategy': 'priority',
    'visibility_timeout': 3600,  # 1 hour
}

# Task routing - Direct tasks to specific queues
CELERY_TASK_ROUTES = {
    'api.celery_tasks.validate_restock_task': {
        'queue': 'default',
        'priority': 10,
    },
    'api.celery_tasks.create_restock_item_task': {
        'queue': 'default',
        'priority': 10,
    },
    'api.celery_tasks.trigger_robot_mission_task': {
        'queue': 'robot',
        'priority': 10,
    },
    'api.celery_tasks.monitor_mission_task': {
        'queue': 'monitoring',
        'priority': 3,
    },
    'api.celery_tasks.execute_restock_workflow': {
        'queue': 'default',
        'priority': 9,
    },
}

# Scheduled tasks (Celery Beat)
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'check-low-stock-daily': {
        'task': 'api.celery_tasks.check_low_stock_products',
        'schedule': crontab(hour=6, minute=0),  # 6 AM daily
    },
}
```

- [ ] Updated `main/settings.py`

---

## Phase 2: Create Celery Tasks (2-4 hours)

### 2.1 Create Celery Tasks File

**File: `api/celery_tasks.py`** (NEW FILE)

Create this file with all task implementations. See `CELERY_IMPLEMENTATION_EXAMPLES.md` for complete code.

Key tasks to implement:
- [ ] `validate_restock_task(product_id)` - validates conditions
- [ ] `create_restock_item_task(product_id, current_stock)` - creates DB record
- [ ] `trigger_robot_mission_task(restock_item_id)` - calls ROS Bridge
- [ ] `monitor_mission_task(restock_item_id)` - monitors progress
- [ ] `execute_restock_workflow(product_id, current_stock)` - orchestrates chain

### 2.2 Create Events (Optional but Recommended)

**File: `api/events.py`** (NEW FILE)

```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json

class EventBus:
    """Publish domain events to Redis/Channels"""
    
    @staticmethod
    def publish(event_type, data):
        """Publish event to WebSocket subscribers"""
        channel_layer = get_channel_layer()
        
        async_to_sync(channel_layer.group_send)(
            "restock_updates",
            {
                "type": "send_event",
                "event_type": event_type,
                "data": data,
            }
        )

# Example usage in tasks:
# EventBus.publish('restock_validated', {'product_id': 1})
```

- [ ] Created `api/events.py`

---

## Phase 3: Update Existing Files

### 3.1 Update Signal Handlers

**File: `api/signals.py`** (REPLACE)

```python
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Product, RestockItem
from .websocket_events import broadcast_update
import logging

logger = logging.getLogger(__name__)

# Cache for tracking stock changes
_product_stock_cache = {}


@receiver(pre_save, sender=Product)
def cache_product_stock(sender, instance, **kwargs):
    """Cache the stock value before changes"""
    try:
        previous = Product.objects.get(pk=instance.pk)
        _product_stock_cache[instance.pk] = previous.stock
    except Product.DoesNotExist:
        _product_stock_cache[instance.pk] = instance.stock


@receiver(post_save, sender=Product)
def handle_stock_below_threshold(sender, instance, created, **kwargs):
    """
    Queue restock workflow when stock falls below threshold.
    Uses Celery for non-blocking asynchronous execution.
    """
    if created:
        return
    
    previous_stock = _product_stock_cache.get(instance.pk, instance.stock)
    current_stock = instance.stock
    
    # Check if stock fell below threshold
    if (
        current_stock < instance.restock_threshold
        and previous_stock >= instance.restock_threshold
        and instance.auto_restock_enabled
    ):
        logger.info(f"Stock below threshold for '{instance.name}'")
        
        try:
            # Import here to avoid circular imports
            from .celery_tasks import execute_restock_workflow
            
            # Queue task via Celery (non-blocking!)
            task = execute_restock_workflow.delay(
                product_id=instance.id,
                current_stock=current_stock,
            )
            
            logger.info(f"Restock workflow queued: task_id={task.id}")
            
        except Exception as exc:
            logger.error(f"Failed to queue restock task: {exc}")
    
    # Clean up cache
    _product_stock_cache.pop(instance.pk, None)


@receiver(post_save, sender=RestockItem)
def broadcast_restock_updates(sender, instance, **kwargs):
    """Broadcast RestockItem updates via WebSocket"""
    broadcast_update(instance)
    logger.info(f"RestockItem broadcasted: {instance.id} - {instance.status}")
```

- [ ] Updated `api/signals.py`

### 3.2 Update Views (Optional)

**File: `api/views.py`** (ADD NEW CLASS)

Add this class to track Celery task status:

```python
class TaskStatusView(APIView):
    """Get status of a Celery task"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, task_id):
        """GET /api/tasks/{task_id}/status/"""
        from main.celery import app
        
        result = app.AsyncResult(task_id)
        
        return Response({
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.successful() else None,
            'error': str(result.info) if result.failed() else None,
        })
```

- [ ] Added `TaskStatusView` to `api/views.py`
- [ ] Added URL route: `path('tasks/<str:task_id>/status/', TaskStatusView.as_view())`

---

## Phase 4: Testing (2-3 hours)

### 4.1 Create Unit Tests

**File: `api/test_celery_tasks.py`** (NEW FILE)

See `CELERY_IMPLEMENTATION_EXAMPLES.md` for test code.

Key tests:
- [ ] `ValidateRestockTaskTest` - validation logic
- [ ] `CreateRestockItemTaskTest` - item creation
- [ ] `TriggerRobotMissionTaskTest` - API call mocking
- [ ] `WorkflowIntegrationTest` - full chain execution

### 4.2 Run Tests

```bash
# Set Celery to eager mode for testing
export CELERY_ALWAYS_EAGER=True

# Run tests
python manage.py test api.test_celery_tasks -v 2
```

- [ ] All tests passing

### 4.3 Manual Testing

```bash
# Terminal 1: Start Redis
redis-server --port 6379

# Terminal 2: Start Django
python manage.py runserver 0.0.0.0:8000

# Terminal 3: Start Celery worker
celery -A main worker -Q default,robot,monitoring -l info

# Terminal 4: Test manually
cd /path/to/project
python manage.py shell

# In Django shell:
from api.models import Product, Order, User
from api.serializers import OrderCreateSerializer

# Create test product
product = Product.objects.create(
    name="Test Coffee",
    price=9.99,
    stock=7,
    restock_threshold=5,
    restock_quantity=10,
    auto_restock_enabled=True,
    shelf_location="TEST_SHELF"
)

# Create order that reduces stock below threshold
# This should trigger the restock workflow
product.stock = 2
product.save()

# Check Celery worker output - should show tasks executing!
```

- [ ] Manual test successful

---

## Phase 5: Monitoring & Observability (1 hour)

### 5.1 Install Flower (Web UI)

```bash
pip install flower

# Start Flower
celery -A main flower --port=5555

# Access at http://localhost:5555
```

- [ ] Flower installed and running
- [ ] Access http://localhost:5555 to monitor tasks

### 5.2 Add Logging

Update `logger` calls in tasks using Python's built-in logging:

```python
import logging

logger = logging.getLogger(__name__)

@shared_task
def my_task():
    logger.info("Starting my_task")
    logger.debug(f"Input: {input_data}")
    try:
        result = do_work()
        logger.info(f"Task completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"Task failed: {exc}", exc_info=True)
        raise
```

- [ ] Debug logging in all tasks
- [ ] Error logging with exception info

---

## Phase 6: Production Deployment (varies)

### 6.1 Choose Message Broker

For production, choose one:

**Option A: Redis (Simple)**
```bash
# Already used for channels, reuse for Celery
# Single point of failure
redis-server --requirepass your_password
```

**Option B: RabbitMQ (Reliable)**
```bash
# More reliable than Redis
brew install rabbitmq  # or docker
rabbitmq-server

# Update settings.py:
CELERY_BROKER_URL = 'amqp://guest:guest@rabbitmq:5672//'
```

**Option C: Both (Recommended)**
```
Redis for channels (WebSocket)
RabbitMQ for Celery (Task queue)
```

- [ ] Choose broker

### 6.2 Setup Worker Processes

Option A: Using Supervisor (Linux/macOS)

**File: `/etc/supervisor/conf.d/recap_celery.conf`**

```ini
[program:recap_celery_default]
process_name=recap_celery_default_%(process_num)02d
command=celery -A main worker -Q default -l info --concurrency=4
directory=/home/recap/INVENTORY
numprocs=2
stdout_logfile=/var/log/celery/default.log
stderr_logfile=/var/log/celery/default.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600

[program:recap_celery_robot]
command=celery -A main worker -Q robot -l info --concurrency=2
directory=/home/recap/INVENTORY
numprocs=1
stdout_logfile=/var/log/celery/robot.log
stderr_logfile=/var/log/celery/robot.log
autostart=true
autorestart=true

[program:recap_celery_monitoring]
command=celery -A main worker -Q monitoring -l info --concurrency=1
directory=/home/recap/INVENTORY
numprocs=1
stdout_logfile=/var/log/celery/monitoring.log
stderr_logfile=/var/log/celery/monitoring.log
autostart=true
autorestart=true
```

Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start recap_celery:*
```

- [ ] Supervisor configured

Option B: Using Systemd (Modern Linux)

**File: `/etc/systemd/system/recap-celery.service`**

```ini
[Unit]
Description=RECAP Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=recap
Group=recap
WorkingDirectory=/home/recap/INVENTORY
ExecStart=/home/recap/INVENTORY/recap/bin/celery -A main worker -l info

Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable recap-celery.service
sudo systemctl start recap-celery.service
```

- [ ] Systemd service created and running

### 6.3 Setup Celery Beat (Scheduling)

For periodic tasks like "check stock every hour":

```bash
pip install django-celery-beat

# Add to INSTALLED_APPS in settings.py:
'django_celery_beat',

# Create tables
python manage.py migrate

# Start Celery Beat
celery -A main beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

- [ ] Celery Beat installed
- [ ] Database scheduler configured

### 6.4 Docker Deployment

See `CELERY_IMPLEMENTATION_EXAMPLES.md` for complete Docker Compose file.

- [ ] Docker Compose created
- [ ] All services running in containers

### 6.5 Deploy to Production

```bash
# 1. Update requirements.txt
pip install celery redis django-celery-beat

# 2. Push to production
git add requirements.txt
git commit -m "Add Celery for distributed task queue"
git push

# 3. On production server
git pull
pip install -r requirements.txt

# 4. Start services
supervisorctl restart recap_celery:*

# 5. Monitor with Flower
# Access http://your-server:5555
```

- [ ] Deployed to production
- [ ] All workers running
- [ ] Monitoring active

---

## Phase 7: Verification

### 7.1 Health Checks

```bash
# Check Redis connection
redis-cli ping  # Should return PONG

# Check Celery worker status
celery -A main inspect active  # Shows active tasks
celery -A main inspect reserved  # Shows reserved tasks
celery -A main inspect stats  # Shows worker stats

# Check task queue
celery -A main purge  # Clear queue (if needed)
```

- [ ] Redis responding
- [ ] All workers connected
- [ ] Queue empty or healthy

### 7.2 End-to-End Test

```bash
# 1. Create product with low stock
python manage.py shell
>>> from api.models import Product
>>> p = Product.objects.create(name="Test", price=10, stock=7, restock_threshold=5, restock_quantity=10, shelf_location="A1")

# 2. Trigger restock by reducing stock
>>> p.stock = 2
>>> p.save()  # Should queue task

# 3. Check Flower dashboard
# Visit http://localhost:5555
# Should see tasks executing in real-time

# 4. Verify results
>>> from api.models import RestockItem
>>> RestockItem.objects.last()
# Should show a new PENDING item

# 5. Mock robot completion (for testing)
>>> restock = RestockItem.objects.last()
>>> restock.status = 'COMPLETED'
>>> restock.save()
```

- [ ] End-to-end workflow tested
- [ ] Tasks visible in Flower
- [ ] RestockItem created successfully

---

## Phase 8: Performance Optimization (Optional)

### 8.1 Tuning Worker Concurrency

```bash
# Default: 4 workers per CPU core
celery -A main worker -c 4

# For I/O-heavy tasks (network calls)
celery -A main worker -c 8

# For CPU-heavy tasks
celery -A main worker -c 2

# Monitor and adjust based on CPU/memory usage
```

### 8.2 Task Priority Fine-Tuning

Adjust priority scores based on your needs:

```python
CELERY_TASK_ROUTES = {
    # Critical: Robot API (must execute immediately)
    'api.celery_tasks.trigger_robot_mission_task': {
        'queue': 'robot',
        'priority': 10,  # Highest
    },
    
    # High: Validation (should be fast)
    'api.celery_tasks.validate_restock_task': {
        'queue': 'default',
        'priority': 9,
    },
    
    # Medium: Creation (normal)
    'api.celery_tasks.create_restock_item_task': {
        'queue': 'default',
        'priority': 5,
    },
    
    # Low: Monitoring (can wait)
    'api.celery_tasks.monitor_mission_task': {
        'queue': 'monitoring',
        'priority': 1,  # Lowest
    },
}
```

### 8.3 Rate Limiting

```python
@shared_task(rate_limit='10/m')  # Max 10 per minute
def rate_limited_task():
    pass
```

---

## Troubleshooting

### Issue: Tasks not executing

```bash
# 1. Check if Redis is running
redis-cli ping

# 2. Check if worker is connected
celery -A main inspect active

# 3. Check if task is in queue
celery -A main inspect reserved

# 4. Clear queue and restart
redis-cli FLUSHALL
celery -A main purge
celery -A main worker -l debug  # Verbose logging
```

### Issue: Memory leaks

```python
# In celery.py
app.conf.update(
    worker_max_tasks_per_child=1000,  # Restart after 1000 tasks
)
```

### Issue: Tasks timing out

```python
# Increase time limits
@shared_task(time_limit=7200)  # 2 hours hard limit
def long_task():
    pass
```

---

## Checklist Summary

- [ ] Phase 1: Setup complete (celery.py, settings, requirements)
- [ ] Phase 2: Tasks created and implemented
- [ ] Phase 3: Signals and views updated
- [ ] Phase 4: Tests written and passing
- [ ] Phase 5: Flower monitoring installed
- [ ] Phase 6: Production deployment configured
- [ ] Phase 7: End-to-end testing verified
- [ ] Phase 8: Performance tuning complete

**Congratulations! Your Celery integration is ready for production! 🚀**

