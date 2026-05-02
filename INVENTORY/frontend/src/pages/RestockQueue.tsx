import { useState, useEffect } from 'react';
import { AppLayout } from '@/components/layout/AppLayout';
import { restockAPI, RestockItem } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useRobotStatus } from '@/contexts/RobotStatusContext';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RefreshCw, Play, CheckCircle, XCircle, Bot } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToast } from '@/hooks/use-toast';

const StatusBadge = ({ status }: { status: RestockItem['status'] }) => {
  return (
    <span className={cn(
      "status-badge",
      status === 'PENDING' && "status-pending",
      status === 'IN_PROGRESS' && "status-progress",
      status === 'COMPLETED' && "status-confirmed",
      status === 'FAILED' && "status-failed"
    )}>
      {status.replace('_', ' ')}
    </span>
  );
};

const RestockQueue = () => {
  const [items, setItems] = useState<RestockItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();
  const {
    setRobotArmStatus,
    setRobotChassisStatus,
    setRobotStep,
    setRobotProgress,
  } = useRobotStatus();

  useEffect(() => {
    const fetchRestockItems = async () => {
      try {
        const response = await restockAPI.getQueue();
        setItems(Array.isArray(response) ? response : []);
      } catch {
        // Demo data
        setItems([
          { id: 1, product_name: 'Watch', quantity: 10, shelf_location: 'C2', status: 'IN_PROGRESS' },
          { id: 2, product_name: 'Camera', quantity: 5, shelf_location: 'D1', status: 'PENDING' },
          { id: 3, product_name: 'Sugar', quantity: 15, shelf_location: 'A1', status: 'PENDING' },
          { id: 4, product_name: 'Coffee Machine', quantity: 8, shelf_location: 'B3', status: 'COMPLETED' },
          { id: 5, product_name: 'Soap', quantity: 20, shelf_location: 'A4', status: 'FAILED' },
        ]);
      } finally {
        setLoading(false);
      }
    };
    fetchRestockItems();
  }, []);

  useEffect(() => {
  const socket = new WebSocket("ws://localhost:8000/ws/restock/");
  const rosSocket = new WebSocket(import.meta.env.VITE_ROS_MESSAGE || "ws://localhost:9000/ws");
  
  rosSocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'restock_update') {
      setItems(prev =>
        prev.map(item =>
          item.id === data.id
            ? { ...item, status: data.status }
            : item
        )
      );
    }

    if (data.type === 'robot_feedback') {
      if (data.arm_status) setRobotArmStatus(data.arm_status);
      if (data.chassis_status) setRobotChassisStatus(data.chassis_status);
      if (data.current_step) setRobotStep(data.current_step);
      if (typeof data.progress === 'number') setRobotProgress(data.progress);
    }

    if (data.type === 'mission_result') {
      const status = data.success ? 'COMPLETED' : 'FAILED';
      const restockItemId = Number(data.item_id ?? data.restockItemId);

      setItems(prev =>
        prev.map(item =>
          item.id === restockItemId
            ? { ...item, status }
            : item
        )
      );
      toast({
        title: `Mission ${status}`,
        description: `Restock for item ID ${restockItemId} has ${status.toLowerCase()}.`,
      });
    }
    console.log("ROS Message Received:", data);
  }

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);

    setItems(prev =>
      prev.map(item =>
        item.id === data.id
          ? { ...item, status: data.status }
          : item
      )
    );
  };

  socket.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  return () => {
    socket.close();
  };
}, []);

  const handleStartRestock = async (item: RestockItem) => {
    try {
      await restockAPI.triggerRobotRestock(item);
      setItems(prev => prev.map(i => 
        i.id === item.id ? { ...i, status: 'IN_PROGRESS' as const } : i
      ));
      toast({
        title: 'Robot Command Sent',
        description: `Restocking ${item.product_name} to ${item.shelf_location}`,
      });
    } catch (error) {
      toast({
        title: 'Command Failed',
        description: 'Failed to send command to robot',
        variant: 'destructive',
      });
    }
  };

  const handleUpdateStatus = async (item: RestockItem, status: RestockItem['status']) => {
    try {
      await restockAPI.updateStatus(item.id, status);
      setItems(prev => prev.map(i => 
        i.id === item.id ? { ...i, status } : i
      ));
      toast({
        title: 'Status Updated',
        description: `Restock has ${status.toLowerCase()} for ${item.product_name}`,
      });
    } catch {
      // Update locally for demo
      setItems(prev => prev.map(i => 
        i.id === item.id ? { ...i, status } : i
      ));
      toast({
        title: 'Status Updated',
        description: `Restock has ${status.toLowerCase()} for ${item.product_name}`,
      });
    }
  };

  const filteredItems = items.filter(i => 
    statusFilter === 'all' || i.status === statusFilter
  );

  const pendingCount = items.filter(i => i.status === 'PENDING').length;
  const inProgressCount = items.filter(i => i.status === 'IN_PROGRESS').length;

  return (
    <AppLayout title="Restock Queue" subtitle="Manage robot restocking operations">
      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-card rounded-xl border border-border p-4 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-warning/20 flex items-center justify-center">
            <RefreshCw className="w-6 h-6 text-warning" />
          </div>
          <div>
            <p className="text-2xl font-bold">{pendingCount}</p>
            <p className="text-sm text-muted-foreground">Pending Tasks</p>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-border p-4 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-info/20 flex items-center justify-center">
            <Bot className="w-6 h-6 text-info animate-pulse" />
          </div>
          <div>
            <p className="text-2xl font-bold">{inProgressCount}</p>
            <p className="text-sm text-muted-foreground">In Progress</p>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-border p-4 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-success/20 flex items-center justify-center">
            <CheckCircle className="w-6 h-6 text-success" />
          </div>
          <div>
            <p className="text-2xl font-bold">{items.filter(i => i.status === 'COMPLETED').length}</p>
            <p className="text-sm text-muted-foreground">Completed</p>
          </div>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-border">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h3 className="text-lg font-semibold">Queue Items</h3>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Filter status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="IN_PROGRESS">In Progress</SelectItem>
              <SelectItem value="COMPLETED">Completed</SelectItem>
              <SelectItem value="FAILED">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Shelf Location</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                    No items in queue
                  </TableCell>
                </TableRow>
              ) : (
                filteredItems.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          "w-10 h-10 rounded-lg flex items-center justify-center",
                          item.status === 'IN_PROGRESS' 
                            ? "bg-info/20" 
                            : "bg-muted"
                        )}>
                          <RefreshCw className={cn(
                            "w-5 h-5",
                            item.status === 'IN_PROGRESS' 
                              ? "text-info animate-spin" 
                              : "text-muted-foreground"
                          )} />
                        </div>
                        <span className="font-medium">{item.product_name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="font-semibold">{item.quantity}</TableCell>
                    <TableCell>
                      <span className="px-2 py-1 rounded bg-muted text-sm font-mono">
                        {item.shelf_location}
                      </span>
                    </TableCell>
                    <TableCell><StatusBadge status={item.status} /></TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        {item.status === 'PENDING' && (
                          <Button 
                            size="sm" 
                            className="gap-1"
                            onClick={() => handleStartRestock(item)}
                          >
                            <Play className="w-3 h-3" />
                            Start
                          </Button>
                        )}
                        {item.status === 'IN_PROGRESS' && (
                          <>
                            <Button 
                              size="sm" 
                              variant="outline"
                              className="gap-1 text-success hover:text-success"
                              onClick={() => handleUpdateStatus(item, 'COMPLETED')}
                            >
                              <CheckCircle className="w-3 h-3" />
                              Complete
                            </Button>
                            <Button 
                              size="sm" 
                              variant="outline"
                              className="gap-1 text-destructive hover:text-destructive"
                              onClick={() => handleUpdateStatus(item, 'FAILED')}
                            >
                              <XCircle className="w-3 h-3" />
                              Failed
                            </Button>
                          </>
                        )}
                        {(item.status === 'COMPLETED' || item.status === 'FAILED') && (
                          <span className="text-sm text-muted-foreground">—</span>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </div>
    </AppLayout>
  );
};

export default RestockQueue;
