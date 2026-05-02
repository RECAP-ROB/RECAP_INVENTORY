# Celery Integration: Step-by-Step Implementation

This guide provides concrete, copy-paste examples for integrating Celery into your event-driven restock system.

---

## Quick Start: 10-Minute Setup

### Step 1: Install Dependencies
```bash
pip install celery redis
# Add to requirements.txt:
# celery==5.3.6
# redis==5.0.1
```

### Step 2: Create `main/celery.py`
```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

app = Celery('recap_inventory')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

### Step 3: Update `main/__init__.py`
```python
from .celery import app as celery_app
__all__ = ('celery_app',)
```

### Step 4: Add to `main/settings.py`
```python
# At the end of settings.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'priority_steps': list(range(10)),
    'sep': ':',
    'queue_order_strategy': 'priority',
    'visibility_timeout': 3600,
}
```

### Step 5: Start Services
```bash
# Terminal 1: Start Redis
redis-server --port 6379

# Terminal 2: Start Django
python manage.py runserver

# Terminal 3: Start Celery worker
celery -A main worker -l info
```

**That's it!** Now you can queue tasks with `.delay()` and `.apply_async()`.

---

## Real Code Examples

### Example 1: Simple Task

```python
# api/celery_tasks.py
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def validate_restock_task(self, product_id):
    """Simple task that validates a product"""
    try:
        from api.models import Product, RestockItem
        
        product = Product.objects.get(id=product_id)
        
        # Check conditions
        if not product.auto_restock_enabled:
            return {'is_valid': False, 'reason': 'disabled'}
        
        pending = RestockItem.objects.filter(
            product_id=product_id,
            status='PENDING'
        ).exists()
        
        if pending:
            return {'is_valid': False, 'reason': 'pending_exists'}
        
        logger.info(f"Product {product_id} passed validation")
        return {'is_valid': True, 'product_id': product_id}
        
    except Product.DoesNotExist:
        self.dont_retry = True  # Don't retry - product doesn't exist
        raise
    except Exception as exc:
        logger.error(f"Validation error: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry in 5 minutes
```

### Example 2: Task with Database Changes

```python
@shared_task(bind=True, max_retries=3)
def create_restock_item_task(self, product_id, current_stock):
    """Create a RestockItem in database"""
    try:
        from api.models import Product, RestockItem
        from api.events import EventBus
        
        product = Product.objects.get(id=product_id)
        
        # Calculate quantity
        quantity = max(0, product.restock_quantity - current_stock)
        
        # Create in database
        restock_item = RestockItem.objects.create(
            product=product,
            quantity=quantity,
            shelf_location=product.shelf_location or 'Unknown',
            status='PENDING',
        )
        
        # Publish event
        EventBus.publish('restock_item_created', {
            'restock_item_id': restock_item.id,
            'product_id': product_id,
            'quantity': quantity,
        })
        
        logger.info(f"Created RestockItem {restock_item.id}")
        
        return {
            'restock_item_id': restock_item.id,
            'quantity': quantity,
        }
        
    except Product.DoesNotExist:
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Failed to create RestockItem: {exc}")
        raise self.retry(exc=exc, countdown=300)
```

### Example 3: Task with External API Call

```python
@shared_task(bind=True, max_retries=5)
def trigger_robot_mission_task(self, restock_item_id):
    """Send mission to ROS Bridge"""
    try:
        from api.models import RestockItem
        from api.events import EventBus
        import requests
        
        restock_item = RestockItem.objects.get(id=restock_item_id)
        product = restock_item.product
        
        # Update status
        restock_item.status = 'IN_PROGRESS'
        restock_item.save()
        
        # Call external API with retry logic
        url = 'http://localhost:9000/restock/queue'
        payload = {
            'item_id': restock_item_id,
            'product_name': product.name,
            'quantity': restock_item.quantity,
            'shelf_location': product.shelf_location,
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Robot mission started for item {restock_item_id}")
            
            EventBus.publish('restock_mission_started', {
                'restock_item_id': restock_item_id,
                'product_name': product.name,
            })
            
            return {'mission_started': True}
            
        except (requests.ConnectionError, requests.Timeout) as exc:
            logger.warning(f"ROS Bridge unreachable: {exc}")
            # Retry: server might be down temporarily
            countdown = 600 * (self.request.retries + 1)  # Exponential backoff
            raise self.retry(exc=exc, countdown=countdown)
        
    except RestockItem.DoesNotExist:
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Error triggering mission: {exc}")
        raise self.retry(exc=exc, countdown=300)
```

### Example 4: Task Chaining (Sequential Execution)

```python
from celery import chain, shared_task

@shared_task
def workflow_orchestration(product_id, current_stock):
    """
    Execute tasks in sequence:
    1. Validate
    2. Create item
    3. Trigger robot
    4. Monitor
    """
    from api.celery_tasks import (
        validate_restock_task,
        create_restock_item_task,
        trigger_robot_mission_task,
        monitor_mission_task,
    )
    
    # Create a chain: task1() → task2() → task3() → task4()
    workflow = chain(
        validate_restock_task.s(product_id),
        create_restock_item_task.s(current_stock),  # Uses output from validate
        trigger_robot_mission_task.s(),  # Uses output from create
        monitor_mission_task.s(),  # Uses output from trigger
    )
    
    # Execute the chain
    result = workflow.apply_async()
    
    return {'task_id': str(result.id)}

# To use:
# workflow_orchestration.delay(product_id=1, current_stock=2)
```

### Example 5: Task with Callbacks

```python
from celery import chain, chord, shared_task

@shared_task
def workflow_with_callbacks(product_id, current_stock):
    """
    Execute tasks with conditional branching based on results
    """
    from api.celery_tasks import (
        validate_restock_task,
        create_restock_item_task,
        trigger_robot_mission_task,
    )
    
    # Define callback: only create item if validation passed
    def on_validate_completed(validation_result):
        if validation_result['is_valid']:
            # If valid, chain to next task
            return create_restock_item_task.delay(product_id, current_stock)
        else:
            logger.warning(f"Validation failed: {validation_result['reason']}")
            return None
    
    # Start the chain with callback
    validate_task = validate_restock_task.delay(product_id)
    validate_task.then(on_validate_completed)
    
    return {'initiated': True}
```

### Example 6: Task Groups (Parallel Execution)

```python
from celery import group, shared_task

@shared_task
def check_all_products():
    """Check multiple products in parallel"""
    from api.models import Product
    from api.celery_tasks import validate_restock_task
    
    products = Product.objects.filter(auto_restock_enabled=True)
    
    # Create a group of tasks - they run in parallel
    parallel_tasks = group(
        validate_restock_task.s(product.id)
        for product in products
    )
    
    # Execute group
    result = parallel_tasks.apply_async()
    
    # Get results when ready
    all_results = result.get()
    
    return {
        'total_products': len(products),
        'results': all_results,
    }
```

### Example 7: Scheduled Tasks (Beat)

```python
# main/settings.py

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'check-low-stock-every-hour': {
        'task': 'api.celery_tasks.check_all_products',
        'schedule': crontab(minute=0),  # Every hour
    },
    'cleanup-old-restocks-daily': {
        'task': 'api.celery_tasks.cleanup_old_restocks',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
    'send-inventory-report-weekly': {
        'task': 'api.celery_tasks.send_inventory_report',
        'schedule': crontab(day_of_week=1, hour=9, minute=0),  # Monday 9 AM
    },
}

# Then run Celery Beat:
# celery -A main beat -l info
```

### Example 8: Task with Progress Updates

```python
@shared_task(bind=True)
def monitor_mission_task(self, restock_item_id):
    """Monitor mission with progress updates"""
    try:
        from api.models import RestockItem
        import requests
        
        restock_item = RestockItem.objects.get(id=restock_item_id)
        
        # Poll status with progress updates
        url = f'http://localhost:9000/missions/{restock_item_id}'
        
        for attempt in range(10):  # Poll for up to 10 times
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                mission_status = response.json()
                
                # Send progress update (visible in Celery Flower)
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': attempt,
                        'total': 10,
                        'status': mission_status.get('status'),
                        'progress': mission_status.get('progress'),
                    }
                )
                
                logger.info(f"Mission progress: {mission_status}")
                
                # Check if complete
                if mission_status.get('status') == 'COMPLETED':
                    restock_item.status = 'COMPLETED'
                    restock_item.save()
                    return {'status': 'COMPLETED'}
                
                if mission_status.get('status') == 'FAILED':
                    restock_item.status = 'FAILED'
                    restock_item.save()
                    return {'status': 'FAILED'}
                    
            except requests.RequestException as exc:
                logger.warning(f"Error checking mission status: {exc}")
            
            # Wait before next poll
            import time
            time.sleep(30)
        
        logger.warning(f"Mission monitoring timeout for item {restock_item_id}")
        return {'status': 'TIMEOUT'}
        
    except RestockItem.DoesNotExist:
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Error monitoring mission: {exc}")
        raise self.retry(exc=exc, countdown=300)
```

### Example 9: Using Task Signatures and Options

```python
from celery import group, chain, chord
from api.celery_tasks import (
    validate_restock_task,
    create_restock_item_task,
    trigger_robot_mission_task,
)

# Method 1: Using .s() - creates signature
task_sig = validate_restock_task.s(product_id=1)
result = task_sig.apply_async()

# Method 2: Using .delay() - quick send
task = validate_restock_task.delay(product_id=1)

# Method 3: Using .apply_async() - full control
task = validate_restock_task.apply_async(
    args=[1],  # product_id
    kwargs={},
    countdown=60,  # Execute in 60 seconds
    expires=600,  # Expires in 10 minutes
    priority=9,  # 0-9 scale
    queue='default',
    retry=True,
    retry_policy={
        'max_retries': 3,
        'interval_start': 1,
        'interval_step': 2,
        'interval_max': 0.2,
    },
    time_limit=3600,
)

# Get task status
print(task.status)  # PENDING, STARTED, SUCCESS, FAILURE
print(task.result)  # Result value when complete
print(task.is_ready())  # Is execution complete?
print(task.successful())  # Did it succeed?
print(task.failed())  # Did it fail?

# Wait for result (blocking)
try:
    result = task.get(timeout=30)
    print(f"Result: {result}")
except task.TimeLimitExceeded:
    print("Task took too long")
except Exception as exc:
    print(f"Task failed: {exc}")
```

---

## Updated Signal Handler

```python
# api/signals.py - Using Celery tasks
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
    When product stock falls below threshold, queue Celery task.
    
    This is NON-BLOCKING:
    - Signal handler returns immediately
    - Task is queued to Redis
    - Celery worker executes in background
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
            # Queue task - this returns immediately!
            from api.celery_tasks import execute_restock_workflow
            
            task = execute_restock_workflow.delay(
                product_id=instance.id,
                current_stock=current_stock,
            )
            
            logger.info(f"Restock workflow queued: task_id={task.id}")
            
            # Publish event for WebSocket
            from api.events import EventBus
            EventBus.publish('restock_workflow_queued', {
                'product_id': instance.id,
                'task_id': str(task.id),
            })
            
        except Exception as exc:
            logger.error(f"Failed to queue restock task: {exc}")
    
    # Clean up cache
    _product_stock_cache.pop(instance.pk, None)


@receiver(post_save, sender=RestockItem)
def broadcast_restock_updates(sender, instance, **kwargs):
    """Broadcast restock updates via WebSocket"""
    broadcast_update(instance)
```

---

## API Endpoint to Track Task Status

```python
# api/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from main.celery import app

class TaskStatusView(APIView):
    """Get status of a Celery task"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, task_id):
        """
        GET /api/tasks/{task_id}/status/
        Returns the current status of a task
        """
        result = app.AsyncResult(task_id)
        
        data = {
            'task_id': task_id,
            'status': result.status,  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
            'result': result.result if result.successful() else None,
            'error': str(result.info) if result.failed() else None,
            'traceback': str(result.traceback) if result.failed() else None,
        }
        
        # Add progress if available
        if hasattr(result, 'info') and isinstance(result.info, dict):
            data['progress'] = result.info.get('progress')
            data['current'] = result.info.get('current')
            data['total'] = result.info.get('total')
        
        return Response(data)

# api/urls.py
from django.urls import path
from .views import TaskStatusView

urlpatterns = [
    # ...
    path('tasks/<str:task_id>/status/', TaskStatusView.as_view()),
]
```

---

## Testing Celery Tasks

```python
# api/test_celery_tasks.py
from django.test import TestCase
from unittest.mock import patch, MagicMock
from celery.result import EagerResult
from main.celery import app
from api.models import Product, RestockItem
from api.celery_tasks import (
    validate_restock_task,
    create_restock_item_task,
    trigger_robot_mission_task,
)

# Enable eager mode for testing
app.conf.task_always_eager = True
app.conf.task_eager_propagates = True


class ValidateRestockTaskTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=5,
            auto_restock_enabled=True,
            restock_threshold=5,
        )
    
    def test_validation_passes(self):
        """Test successful validation"""
        result = validate_restock_task.delay(self.product.id)
        
        self.assertTrue(result.successful())
        self.assertEqual(result.result['is_valid'], True)
    
    def test_validation_fails_disabled(self):
        """Test validation fails when auto_restock disabled"""
        self.product.auto_restock_enabled = False
        self.product.save()
        
        result = validate_restock_task.delay(self.product.id)
        
        self.assertTrue(result.successful())
        self.assertEqual(result.result['is_valid'], False)
    
    def test_validation_fails_pending_exists(self):
        """Test validation fails when pending restock exists"""
        RestockItem.objects.create(
            product=self.product,
            quantity=5,
            shelf_location='TEST',
            status='PENDING',
        )
        
        result = validate_restock_task.delay(self.product.id)
        
        self.assertTrue(result.successful())
        self.assertEqual(result.result['is_valid'], False)


class CreateRestockItemTaskTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=2,
            auto_restock_enabled=True,
            restock_quantity=10,
            shelf_location="SHELF_A1",
        )
    
    def test_create_restock_item(self):
        """Test RestockItem creation"""
        result = create_restock_item_task.delay(
            self.product.id,
            current_stock=2
        )
        
        self.assertTrue(result.successful())
        self.assertEqual(result.result['quantity'], 8)  # 10 - 2
        
        # Verify created in database
        restock = RestockItem.objects.get(id=result.result['restock_item_id'])
        self.assertEqual(restock.quantity, 8)
        self.assertEqual(restock.status, 'PENDING')


class TriggerRobotMissionTaskTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name="Test Product",
            description="Test",
            price=9.99,
            stock=2,
            shelf_location="SHELF_A1",
        )
        self.restock_item = RestockItem.objects.create(
            product=self.product,
            quantity=8,
            shelf_location="SHELF_A1",
            status='PENDING',
        )
    
    @patch('requests.post')
    def test_trigger_success(self, mock_post):
        """Test successful robot trigger"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'queued'}
        mock_post.return_value = mock_response
        
        result = trigger_robot_mission_task.delay(self.restock_item.id)
        
        self.assertTrue(result.successful())
        self.assertTrue(result.result['mission_started'])
    
    @patch('requests.post')
    def test_trigger_retry_on_connection_error(self, mock_post):
        """Test that task retries on connection error"""
        import requests
        mock_post.side_effect = requests.ConnectionError("No connection")
        
        result = trigger_robot_mission_task.delay(self.restock_item.id)
        
        # In eager mode, retries are propagated
        self.assertTrue(result.failed())
```

---

## Docker Compose (Production-Ready)

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: recap_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - recap_network

  postgres:
    image: postgres:15-alpine
    container_name: recap_postgres
    environment:
      POSTGRES_DB: recap_inventory
      POSTGRES_USER: recap_user
      POSTGRES_PASSWORD: recap_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - recap_network

  django:
    build: .
    container_name: recap_django
    command: python manage.py runserver 0.0.0.0:8000
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - postgres
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
      DATABASE_URL: postgresql://recap_user:recap_password@postgres:5432/recap_inventory
    volumes:
      - .:/app
    networks:
      - recap_network

  celery_worker_default:
    build: .
    container_name: recap_celery_default
    command: celery -A main worker -Q default -l info
    depends_on:
      - redis
      - postgres
      - django
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    volumes:
      - .:/app
    networks:
      - recap_network

  celery_worker_robot:
    build: .
    container_name: recap_celery_robot
    command: celery -A main worker -Q robot -l info -c 2
    depends_on:
      - redis
      - postgres
      - django
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    volumes:
      - .:/app
    networks:
      - recap_network

  celery_worker_monitoring:
    build: .
    container_name: recap_celery_monitoring
    command: celery -A main worker -Q monitoring -l info -c 1
    depends_on:
      - redis
      - postgres
      - django
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    volumes:
      - .:/app
    networks:
      - recap_network

  celery_beat:
    build: .
    container_name: recap_celery_beat
    command: celery -A main beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    depends_on:
      - redis
      - postgres
      - django
      - celery_worker_default
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    volumes:
      - .:/app
    networks:
      - recap_network

  flower:
    build: .
    container_name: recap_flower
    command: celery -A main flower --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis
      - celery_worker_default
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    volumes:
      - .:/app
    networks:
      - recap_network

volumes:
  redis_data:
  postgres_data:

networks:
  recap_network:
    driver: bridge
```

---

## Running Everything

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f django celery_worker_default flower

# Stop everything
docker-compose down

# Monitor Flower dashboard
open http://localhost:5555
```

This implementation provides a complete, production-ready Celery integration! 🚀

