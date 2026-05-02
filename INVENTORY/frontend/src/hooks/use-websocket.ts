import { useEffect, useRef, useState } from 'react';

interface WebSocketMessage {
  event_type?: string;
  data?: any;
  id?: number;
  status?: string;
  product_name?: string;
}

interface UseWebSocketOptions {
  url?: string;
  onMessage?: (message: WebSocketMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

export const useWebSocket = (options: UseWebSocketOptions = {}) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const {
    url = `ws://localhost:8000/ws/restock/`,
    onMessage,
    onOpen,
    onClose,
    onError,
  } = options;

  useEffect(() => {
    const connect = () => {
      try {
        wsRef.current = new WebSocket(url);

        wsRef.current.onopen = () => {
          setIsConnected(true);
          onOpen?.();
        };

        wsRef.current.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            setLastMessage(message);
            onMessage?.(message);
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        wsRef.current.onclose = () => {
          setIsConnected(false);
          onClose?.();
          // Auto-reconnect after 5 seconds
          setTimeout(connect, 5000);
        };

        wsRef.current.onerror = (error) => {
          console.error('WebSocket error:', error);
          onError?.(error);
        };
      } catch (error) {
        console.error('Failed to create WebSocket connection:', error);
        // Retry connection after 5 seconds
        setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [url, onMessage, onOpen, onClose, onError]);

  const sendMessage = (message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected');
    }
  };

  return {
    isConnected,
    lastMessage,
    sendMessage,
  };
};