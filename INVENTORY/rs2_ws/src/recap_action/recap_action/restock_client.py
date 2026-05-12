import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
import asyncio

from my_recap_interfaces.action import Restock


class ROSBridge(Node):

    def __init__(self, websocket_manager):
        super().__init__('ros_bridge')

        self.ws_manager = websocket_manager
        self.current_goal_item_id = None

        self.action_client_ = ActionClient(
            self,
            Restock,
            'restock'
        )

    async def send_restock_goal(self, request):

        goal_msg = Restock.Goal()

        self.current_goal_item_id = request.item_id

        goal_msg.item_id = request.item_id
        goal_msg.product_name = request.product_name
        goal_msg.shelf_location = request.shelf_location
        goal_msg.quantity = request.quantity
        goal_msg.current_state = request.current_state

        self.get_logger().info("Sending restock mission")

        self.action_client_.wait_for_server()

        goal_future = asyncio.Future()

        def goal_callback(fut):
            try:
                goal_handle = fut.result()
                if goal_handle.accepted:
                    result_future = goal_handle.get_result_async()
                    def result_callback(res_fut):
                        try:
                            result = res_fut.result()
                            mission_result = {
                                "status": "mission_complete",
                                "success": result.result.success,
                                "message": result.result.message,
                                "item_id": self.current_goal_item_id,
                                "arm_status": "READY" if result.result.success else "ERROR",
                                "chassis_status": "IDLE" if result.result.success else "ERROR",
                            }
                            self.ws_manager.feedback_queue.put({
                                "type": "robot_feedback",
                                "item_id": self.current_goal_item_id,
                                "current_step": "Final verification",
                                "progress": 1.0,
                                "arm_status": mission_result["arm_status"],
                                "chassis_status": mission_result["chassis_status"],
                                "mission_result": mission_result,
                            })
                            goal_future.set_result(mission_result)
                        except Exception as e:
                            goal_future.set_exception(e)
                    result_future.add_done_callback(result_callback)
                else:
                    goal_future.set_result({"status": "rejected"})
            except Exception as e:
                goal_future.set_exception(e)

        self.action_client_.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        ).add_done_callback(goal_callback)

        return await goal_future

    def _map_feedback_to_subsystems(self, current_step: str):
        if current_step in ["Navigating to pickup location", "Navigating to shelf"]:
            return "MOVING", "IDLE"
        if current_step in ["Picking item", "Placing item"]:
            return "IDLE", "BUSY"
        if current_step in ["Final verification", "Validating inventory"]:
            return "IDLE", "READY"
        return "ERROR", "ERROR"

    def feedback_callback(self, feedback_msg):

        feedback = feedback_msg.feedback
        chassis_status, arm_status = self._map_feedback_to_subsystems(feedback.current_step)

        self.ws_manager.feedback_queue.put({
            "type": "robot_feedback",
            "item_id": self.current_goal_item_id,
            "current_step": feedback.current_step,
            "progress": feedback.progress,
            "arm_status": arm_status,
            "chassis_status": chassis_status,
        })
