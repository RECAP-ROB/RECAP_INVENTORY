# RECAP_INVENTORY

RECAP_INVENTORY is a full-stack inventory management system designed to automate restocking for physical products using sensor-driven monitoring, task orchestration, and robot mission execution.

## Core functionality

- Tracks product inventory and stock levels in a Django backend.
- Automatically creates restock requests when products fall below configured thresholds.
- Uses MQTT camera alerts to detect shelf blockage and incorrect items during restocking.
- Orchestrates asynchronous restock workflow with Celery tasks.
- Publishes real-time queue and event updates over WebSockets to the React frontend.
- Integrates with a ROS 2 robot bridge to dispatch robot missions for replenishing shelves.
- Supports manual order and restock queue review through REST API endpoints.

## System components

- `api/`: Django app containing models, serializers, views, MQTT listener, and Celery task logic.
- `main/`: Django project settings, ASGI/WGI configuration, and Celery integration.
- `frontend/`: React + TypeScript UI for dashboard, order views, and restock queue monitoring.
- `ros_bridge/`: lightweight bridge for robot mission communication and WebSocket event forwarding.
- `RECAP_INVENTORY/README.md`: this documentation file.

## How it works

1. Product stock changes are monitored and persisted in the database.
2. When a product crosses its restock threshold, a restock item is queued.
3. The frontend receives live updates and shows pending robot restock jobs.
4. A REST or scheduled process triggers the ROS robot mission via the ROS bridge.
5. The robot reports mission feedback and completion over WebSockets.
6. MQTT camera events can flag `wrong_item` or `camera_blocked` conditions and pause the workflow.

## Notes

- The system assumes a configured MQTT broker for shelf sensors and a ROS 2 bridge endpoint for robot control.
- The repository contains the complete codebase for backend, frontend, and robot integration.
