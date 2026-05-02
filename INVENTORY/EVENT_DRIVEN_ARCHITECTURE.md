"""
EVENT-DRIVEN RESTOCK ORCHESTRATION ARCHITECTURE

This document explains how automatic robot restock triggering works through
an event-driven architecture with task orchestration.

================================================================================
ARCHITECTURE OVERVIEW
================================================================================

The system follows a reactive, event-driven design:

    ┌────────────────────────────────────────────────────────────────┐
    │  CREATE ORDER (Product Stock Decreases)                        │
    │  ↓                                                             │
    │  Signal Handler (pre_save) → Cache Stock                       │
    │  ↓                                                             │
    │  Signal Handler (post_save) → Detect Stock < Threshold        │
    │  ↓                                                             │
    │  Event: StockBelowThresholdEvent Published                    │
    │  ↓                                                             │
    │  ┌─ ORCHESTRATOR WORKFLOW ──────────────────────────────────┐ │
    │  │                                                           │ │
    │  │  Task 1: ValidateRestockTask                             │ │
    │  │  ├─ Check auto_restock_enabled                           │ │
    │  │  ├─ Check for existing pending restock                   │ │
    │  │  └─ Publish RestockValidatedEvent                        │ │
    │  │      ↓                                                    │ │
    │  │  Task 2: CreateRestockItemTask                           │ │
    │  │  ├─ Calculate restock quantity                           │ │
    │  │  ├─ Create RestockItem in database                       │ │
    │  │  └─ Publish RestockItemCreatedEvent                      │ │
    │  │      ↓                                                    │ │
    │  │  Task 3: TriggerRobotMissionTask                         │ │
    │  │  ├─ Update RestockItem status to IN_PROGRESS             │ │
    │  │  ├─ Call ROS Bridge API                                  │ │
    │  │  └─ Publish RestockMissionStartedEvent                   │ │
    │  │      ↓                                                    │ │
    │  │  Task 4: MonitorMissionTask                              │ │
    │  │  └─ Return (WebSocket monitors progress)                 │ │
    │  │                                                           │ │
    │  │  On Completion:                                           │ │
    │  │  └─ Publish RestockWorkflowCompletedEvent                │ │
    │  │                                                           │ │
    │  └───────────────────────────────────────────────────────────┘ │
    │      ↓                                                           │
    │  Broadcast via Channels → Frontend Updates                      │
    │                                                                 │
    └────────────────────────────────────────────────────────────────┘

================================================================================
KEY COMPONENTS
================================================================================

1. EVENTS (api/events.py)
   - Domain events representing state changes
   - Published to Redis using Django Channels
   - Enable loose coupling between components
   
   Events:
   • StockBelowThresholdEvent - Triggers workflow start
   • RestockValidatedEvent - Validation passed
   • RestockValidationFailedEvent - Validation failed
   • RestockItemCreatedEvent - DB record created
   • RestockMissionStartedEvent - Robot triggered
   • RestockMissionFailedEvent - Robot trigger failed
   • RestockWorkflowCompletedEvent - Workflow finished

2. TASKS (api/tasks.py)
   - Individual, composable workflow steps
   - Each task is independently testable
   - Async/await compatible
   
   Tasks:
   • ValidateRestockTask - Verify conditions
   • CreateRestockItemTask - Create DB record
   • TriggerRobotMissionTask - Call ROS Bridge
   • MonitorMissionTask - Async progress monitoring

3. ORCHESTRATOR (api/orchestrator.py)
   - Composes tasks into coordinated workflow
   - Handles task sequencing and error handling
   - Maintains execution history
   - Global singleton instance via get_orchestrator()

4. SIGNAL HANDLERS (api/signals.py)
   - Django signals trigger on model changes
   - pre_save: Cache previous stock value
   - post_save: Detect stock changes, trigger orchestrator

5. EVENT BUS (events.EventBus)
   - Central event publisher
   - Uses Redis/Channels for distribution
   - Enables real-time updates via WebSocket

================================================================================
HOW IT WORKS: STEP BY STEP
================================================================================

SCENARIO: Customer purchases 5 units of Product say "Detergent"
- Before: Detergent has 7 units, threshold is 5
- After: Detergent has 2 units (below threshold)

1. ORDER CREATION
   create(validated_data)
   └─ product.stock -= 5  # 7 → 2
   └─ product.save()

2. SIGNAL DETECTION
   @ pre_save(Product)
   └─ _product_stock_cache[detergent_id] = 7
   
   @ post_save(Product)
   └─ previous_stock = 7
   └─ current_stock = 2
   └─ 2 < 5 (threshold)
   └─ auto_restock_enabled = True
   └─ EVENT: StockBelowThresholdEvent published

3. ORCHESTRATOR TRIGGERED
   orchestrator.execute_workflow({
       'product_id': detergent_id,
       'current_stock': 2,
       'threshold': 5,
   })

4. WORKFLOW EXECUTION
   
   Task 1: ValidateRestockTask
   ├─ Check auto_restock_enabled: ✅ True
   ├─ Check existing pending: ✅ None
   ├─ EVENT: RestockValidatedEvent published
   └─ context['is_valid'] = True
   
   Task 2: CreateRestockItemTask
   ├─ Calculate: restock_quantity(10) - current_stock(2) = 8
   ├─ Create: RestockItem(quantity=8, status=PENDING)
   ├─ EVENT: RestockItemCreatedEvent published
   └─ context['restock_item_id'] = 42
   
   Task 3: TriggerRobotMissionTask
   ├─ Update: RestockItem.status = IN_PROGRESS
   ├─ Send: POST /restock/queue to ROS Bridge
   │  Payload: {
   │    "item_id": 42,
   │    "product_name": "Detergent",
   │    "quantity": 8,
   │    "shelf_location": "SHELF_A1"
   │  }
   ├─ EVENT: RestockMissionStartedEvent published
   └─ Robot receives mission and starts pickup/delivery
   
   Task 4: MonitorMissionTask
   ├─ Returns immediately
   └─ WebSocket connection monitors robot progress
   
   On ROS Bridge feedback (robot completes):
   ├─ RestockItem.status = COMPLETED
   ├─ Product.stock += 8  # 2 → 10
   ├─ EVENT: RestockWorkflowCompletedEvent published
   └─ Frontend updates real-time via WebSocket

5. FRONTEND UPDATES
   User sees:
   - RestockItem appears in queue with status "IN_PROGRESS"
   - Robot status in dashboard
   - Real-time progress updates
   - Final completion status

================================================================================
CONFIGURATION
================================================================================

Product Model Fields:

  restock_threshold (default: 5)
  └─ When stock falls below this, restock is triggered
  
  restock_quantity (default: 10)
  └─ Target stock level after successful restock
  └─ Restock quantity = restock_quantity - current_stock
  
  auto_restock_enabled (default: True)
  └─ Enable/disable automatic restock for this product
  └─ Can be toggled in admin or via API

Example API to update Product:
  PATCH /api/products/123/
  {
    "restock_threshold": 3,
    "restock_quantity": 15,
    "auto_restock_enabled": false
  }

================================================================================
ERROR HANDLING & RESILIENCE
================================================================================

Graceful Degradation:

1. Validation Failure
   ├─ RestockValidationFailedEvent published
   ├─ Workflow stops early (no database pollution)
   └─ Admin can check event log to debug

2. Robot Connection Failure
   ├─ RestockItem.status = FAILED
   ├─ RestockMissionFailedEvent published
   ├─ Workflow stops
   └─ Admin manually triggers retry

3. Database Transaction Failure
   ├─ Logged to orchestrator.error
   ├─ RestockWorkflowCompletedEvent published (success=False)
   ├─ System continues operating
   └─ Partial state reverted by transaction.atomic()

4. Event Publishing Failure
   ├─ Logged but doesn't crash workflow
   ├─ Workflow proceeds normally
   ├─ Clients may miss real-time updates
   └─ Status still queryable via API

================================================================================
TESTING THE WORKFLOW
================================================================================

Test in Django Shell:

```python
from api.models import Product, RestockItem
from api.orchestrator import get_orchestrator
import asyncio

# Create a test product
product = Product.objects.create(
    name="Test Coffee",
    description="Test",
    price=9.99,
    stock=7,
    restock_threshold=5,
    restock_quantity=10,
    auto_restock_enabled=True,
    shelf_location="TEST_SHELF"
)

# Simulate stock reduction (which would trigger event)
product.stock = 2
product.save()  # ← This triggers the signal and orchestrator

# Check created RestockItem
restock = RestockItem.objects.filter(product=product).first()
print(f"RestockItem created: {restock}")
print(f"Status: {restock.status}")
print(f"Quantity: {restock.quantity}")
```

Monitor Logs:

```bash
# Terminal 1: Watch Django logs
python manage.py runserver

# Terminal 2: Make API request
curl -X POST http://localhost:8000/api/orders/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "items": [
      {"product": 1, "quantity": 5}
    ]
  }'

# Check logs for:
# ✅ All modules imported successfully
# 🚀 Starting restock workflow for product 1
# ✅ Task 'validate' completed
# ✅ Task 'create' completed
# ✅ Task 'trigger_robot' completed
# ✅ Workflow completed successfully
```

Check Events:

```python
from api.events import EventBus
from channels.layers import get_channel_layer
import asyncio

# Events are published to Redis, received by WebSocket clients
# Monitor in real-time via /ws/restock WebSocket endpoint
```

================================================================================
ADVANTAGES OF THIS ARCHITECTURE
================================================================================

✅ Decoupled: Stock logic ≠ Restock logic ≠ Robot trigger
✅ Scalable: Easy to add new tasks or events
✅ Testable: Each component can be tested independently
✅ Resilient: Failures don't cascade
✅ Observable: Event trail for debugging and monitoring
✅ Asynchronous: Non-blocking, responsive UI
✅ Maintainable: Clear separation of concerns
✅ Extensible: Add new events/tasks without changing core
✅ Event-sourced: Full audit trail of all state changes

================================================================================
FUTURE ENHANCEMENTS
================================================================================

1. Celery Integration
   └─ Replace asyncio with Celery for distributed task queue
   └─ Better reliability and retry logic
   └─ Multi-worker scaling

2. Workflow Persistence
   └─ Save workflow state to database
   └─ Resume interrupted workflows

3. Event Replay
   └─ Rebuild state by replaying events
   └─ Temporal debugging

4. Advanced Monitoring
   └─ Prometheus metrics for events/tasks
   └─ Dashboard showing workflow metrics

5. Conditional Workflows
   └─ Alternative task paths based on conditions
   └─ Complex restock strategies

================================================================================
"""
