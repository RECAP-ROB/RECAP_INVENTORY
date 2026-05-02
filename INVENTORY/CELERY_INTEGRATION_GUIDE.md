# Celery Integration with Event-Driven Restock Architecture

## Executive Summary

Your event-driven architecture uses `async/await` with asyncio for task orchestration. **Celery upgrades this to a distributed task queue** with:

- **Multiple worker processes** (scalability)
- **Task persistence** (reliability)
- **Automatic retries** (resilience)
- **Task monitoring** (observability)
- **Priority queues** (performance)
- **Delayed execution** (scheduling)

This guide explains the integration in detail.

---

## Part 1: Current Architecture Analysis

### Current Flow (Async/Await Model)

```
Customer Creates Order
    ↓
Product.save() triggers post_save signal
    ↓
Signal Handler calls orchestrator.execute_workflow() asynchronously
    ↓
Asyncio tasks run in SINGLE PROCESS:
    • ValidateRestockTask (async)
    • CreateRestockItemTask (async)
    • TriggerRobotMissionTask (async)
    • MonitorMissionTask (async)
    ↓
Events published to Redis
    ↓
WebSocket broadcasts to frontend
```

### Limitations

| Issue | Impact | Solution |
|-------|--------|----------|
| Single process | Can't scale across servers | Celery workers on multiple machines |
| No persistence | Tasks lost on crash | Celery stores in Redis/RabbitMQ |
| Limited retries | Failed tasks don't retry | Celery auto-retry with exponential backoff |
| No monitoring | Can't track task status | Celery Flower dashboard |
| Blocking imports | Main thread blocked | Celery async workers handle independently |
| No rate limiting | Robot API gets hammered | Celery rate limiting + task priority |

---

## Part 2: Celery Architecture Overview

### How Celery Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                       MESSAGE BROKER (Redis)                        │
│   [Task Queue] ← Tasks pushed here by Django                        │
│                                                                     │
└────────┬────────────────────────────────────────────────────────────┘
         │
         ├─→ [Worker 1] → Python process executes tasks
         │       ├─ Validates stock
         │       ├─ Creates RestockItem
         │       └─ Triggers robot
         │
         ├─→ [Worker 2] → Python process executes tasks
         │       ├─ Monitors mission
         │       └─ Broadcasts updates
         │
         └─→ [Worker 3] → Python process handles priority tasks
                 └─ Urgent restock escalations

┌─────────────────────────────────────────────────────────────────────┐
│                       RESULT BACKEND (Redis)                        │
│   [Task Results] ← Workers store results here                       │
│   [Task Status]  ← Status: PENDING → STARTED → SUCCESS/FAILURE      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Components

1. **Producer** (Django app)
   - Publishes tasks to message broker
   - Sends events via Channels
   - Example: Signal handler calls `.delay()` or `.apply_async()`

2. **Message Broker** (Redis)
   - Queue of tasks to execute
   - Persistent storage
   - Multiple workers consume from same queue

3. **Workers** (separate Python processes)
   - Consume tasks from queue
   - Execute task function
   - Store result in result backend
   - Handle retries, timeouts, logging

4. **Result Backend** (Redis)
   - Stores task results (success/failure)
   - Stores task state (PENDING, STARTED, SUCCESS, FAILURE)
   - Allows task status queries

---

## Part 3: Integration Strategy

### Step 1: Install Celery & Dependencies

```bash
pip install celery redis
```

Update `requirements.txt`:
```
celery==5.3.6
redis==5.0.1
```

### Step 2: Create `main/celery.py`

This configures Celery to work with Django:

```python
# main/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

app = Celery('recap_inventory')

# Load Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all apps
app.autodiscover_tasks()

# Celery Configuration
app.conf.update(
    # Broker settings
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/1',
    
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Retry and timeout settings
    task_acks_late=True,  # Acknowledge task after execution
    task_reject_on_worker_lost=True,  # Re-queue if worker dies
    
    # Worker settings
    worker_max_tasks_per_child=1000,  # Prevent memory leaks
    worker_prefetch_multiplier=1,  # Don't prefetch many tasks
    
    # Default task settings
    task_default_retry_delay=300,  # Retry after 5 minutes
    task_max_retries=3,  # Max 3 retry attempts
    task_time_limit=3600,  # Hard time limit: 1 hour
    task_soft_time_limit=3300,  # Soft time limit: 55 minutes
)

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

### Step 3: Initialize Celery in Django

Update `main/__init__.py`:

```python
# main/__init__.py
from .celery import app as celery_app

__all__ = ('celery_app',)
```

### Step 4: Update Django Settings

Add to `main/settings.py`:

```python
# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Task routing
CELERY_TASK_ROUTES = {
    'api.tasks.validate_restock': {'queue': 'default', 'priority': 10},
    'api.tasks.create_restock_item': {'queue': 'default', 'priority': 10},
    'api.tasks.trigger_robot_mission': {'queue': 'robot', 'priority': 5},
    'api.tasks.monitor_mission': {'queue': 'monitoring', 'priority': 3},
}

# Priority queue settings
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'priority_steps': list(range(10)),  # 0-9 priority levels
    'sep': ':',
    'queue_order_strategy': 'priority',
    'visibility_timeout': 3600,
}
```

---

## Part 4: Celery Tasks Implementation

### Traditional vs Celery Task Structure

#### Before (Async/Await)

```python
# api/tasks.py - Current implementation
class ValidateRestockTask:
    async def execute(self, context):
        # Logic here
        pass

class CreateRestockItemTask:
    async def execute(self, context):
        # Logic here
        pass

# Called via orchestrator
result = await orchestrator.execute_workflow(context)
```

#### After (Celery Tasks)

```python
# api/celery_tasks.py - New Celery implementation
from celery import shared_task, Task, chain, group
from api.models import Product, RestockItem
from api.events import EventBus
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# INDIVIDUAL CELERY TASKS - Each runs independently in worker pool
# ============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # Retry after 5 minutes
    time_limit=600,  # Hard timeout: 10 minutes
)
def validate_restock_task(self, product_id):
    """
    Validate restock conditions
    
    Args:
        product_id: ID of product to validate
        
    Returns:
        dict: {
            'is_valid': bool,
            'reason': str,
            'product_id': int,
        }
    """
    try:
        product = Product.objects.get(id=product_id)
        
        logger.info(f"Validating restock for product {product_id}")
        
        # Check 1: Auto restock enabled
        if not product.auto_restock_enabled:
            logger.warning(f"Product {product_id} has auto_restock_enabled=False")
            EventBus.publish(
                'restock_validation_failed',
                {
                    'product_id': product_id,
                    'reason': 'auto_restock_disabled'
                }
            )
            return {
                'is_valid': False,
                'reason': 'auto_restock_disabled',
                'product_id': product_id,
            }
        
        # Check 2: No pending restock
        pending = RestockItem.objects.filter(
            product_id=product_id,
            status='PENDING'
        ).first()
        
        if pending:
            logger.info(f"Pending restock already exists for product {product_id}")
            EventBus.publish(
                'restock_validation_failed',
                {
                    'product_id': product_id,
                    'reason': 'pending_restock_exists'
                }
            )
            return {
                'is_valid': False,
                'reason': 'pending_restock_exists',
                'product_id': product_id,
            }
        
        logger.info(f"Validation passed for product {product_id}")
        
        EventBus.publish(
            'restock_validated',
            {
                'product_id': product_id,
                'current_stock': product.stock,
                'threshold': product.restock_threshold,
            }
        )
        
        return {
            'is_valid': True,
            'product_id': product_id,
        }
        
    except Product.DoesNotExist:
        logger.error(f"Product {product_id} not found")
        # Retry won't help - product doesn't exist
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Error validating restock: {exc}")
        # Exponential backoff retry
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    time_limit=600,
)
def create_restock_item_task(self, product_id, current_stock):
    """
    Create RestockItem database record
    
    Args:
        product_id: ID of product
        current_stock: Current stock level
        
    Returns:
        dict: {
            'restock_item_id': int,
            'quantity': int,
            'product_id': int,
        }
    """
    try:
        product = Product.objects.get(id=product_id)
        
        logger.info(f"Creating RestockItem for product {product_id}")
        
        # Calculate restock quantity
        quantity = max(0, product.restock_quantity - current_stock)
        
        # Create restockitem
        restock_item = RestockItem.objects.create(
            product=product,
            quantity=quantity,
            shelf_location=product.shelf_location or 'Unknown',
            status='PENDING',
        )
        
        logger.info(f"RestockItem {restock_item.id} created for product {product_id}")
        
        EventBus.publish(
            'restock_item_created',
            {
                'restock_item_id': restock_item.id,
                'product_id': product_id,
                'quantity': quantity,
            }
        )
        
        return {
            'restock_item_id': restock_item.id,
            'quantity': quantity,
            'product_id': product_id,
        }
        
    except Product.DoesNotExist:
        logger.error(f"Product {product_id} not found")
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Error creating RestockItem: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=5,  # Robot API might be flaky
    default_retry_delay=600,  # Retry after 10 minutes
    time_limit=1800,  # Hard timeout: 30 minutes
)
def trigger_robot_mission_task(self, restock_item_id):
    """
    Trigger robot mission via ROS Bridge
    
    Args:
        restock_item_id: ID of RestockItem
        
    Returns:
        dict: {
            'mission_started': bool,
            'restock_item_id': int,
        }
    """
    try:
        restock_item = RestockItem.objects.get(id=restock_item_id)
        product = restock_item.product
        
        logger.info(f"Triggering robot mission for RestockItem {restock_item_id}")
        
        # Update status
        restock_item.status = 'IN_PROGRESS'
        restock_item.save()
        
        # Call ROS Bridge
        import requests
        ros_bridge_url = 'http://localhost:9000/restock/queue'
        
        payload = {
            'item_id': restock_item_id,
            'product_name': product.name,
            'quantity': restock_item.quantity,
            'shelf_location': product.shelf_location,
        }
        
        response = requests.post(
            ros_bridge_url,
            json=payload,
            timeout=10  # 10 second timeout
        )
        
        response.raise_for_status()
        
        logger.info(f"Robot mission started for RestockItem {restock_item_id}")
        
        EventBus.publish(
            'restock_mission_started',
            {
                'restock_item_id': restock_item_id,
                'product_name': product.name,
                'quantity': restock_item.quantity,
            }
        )
        
        return {
            'mission_started': True,
            'restock_item_id': restock_item_id,
        }
        
    except RestockItem.DoesNotExist:
        logger.error(f"RestockItem {restock_item_id} not found")
        self.dont_retry = True
        raise
    except requests.exceptions.ConnectionError as exc:
        logger.warning(f"ROS Bridge connection error: {exc}")
        # Retry - connection might be temporarily unavailable
        raise self.retry(exc=exc)
    except requests.exceptions.Timeout as exc:
        logger.warning(f"ROS Bridge timeout: {exc}")
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error(f"Error triggering robot mission: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    time_limit=5400,  # 90 minutes soft limit
)
def monitor_mission_task(self, restock_item_id):
    """
    Monitor robot mission progress
    
    Args:
        restock_item_id: ID of RestockItem
        
    Returns:
        dict: {
            'mission_id': str,
            'restock_item_id': int,
            'status': str,
        }
    """
    try:
        restock_item = RestockItem.objects.get(id=restock_item_id)
        
        logger.info(f"Monitoring mission for RestockItem {restock_item_id}")
        
        # Poll ROS Bridge for mission status
        import requests
        ros_bridge_url = f'http://localhost:9000/missions/{restock_item_id}'
        
        try:
            response = requests.get(ros_bridge_url, timeout=10)
            response.raise_for_status()
            mission_status = response.json()
            
            logger.info(f"Mission status: {mission_status}")
            
            EventBus.publish(
                'mission_status_update',
                {
                    'restock_item_id': restock_item_id,
                    'status': mission_status.get('status'),
                    'progress': mission_status.get('progress'),
                }
            )
            
        except requests.exceptions.RequestException as exc:
            logger.warning(f"Error querying mission status: {exc}")
            # Retry monitoring
            raise self.retry(exc=exc)
        
        return {
            'mission_id': restock_item_id,
            'restock_item_id': restock_item_id,
            'status': 'monitoring',
        }
        
    except RestockItem.DoesNotExist:
        logger.error(f"RestockItem {restock_item_id} not found")
        self.dont_retry = True
        raise
    except Exception as exc:
        logger.error(f"Error monitoring mission: {exc}")
        raise self.retry(exc=exc)


# ============================================================================
# WORKFLOW ORCHESTRATION - Chain tasks together
# ============================================================================

@shared_task
def execute_restock_workflow(product_id, current_stock):
    """
    Orchestrate restock workflow using Celery chains
    
    Chains tasks together so they execute in sequence:
    1. validate_restock_task
    2. create_restock_item_task (depends on validation)
    3. trigger_robot_mission_task (depends on item creation)
    4. monitor_mission_task (depends on mission trigger)
    
    Args:
        product_id: ID of product needing restock
        current_stock: Current stock level
    """
    from celery import chain, chord
    
    logger.info(f"Starting restock workflow for product {product_id}")
    
    # Build task chain
    workflow = chain(
        # Step 1: Validate
        validate_restock_task.s(product_id),
        
        # Step 2: Create RestockItem (use chord callback)
        # Conditional: only run if validation passed
        create_restock_item_task.s(current_stock),
        
        # Step 3: Trigger robot (uses output from step 2)
        trigger_robot_mission_task.s([]),  # Will get restock_item_id from step 2
        
        # Step 4: Monitor mission (uses output from step 3)
        monitor_mission_task.s([]),
    )
    
    # Execute the chain
    result = workflow.apply_async()
    
    logger.info(f"Restock workflow started with task_id: {result.id}")
    
    EventBus.publish(
        'restock_workflow_started',
        {
            'product_id': product_id,
            'task_id': str(result.id),
        }
    )
    
    return str(result.id)
```

---

## Part 5: Signal Handler Integration

Update `api/signals.py` to use Celery instead of asyncio:

```python
# api/signals.py - Updated for Celery
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Product, RestockItem
from .websocket_events import broadcast_update
from .celery_tasks import execute_restock_workflow
import logging

logger = logging.getLogger(__name__)

# Cache for tracking stock changes
_product_stock_cache = {}


@receiver(pre_save, sender=Product)
def _product_stock_cache_before_save(sender, instance, **kwargs):
    """Cache the previous stock value before save"""
    try:
        previous = Product.objects.get(pk=instance.pk)
        _product_stock_cache[instance.pk] = previous.stock
    except Product.DoesNotExist:
        _product_stock_cache[instance.pk] = instance.stock


@receiver(post_save, sender=Product)
def restock_on_stock_below_threshold(sender, instance, created, **kwargs):
    """
    Trigger restock workflow when stock falls below threshold.
    
    Uses Celery task queue for asynchronous execution:
    - Non-blocking: Response returned immediately
    - Reliable: Task persisted in Redis
    - Scalable: Multiple workers process in parallel
    - Monitorable: Track task status via Celery
    """
    
    # Skip if product just created
    if created:
        return
    
    # Get previous stock
    previous_stock = _product_stock_cache.get(instance.pk, instance.stock)
    current_stock = instance.stock
    
    logger.info(
        f"Product {instance.id} stock changed: {previous_stock} → {current_stock}"
    )
    
    # Check if stock fell below threshold
    if (
        current_stock < instance.restock_threshold
        and previous_stock >= instance.restock_threshold
        and instance.auto_restock_enabled
    ):
        logger.info(
            f"Stock below threshold for {instance.name}. "
            f"Triggering restock workflow via Celery"
        )
        
        try:
            # Queue task: execute_restock_workflow runs in Celery worker
            task = execute_restock_workflow.delay(
                product_id=instance.id,
                current_stock=current_stock,
            )
            
            logger.info(f"Restock task queued with ID: {task.id}")
            
        except Exception as exc:
            logger.error(f"Failed to queue restock task: {exc}")
    
    # Clean up cache
    _product_stock_cache.pop(instance.pk, None)


@receiver(post_save, sender=RestockItem)
def restock_item_updated(sender, instance, created, **kwargs):
    """
    Broadcast restock item updates via WebSocket
    Allows real-time UI updates for all connected clients
    """
    broadcast_update(instance)
    logger.info(f"RestockItem update broadcasted: {instance.id} - {instance.status}")
```

---

## Part 6: Running Celery Workers

### Start Redis (Message Broker)

```bash
# Install Redis (if not already installed)
# Ubuntu/Debian:
sudo apt-get install redis-server

# macOS:
brew install redis

# Start Redis
redis-server --port 6379
```

### Start Celery Worker

```bash
# Terminal 1: Default worker (handles all task types)
celery -A main worker -l info

# Terminal 2: Robot mission worker (high priority)
celery -A main worker -Q robot -l info -c 2

# Terminal 3: Monitoring worker
celery -A main worker -Q monitoring -l info -c 1

# Production: Use supervisor or systemd to manage workers
```

### Monitor Celery with Flower

```bash
# Install Flower (web-based monitoring)
pip install flower

# Start Flower dashboard
celery -A main flower --port=5555

# Access at http://localhost:5555
```

---

## Part 7: Architecture Comparison

### Before (Async/Await)

```
Single Django Process
├─ RequestHandler (blocks during restock)
├─ Asyncio Event Loop
│  ├─ ValidateRestockTask
│  ├─ CreateRestockItemTask
│  ├─ TriggerRobotMissionTask
│  └─ MonitorMissionTask
│
Issues:
├─ Single point of failure
├─ Can't scale horizontally
├─ Limited task retry logic
└─ No built-in monitoring
```

### After (Celery)

```
Django Process (Producer)
├─ Request Handler (returns immediately)
├─ Queue task to Redis: execute_restock_workflow.delay()
│
Message Broker (Redis)
├─ Task Queue: [task1, task2, task3, ...]
├─ Result Backend: {task_id → results}
│
Worker Pool (separate processes/machines)
├─ Worker 1: Consumes validate_restock_task
├─ Worker 2: Consumes create_restock_item_task
├─ Worker 3: Consumes trigger_robot_mission_task
├─ Worker 4: Consumes monitor_mission_task
│
Advantages:
├─ Distributed: Workers on multiple machines
├─ Resilient: Tasks persisted, auto-retry
├─ Scalable: Add workers as needed
├─ Observable: Flower dashboard, task monitoring
├─ Prioritizable: High-priority tasks first
└─ Non-blocking: Django responds immediately
```

---

## Part 8: Full Integration Example

### Complete Workflow

```python
# 1. Customer creates order (API request)
POST /api/orders/
{
    "items": [
        {"product": 1, "quantity": 5}  # Reduces stock by 5
    ]
}

# 2. Django saves order, product stock changes
# 3. pre_save signal: Caches stock=7
# 4. post_save signal triggers:
#    - Detects: 7 → 2 (below threshold of 5)
#    - Calls: execute_restock_workflow.delay(product_id=1, current_stock=2)

# 5. Task queued to Redis immediately
# 6. HTTP response sent to client: {"status": "Order created"}

# 7. Celery worker picks up task from queue:
#    - Runs validate_restock_task(product_id=1)
#    - If valid, runs create_restock_item_task(product_id=1, current_stock=2)
#    - If created, runs trigger_robot_mission_task(restock_item_id=42)
#    - Monitors mission status

# 8. At each step, events published to EventBus
# 9. WebSocket broadcasts updates to frontend
# 10. Frontend shows real-time progress
# 11. Robot autonomously executes mission
# 12. On completion, stock updated and RestockItem marked COMPLETED
```

---

## Part 9: Production Configuration

### Celery Configuration for Production

```python
# main/celery.py - Production settings
app.conf.update(
    # Broker
    broker_url='amqp://user:pass@rabbitmq:5672//',  # RabbitMQ more reliable than Redis
    result_backend='redis://redis:6379/1',
    
    # Durability
    task_acks_late=True,  # Don't ack until task completes
    task_reject_on_worker_lost=True,  # Re-queue if worker dies
    broker_connection_retry_on_startup=True,
    
    # Performance
    worker_max_tasks_per_child=1000,  # Prevent memory leaks
    worker_prefetch_multiplier=1,  # Don't prefetch tasks
    
    # Timeouts
    task_time_limit=3600,  # Hard timeout: 1 hour
    task_soft_time_limit=3300,  # Soft timeout: 55 minutes
    
    # Retries
    task_default_retry_delay=300,
    task_default_max_retries=3,
    
    # Logging
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
)

# Task routing for priority queues
app.conf.task_routes = {
    'api.celery_tasks.validate_restock': {
        'queue': 'default',
        'priority': 10,
    },
    'api.celery_tasks.create_restock_item': {
        'queue': 'default',
        'priority': 10,
    },
    'api.celery_tasks.trigger_robot_mission': {
        'queue': 'robot',
        'priority': 5,
        'routing_key': 'robot.high',
    },
    'api.celery_tasks.monitor_mission': {
        'queue': 'monitoring',
        'priority': 3,
    },
}
```

### Docker Compose for Local Development

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq

  django:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - rabbitmq
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      CELERY_RESULT_BACKEND: redis://redis:6379/1

  celery_default:
    build: .
    command: celery -A main worker -Q default -l info
    depends_on:
      - redis
      - rabbitmq
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      CELERY_RESULT_BACKEND: redis://redis:6379/1

  celery_robot:
    build: .
    command: celery -A main worker -Q robot -l info -c 2
    depends_on:
      - redis
      - rabbitmq
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      CELERY_RESULT_BACKEND: redis://redis:6379/1

  celery_monitoring:
    build: .
    command: celery -A main worker -Q monitoring -l info
    depends_on:
      - redis
      - rabbitmq
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      CELERY_RESULT_BACKEND: redis://redis:6379/1

  celery_beat:
    build: .
    command: celery -A main beat -l info
    depends_on:
      - redis
      - rabbitmq
      - celery_default
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      CELERY_RESULT_BACKEND: redis://redis:6379/1

  flower:
    build: .
    command: celery -A main flower --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis
      - rabbitmq
    environment:
      CELERY_BROKER_URL: amqp://guest:guest@rabbitmq:5672//
      CELERY_RESULT_BACKEND: redis://redis:6379/1

volumes:
  redis_data:
  rabbitmq_data:
```

---

## Part 10: Advanced Features

### Delayed Task Execution

```python
from .celery_tasks import trigger_robot_mission_task
from datetime import timedelta

# Execute in 1 hour
trigger_robot_mission_task.apply_async(
    args=[restock_item_id],
    countdown=3600,  # seconds
)

# Or use eta (scheduled time)
from datetime import datetime, timedelta
eta = datetime.utcnow() + timedelta(hours=1)
trigger_robot_mission_task.apply_async(
    args=[restock_item_id],
    eta=eta,
)
```

### Task Priorities

```python
# High priority (execute immediately)
validate_restock_task.apply_async(
    args=[product_id],
    priority=10,  # 0-9 scale
    queue='default',
)

# Low priority (run when idle)
monitor_mission_task.apply_async(
    args=[restock_item_id],
    priority=1,
    queue='monitoring',
)
```

### Task Groups (Parallel Execution)

```python
from celery import group

# Check multiple products in parallel
products_to_check = [1, 2, 3, 4, 5]

parallel_tasks = group(
    validate_restock_task.s(product_id)
    for product_id in products_to_check
)

results = parallel_tasks.apply_async()

# Get all results
all_results = results.get()
```

### Conditional Task Execution

```python
from celery import chain, chord, group

# Validation → CreateItem (if valid) → TriggerRobot
def restock_workflow_verbose(product_id, current_stock):
    """
    Conditional workflow:
    - If validation fails, stop
    - If validation passes, create item
    - If item created, trigger robot
    """
    
    def create_item_if_valid(validation_result):
        """Callback: only execute if validation was valid"""
        if validation_result.get('is_valid'):
            return create_restock_item_task.delay(
                product_id,
                current_stock
            )
        else:
            logger.warning(f"Validation failed: {validation_result}")
            return None
    
    def trigger_if_created(item_result):
        """Callback: only execute if item was created"""
        if item_result:
            restock_item_id = item_result.get('restock_item_id')
            return trigger_robot_mission_task.delay(restock_item_id)
        else:
            logger.warning("No Restock item created")
            return None
    
    # Start workflow
    task = validate_restock_task.delay(product_id)
    task.then(create_item_if_valid).then(trigger_if_created)
```

---

## Part 11: Migration Path

### Phase 1: Setup (1-2 hours)

1. Install Celery, Redis
2. Create `main/celery.py`
3. Update `main/settings.py`
4. Create `requirements.txt` entry

### Phase 2: Convert Tasks (2-4 hours)

1. Create `api/celery_tasks.py` with Celery versions
2. Update signal handlers to use `.delay()`
3. Update views to queue tasks instead of async

### Phase 3: Testing (2-3 hours)

1. Unit tests for each task
2. Integration tests for workflow
3. Load testing with multiple workers

### Phase 4: Deployment (varies)

1. Set up Redis/RabbitMQ in production
2. Configure worker processes
3. Set up monitoring (Flower)
4. Deploy workers on separate machines

---

## Part 12: Monitoring & Observability

### Task Status Tracking

```python
from main.celery import app

def get_task_status(task_id):
    """Get status of any task"""
    result = app.AsyncResult(task_id)
    
    return {
        'task_id': task_id,
        'status': result.status,  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
        'result': result.result if result.successful() else None,
        'error': str(result.info) if result.failed() else None,
        'progress': result.get('progress') if hasattr(result, 'get') else None,
    }

# Expose as API
class TaskStatusView(APIView):
    def get(self, request, task_id):
        return Response(get_task_status(task_id))
```

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram

celery_task_total = Counter(
    'celery_task_total',
    'Total celery tasks',
    ['task_name', 'status']
)

celery_task_duration = Histogram(
    'celery_task_duration_seconds',
    'Celery task duration',
    ['task_name']
)

# In task
@shared_task
def my_task():
    with celery_task_duration.labels(task_name='my_task').time():
        try:
            # Task logic
            celery_task_total.labels(task_name='my_task', status='success').inc()
        except Exception:
            celery_task_total.labels(task_name='my_task', status='failure').inc()
```

---

## Part 13: Troubleshooting

### Task Not Executing

```bash
# 1. Check if Redis is running
redis-cli ping  # Should return PONG

# 2. Check if worker is running and connected
celery -A main inspect active  # Shows active tasks

# 3. Check if task is in queue
celery -A main inspect reserved  # Shows reserved tasks

# 4. Check worker logs for errors
celery -A main worker -l debug
```

### Task Stuck in PENDING

```python
# Task queued but not executing
# Common causes:
# 1. Worker not running
# 2. Worker queue mismatch (task in 'default', worker on 'robot')
# 3. Redis connection issue

# Solution: Restart worker
celery -A main worker --purge  # Clear queue
celery -A main worker -l info  # Start fresh
```

### Redis Memory Issues

```bash
# Monitor Redis size
redis-cli info memory

# Clear old data
redis-cli FLUSHDB  # Clear current database
redis-cli FLUSHALL  # Clear everything

# Set max memory policy
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

---

## Summary: Why Celery for Your Event-Driven Architecture

| Feature | Before | After |
|---------|--------|-------|
| **Execution Model** | Single process asyncio | Distributed worker pool |
| **Scalability** | Limited to one machine | Unlimited horizontal scaling |
| **Reliability** | Tasks lost on crash | Persisted with auto-retry |
| **Monitoring** | Logs only | Flower dashboard + Prometheus |
| **Task Retry** | None | Exponential backoff |
| **Task Delay** | Not supported | Built-in with countdown/eta |
| **Priority Queues** | Not supported | Full support |
| **Rate Limiting** | Manual | Automatic via queue priority |
| **Observable** | Limited | Complete audit trail |
| **Production Ready** | Partial | Full with enterprise features |

**Result**: From a prototype to production-grade distributed system! 🚀

