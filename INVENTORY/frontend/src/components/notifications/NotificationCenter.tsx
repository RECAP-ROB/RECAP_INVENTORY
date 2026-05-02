import { useState, useEffect } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { X, AlertTriangle, EyeOff } from 'lucide-react';
import { useWebSocket } from '@/hooks/use-websocket';

interface Notification {
  id: string;
  type: 'wrong_item' | 'camera_blocked' | 'info' | 'warning' | 'error';
  title: string;
  message: string;
  timestamp: Date;
  data?: any;
}

export const NotificationCenter = () => {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const { isConnected } = useWebSocket({
    onMessage: (message) => {
      if (message.event_type) {
        handleEventMessage(message);
      }
    },
  });

  const handleEventMessage = (message: any) => {
    const eventType = message.event_type;
    const data = message.data || {};

    let notification: Notification | null = null;

    switch (eventType) {
      case 'wrong_item':
        notification = {
          id: `wrong_item_${Date.now()}`,
          type: 'warning',
          title: 'Wrong Item Detected',
          message: `Wrong item detected for ${data.product_name} at ${new Date(data.timestamp).toLocaleTimeString()}`,
          timestamp: new Date(),
          data,
        };
        break;

      case 'camera_blocked':
        notification = {
          id: `camera_blocked_${Date.now()}`,
          type: 'error',
          title: 'Camera Obstructed',
          message: `Camera vision blocked by ${data.obstacles} obstacle(s) at ${new Date(data.timestamp).toLocaleTimeString()}`,
          timestamp: new Date(),
          data,
        };
        break;

      default:
        // Handle other event types if needed
        break;
    }

    if (notification) {
      setNotifications(prev => [notification!, ...prev].slice(0, 10)); // Keep max 10 notifications
    }
  };

  const dismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const clearAllNotifications = () => {
    setNotifications([]);
  };

  const getAlertVariant = (type: Notification['type']) => {
    switch (type) {
      case 'error':
        return 'destructive';
      case 'warning':
        return 'default';
      default:
        return 'default';
    }
  };

  const getAlertIcon = (type: Notification['type']) => {
    switch (type) {
      case 'wrong_item':
      case 'warning':
        return <AlertTriangle className="h-4 w-4" />;
      case 'camera_blocked':
      case 'error':
        return <EyeOff className="h-4 w-4" />;
      default:
        return null;
    }
  };

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {/* Connection status indicator */}
      <div className={`text-xs px-2 py-1 rounded ${
        isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
      }`}>
        WebSocket: {isConnected ? 'Connected' : 'Disconnected'}
      </div>

      {/* Notifications */}
      {notifications.map((notification) => (
        <Alert key={notification.id} variant={getAlertVariant(notification.type)} className="relative">
          <div className="flex items-start justify-between">
            <div className="flex items-start space-x-2">
              {getAlertIcon(notification.type)}
              <div className="flex-1">
                <AlertTitle className="text-sm font-medium">
                  {notification.title}
                </AlertTitle>
                <AlertDescription className="text-xs mt-1">
                  {notification.message}
                </AlertDescription>
                <div className="text-xs text-muted-foreground mt-1">
                  {notification.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 ml-2"
              onClick={() => dismissNotification(notification.id)}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        </Alert>
      ))}

      {/* Clear all button */}
      {notifications.length > 1 && (
        <Button
          variant="outline"
          size="sm"
          onClick={clearAllNotifications}
          className="w-full text-xs"
        >
          Clear All ({notifications.length})
        </Button>
      )}
    </div>
  );
};