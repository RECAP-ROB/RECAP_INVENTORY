import { useState, useEffect } from 'react';
import { AppLayout } from '@/components/layout/AppLayout';
import { StatCard } from '@/components/dashboard/StatCard';
import { RecentOrders } from '@/components/dashboard/RecentOrders';
import { LowStockAlerts } from '@/components/dashboard/LowStockAlerts';
import { RobotOperations } from '@/components/dashboard/RobotOperations';
import { Package, AlertTriangle, ShoppingCart, Bot } from 'lucide-react';
import { productsAPI, ordersAPI, restockAPI, dashboardAPI, Product, Order, RestockItem } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import { useRobotStatus } from '@/contexts/RobotStatusContext';

const Dashboard = () => {
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [restockItems, setRestockItems] = useState<RestockItem[]>([]);
  const {
    robotArmStatus,
    robotChassisStatus,
    robotStep,
    robotProgress,
    setRobotArmStatus,
    setRobotChassisStatus,
    setRobotStep,
    setRobotProgress,
  } = useRobotStatus();
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const fetchData = async () => {
    try {
      // For demo, use mock data if API fails
      try {
        const data = await dashboardAPI.getData();
        setProducts(data.products || []);
        setOrders(data.orders || []);
        setRestockItems(data.restock_queue || []);
      } catch {
        // Use demo data
        setProducts([
          { id: 1, name: 'Sugar', description: 'Sweet', price: 79.99, stock: 4 },
          { id: 2, name: 'Coffee Machine', description: 'Brewing', price: 70.99, stock: 6 },
          { id: 3, name: 'Vegetable Oil', description: 'Cooking', price: 15.99, stock: 11 },
          { id: 4, name: 'Soap', description: 'Cleaning', price: 17.99, stock: 12 },
          { id: 5, name: 'Camera', description: 'Photography', price: 350.99, stock: 4 },
          { id: 6, name: 'Watch', description: 'Timekeeping', price: 500.05, stock: 0 },
        ]);
        setOrders([
          { order_id: '001abc', user: 1, created_at: new Date().toISOString(), status: 'Pending', items: [{ product_name: 'Sugar', product_price: 79.99, quantity: 2, item_subtotal: 159.98 }], total_price: 129.99 },
          { order_id: '002def', user: 1, created_at: new Date().toISOString(), status: 'Confirmed', items: [{ product_name: 'Coffee', product_price: 70.99, quantity: 1, item_subtotal: 70.99 }], total_price: 89.50 },
          { order_id: '003ghi', user: 1, created_at: new Date().toISOString(), status: 'Pending', items: [{ product_name: 'Watch', product_price: 245, quantity: 1, item_subtotal: 245 }], total_price: 245 },
        ]);
        setRestockItems([
          { id: 1, product_name: 'Watch', quantity: 10, shelf_location: 'C2', status: 'IN_PROGRESS' },
          { id: 2, product_name: 'Camera', quantity: 5, shelf_location: 'D1', status: 'PENDING' },
        ]);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    const rosUrl = import.meta.env.VITE_ROS_MESSAGE || 'ws://localhost:9000/ws';
    const ws = new WebSocket(rosUrl);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'robot_feedback') {
        if (data.arm_status) setRobotArmStatus(data.arm_status);
        if (data.chassis_status) setRobotChassisStatus(data.chassis_status);
        if (data.current_step) setRobotStep(data.current_step);
        if (typeof data.progress === 'number') setRobotProgress(data.progress);

        if (typeof data.item_id !== 'undefined') {
          setRestockItems(prev => prev.map(item =>
            item.id === Number(data.item_id)
              ? { ...item, status: data.mission_result?.success ? 'COMPLETED' : (data.mission_result ? 'FAILED' : item.status) }
              : item
          ));
        }
      }
    };

    ws.onerror = (error) => {
      console.error('Dashboard ROS WebSocket error:', error);
    };

    return () => {
      ws.close();
    };
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    await fetchData();
    setSyncing(false);
    toast({
      title: 'Data Synced',
      description: 'All inventory data has been refreshed',
    });
  };

  const lowStockCount = products.filter(p => p.stock <= 1).length;
  const pendingOrdersCount = orders.filter(o => o.status === 'Pending').length;
  const pendingRestockCount = restockItems.filter(r => r.status === 'PENDING' || r.status === 'IN_PROGRESS').length;
  

  if (loading) {
    return (
      <AppLayout title="Dashboard" subtitle="Monitor your inventory and robot operations">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout 
      title="Dashboard" 
      subtitle="Monitor your inventory and robot operations"
      onSync={handleSync}
      syncing={syncing}
    >
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Total Products"
          value={products.length}
          subtitle="In inventory"
          trend={{ value: '5% increase', positive: true }}
          icon={Package}
          variant="primary"
        />
        <StatCard
          title="Low Stock Items"
          value={lowStockCount}
          subtitle="Need attention"
          icon={AlertTriangle}
          variant="warning"
        />
        <StatCard
          title="Recent Orders"
          value={pendingOrdersCount}
          subtitle="Monitor pending orders"
          icon={ShoppingCart}
        />
        <StatCard
          title="Restock Queue"
          value={pendingRestockCount}
          subtitle="Robot tasks pending"
          icon={Bot}
        />
      </div>

      {/* Orders and Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <RecentOrders orders={orders} />
        <LowStockAlerts products={products} />
      </div>

      {/* Robot Operations */}
      <RobotOperations
        restockItems={restockItems}
        robotArmStatus={robotArmStatus}
        robotChassisStatus={robotChassisStatus}
        robotStep={robotStep}
        robotProgress={robotProgress}
      />
    </AppLayout>
  );
};

export default Dashboard;
