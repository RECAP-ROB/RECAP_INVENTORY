"""
QUICK REFERENCE: Event-Driven Restock Architecture

This file provides quick reference for developers working with the system.
"""

# ============================================================================
# IMPORT CHEATSHEET
# ============================================================================

# Get Orchestrator (Singleton):
from api.orchestrator import get_orchestrator
orchestrator = get_orchestrator()

# Use EventBus to publish events:
from api.events import EventBus, StockBelowThresholdEvent
event = StockBelowThresholdEvent(product_id=1, current_stock=3, threshold=5)
EventBus.publish(event)

# Access Tasks (for testing):
from api.tasks import ValidateRestockTask, CreateRestockItemTask, TriggerRobotMissionTask, MonitorMissionTask

# Models:
from api.models import Product, RestockItem


# ============================================================================
# PRODUCT MODEL - NEW FIELDS
# ============================================================================

# All products now have:
product.restock_threshold       # int (default: 5)
product.restock_quantity        # int (default: 10)
product.auto_restock_enabled    # bool (default: True)

# Before:
# coffee.stock = 7

# After stock reduction (via order):
# coffee.stock = 2
# → Trigger: stock(2) < threshold(5) AND auto_restock_enabled = True
# → Signal automatically calls orchestrator


# ============================================================================
# EVENT TYPES (Published to Redis)
# ============================================================================

"""
Event publishing flow:

1. StockBelowThresholdEvent
   Trigger: Product.stock drops below threshold
   Handler: Signal handler → Calls orchestrator
   
2. RestockValidatedEvent / RestockValidationFailedEvent
   Trigger: ValidateRestockTask completes
   Use: Frontend/logging to track validation status
   
3. RestockItemCreatedEvent
   Trigger: CreateRestockItemTask completes
   Data: Includes restock_item_id, product_id, quantity
   
4. RestockMissionStartedEvent
   Trigger: TriggerRobotMissionTask successfully calls ROS Bridge
   Data: Includes product_name, shelf_location
   
5. RestockMissionFailedEvent
   Trigger: Robot trigger failed
   Data: Includes reason for failure
   
6. RestockWorkflowCompletedEvent
   Trigger: Entire workflow finished
   Data: success (bool), details (string)
"""


# ============================================================================
# TASK SEQUENCE
# ============================================================================

"""
Task execution order (automatically sequenced by orchestrator):

[1] ValidateRestockTask
    ├─ Input: {product_id, current_stock, threshold}
    ├─ Checks:
    │  ├─ product.auto_restock_enabled == True
    │  ├─ no RestockItem with status=PENDING exists
    │  └─ product exists in database
    ├─ Output: {is_valid, reason, product}
    └─ On failure: stops workflow

[2] CreateRestockItemTask  
    ├─ Input: {product}
    ├─ Calculates: qty = restock_quantity - current_stock
    ├─ Creates: RestockItem(status=PENDING)
    ├─ Output: {restock_item_id, restock_item}
    └─ DB change: ++1 RestockItem

[3] TriggerRobotMissionTask
    ├─ Input: {restock_item}
    ├─ Actions:
    │  ├─ Update RestockItem.status = IN_PROGRESS
    │  ├─ POST /restock/queue → ROS Bridge
    │  └─ Publish RestockMissionStartedEvent
    ├─ Output: {robot_mission_id, mission_sent}
    └─ On failure: sets status = FAILED

[4] MonitorMissionTask
    ├─ Input: {restock_item_id}
    ├─ Action: Returns immediately
    ├─ Monitoring: Continues via WebSocket
    └─ Output: {monitoring_started}

After Tasks Complete:
└─ Publish RestockWorkflowCompletedEvent
```


# ============================================================================
# COMMON WORKFLOWS
# ============================================================================

# Get a product with restock config:
from api.models import Product
coffee = Product.objects.get(name="Coffee")
print(f"Threshold: {coffee.restock_threshold}")
print(f"Target Stock: {coffee.restock_quantity}")
print(f"Auto Enabled: {coffee.auto_restock_enabled}")

# Disable auto-restock for a product:
product.auto_restock_enabled = False
product.save()
# → Orchestrator will skip this product even if stock drops

# Create restock item manually (for testing):
from api.models import RestockItem
restock = RestockItem.objects.create(
    product=product,
    quantity=5,
    shelf_location="SHELF_A1",
    status=RestockItem.Status.PENDING
)

# Check restock items in queue:
from api.models import RestockItem
pending = RestockItem.objects.filter(status=RestockItem.Status.PENDING)
for item in pending:
    print(f"{item.product.name}: {item.quantity} units to {item.shelf_location}")

# Update restock status manually (simulate robot completion):
restock.status = RestockItem.Status.IN_PROGRESS
restock.save()
# → Broadcasts update via WebSocket

restock.status = RestockItem.Status.COMPLETED
restock.save()
product.stock += restock.quantity  # Admin manually adds stock
product.save()

# Get orchestrator execution report:
from api.orchestrator import get_orchestrator
orchestrator = get_orchestrator()
report = orchestrator.get_execution_report()
print(f"Completed tasks: {report['completed_tasks']}")
print(f"Failed tasks: {report['failed_tasks']}")
print(f"History: {report['history']}")


# ============================================================================
# ASYNC OPERATIONS
# ============================================================================

"""
The orchestrator runs asynchronously:

from api.orchestrator import get_orchestrator
import asyncio

orchestrator = get_orchestrator()
context = {
    'product_id': 1,
    'current_stock': 3,
    'threshold': 5
}

# In Django signal handler (auto):
asyncio.run(orchestrator.execute_workflow(context))

# Or from CLI:
asyncio.run(orchestrator.execute_workflow(context))

# Result: Workflow executes all 4 tasks
# Returns: {workflow_status, execution_history, ...}
"""


# ============================================================================
# TESTING
# ============================================================================

# Run all tests:
# python manage.py test api.test_orchestrator -v 2

# Run specific test class:
# python manage.py test api.test_orchestrator.EventTestCase

# Run specific test:
# python manage.py test api.test_orchestrator.EventTestCase.test_stock_below_threshold_event


# ============================================================================
# LOGGING
# ============================================================================

"""
Logger: 'api.orchestrator', 'api.tasks', 'api.signals'

Log messages show workflow progress:

🚀 Starting restock workflow for product 1
[1/4] Executing task: validate
✅ Task 'validate' completed with status: completed
[2/4] Executing task: create
✅ RestockItem created: id=42, qty=8
[3/4] Executing task: trigger_robot
✅ Task 'trigger_robot' completed with status: completed
[4/4] Executing task: monitor
✅ Workflow completed successfully for product 1

On failure:
⚠️  Validation failed: Auto restock disabled for product
⚠️  Workflow failed for product 1
"""


# ============================================================================
# DATABASE SCHEMA
# ============================================================================

"""
Product Model (after migration 0007):
├─ id (PrimaryKey)
├─ name
├─ description
├─ price
├─ stock
├─ shelf_location
├─ image
├─ restock_threshold (NEW)       ← Trigger point
├─ restock_quantity (NEW)        ← Target stock
└─ auto_restock_enabled (NEW)    ← Enable/disable

RestockItem Model (unchanged):
├─ id
├─ product_id (FK)
├─ quantity
├─ status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
├─ shelf_location
├─ created_at
└─ updated_at
"""


# ============================================================================
# REST API ENDPOINTS AFFECTED
# ============================================================================

"""
GET /api/products/
GET /api/products/{id}/
PATCH /api/products/{id}/
    ├─ Returns new fields: restock_threshold, restock_quantity, auto_restock_enabled
    └─ Can update these fields

POST /api/orders/
    └─ Creating an order reduces product.stock
        └─ Triggers orchestrator if stock < threshold

GET /api/restock/queue/
    └─ Returns RestockItems created by orchestrator

POST /api/restock/{id}/
    └─ Manually update RestockItem status (admin only)
"""


# ============================================================================
# EVENT CHANNELS (Redis)
# ============================================================================

"""
Events published to Redis channel: "events"

Subscribe to events in real-time:
$ redis-cli
> SUBSCRIBE events

Example event message:
{
  "type": "event.dispatch",
  "event": {
    "event_type": "stock.below_threshold",
    "timestamp": "2026-04-01T12:34:56.789123",
    "data": {
      "product_id": 1,
      "current_stock": 2,
      "threshold": 5
    }
  }
}
"""


# ============================================================================
# PERFORMANCE NOTES
# ============================================================================

"""
Async Operations:
- Orchestrator runs asynchronously (non-blocking)
- UI remains responsive during restock workflow
- Multiple products can restock simultaneously

Database:
- Signal handler uses pre_save/post_save hooks
- Minimal database impact (only on product stock changes)
- RestockItem creation is atomic (transaction.atomic)

Redis/Events:
- Event publishing is fire-and-forget
- Failures in event publishing don't crash workflow
- Subscribers receive updates in real-time

Robot Communication:
- aiohttp with 10-second timeout to ROS Bridge
- On timeout: RestockItem marked FAILED, logged, event published
- Synchronous exception in ROS Bridge doesn't break workflow
"""


# ============================================================================
# FUTURE EXTENSIBILITY
# ============================================================================

"""
To add new events:
1. Create class in api/events.py extending Event
2. Publish via EventBus.publish(event)
3. Subscribers automatically receive

To add new tasks:
1. Create class in api/tasks.py extending Task
2. Implement async execute() method
3. Add to RestockOrchestrator.tasks list

To add new task types:
1. Create conditional branching in orchestrator.execute_workflow()
2. Execute alternative task sequences based on conditions
3. Example: Different tasks for different product types

To add persistence:
1. Create WorkflowExecution model
2. Save context to database in orchestrator
3. Enable workflow resumption after failures
"""
