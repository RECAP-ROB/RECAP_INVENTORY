import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { ordersAPI, productsAPI, Order, Product, restockAPI } from '@/lib/api';
import { RestockItem } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { Search, Plus, ShoppingCart, Eye } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format, set } from 'date-fns';
import { useToast } from '@/hooks/use-toast';
import { NotificationCenter } from '@/components/notifications/NotificationCenter';
import { useWebSocket } from '@/hooks/use-websocket';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';

const StatusBadge = ({ status }: { status: Order['status'] }) => {
  return (
    <span className={cn(
      "status-badge",
      status === 'Pending' && "status-pending",
      status === 'Confirmed' && "status-confirmed",
      status === 'Cancelled' && "status-failed"
    )}>
      {status}
    </span>
  );
};

const Orders = () => {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<Order[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [restockItems, setRestockItems] = useState<RestockItem[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [showNewOrderModal, setShowNewOrderModal] = useState(false);
  const [orderItems, setOrderItems] = useState<{ product: Product; quantity: number }[]>([]);
  const [creating, setCreating] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [ordersRes, productsRes, restockRes] = await Promise.all([
          ordersAPI.getAll(),
          productsAPI.getAll(),
          restockAPI.getQueue(),
        ]);
        setOrders(Array.isArray(ordersRes) ? ordersRes : []);
        setProducts(productsRes.results || []);
        setRestockItems(restockRes || []);
      }finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  // WebSocket integration for real-time restock updates
  useWebSocket({
    onMessage: (message) => {
      // Handle restock item status updates
      if (message.id && message.status && message.product_name) {
        setRestockItems(prev =>
          prev.map(item =>
            item.id === message.id
              ? { ...item, status: message.status as RestockItem['status'] }
              : item
          )
        );
      }
    },
  });

  // const productsRes = await productsAPI.getAll({ page_size: 1000 });

  const formatOrderId = (id: string) => {
    return `ORD-${id.slice(0, 8).toUpperCase()}`;
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
    }).format(price);
  };

  const handleCreateOrder = async () => {
    if (orderItems.length === 0) {
      toast({
        title: 'Validation Error',
        description: 'Please add at least one item to the order',
        variant: 'destructive',
      });
      return;
    }

    setCreating(true);
    try {
      const orderData = {
        items: orderItems.map(item => ({ product: item.product.id!, quantity: item.quantity })),
      };
      const newOrder = await ordersAPI.create(orderData);
      const [ordersRes, productsRes, restockRes] = await Promise.all([
        ordersAPI.getAll(),
        productsAPI.getAll(),
        restockAPI.getQueue(),
      ]);
      setOrders(Array.isArray(ordersRes) ? ordersRes : [newOrder]);
      setProducts(productsRes.results || []);
      setRestockItems(restockRes || []);
      setShowNewOrderModal(false);
      setOrderItems([]);
      toast({
        title: 'Success',
        description: 'Order created successfully',
      });
      navigate('/orders');
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to create order',
        variant: 'destructive',
      });
    } finally {
      setCreating(false);
    }
  };

  const addOrderItem = (product: Product, quantity: number) => {
    if (quantity <= 0) return;

    setOrderItems(prev => {
      const existing = prev.find(item => item.product.id === product.id);
      if (existing) {
        return prev.map(item =>
          item.product.id === product.id
            ? { ...item, quantity: item.quantity + quantity }
            : item
        );
      }

      return [...prev, { product, quantity }];
    });
  };

  const removeOrderItem = (productId?: number) => {
    setOrderItems(prev => prev.filter(item => item.product.id !== productId));
  };

  const filteredOrders = orders.filter(o => {
    const matchesSearch = formatOrderId(o.order_id).toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || o.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const lowStockCount = products.filter(p => p.stock <= 1).length;
  const pendingOrdersCount = orders.filter(o => o.status === 'Pending').length;

  const [selectedProductId, setSelectedProductId] = useState<string>('');
  const [selectedQuantity, setSelectedQuantity] = useState<number>(1);
  

  return (
    <AppLayout title="Orders" subtitle="View and manage customer orders">
      <div className="bg-card rounded-xl border border-border">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 border-b border-border">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search orders..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-40">
                <SelectValue placeholder="Filter status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="Pending">Pending</SelectItem>
                <SelectItem value="Confirmed">Confirmed</SelectItem>
                <SelectItem value="Cancelled">Cancelled</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button className="gap-2" onClick={() => setShowNewOrderModal(true)}>
            <Plus className="w-4 h-4" />
            New Order
          </Button>
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
                <TableHead>Order ID</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Items</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredOrders.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    No orders found
                  </TableCell>
                </TableRow>
              ) : (
                filteredOrders.map((order) => (
                  <TableRow key={order.order_id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                          <ShoppingCart className="w-5 h-5 text-muted-foreground" />
                        </div>
                        <span className="font-medium">{formatOrderId(order.order_id)}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {(() => {
                        try {
                          return format(new Date(order.created_at), 'yyyy-MM-dd');
                        } catch {
                          return 'Invalid Date';
                        }
                      })()}
                    </TableCell>
                    <TableCell>
                      {order.items.length} item{order.items.length !== 1 ? 's' : ''}
                    </TableCell>
                    <TableCell className="font-semibold">{formatPrice(order.total_price)}</TableCell>
                    <TableCell><StatusBadge status={order.status} /></TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon">
                        <Eye className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </div>

      {/* New Order Modal */}
      <Dialog open={showNewOrderModal} onOpenChange={setShowNewOrderModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Create New Order</DialogTitle>
            <DialogDescription>
              Add items to create a new order.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Add Product</Label>
              <div className="flex gap-2 mt-2">
                <Select value={selectedProductId} onValueChange={(value) => setSelectedProductId(value)}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select product" />
                  </SelectTrigger>
                  <SelectContent>
                    {products.map((product) => (
                      <SelectItem key={product.id} value={product.id?.toString() || ''}>
                        {product.name} - {formatPrice(product.price)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={selectedQuantity.toString()}
                  min={1}
                  placeholder="Quantity"
                  className="w-20"
                  onChange={(e) => {
                    const value = parseInt(e.target.value);
                    if (!isNaN(value) && value > 0) {
                      setSelectedQuantity(value);
                    } else {
                      setSelectedQuantity(1);
                    }
                  }}
                />
                <Button
                  variant="secondary"
                  onClick={() => {
                    const product = products.find(p => p.id?.toString() === selectedProductId);
                    if (product) {
                      addOrderItem(product, selectedQuantity);
                    }
                  }}
                >
                  Add Item
                </Button>
              </div>
            </div>
            {orderItems.length > 0 && (
              <div>
                <Label>Order Items</Label>
                <div className="mt-2 space-y-2">
                  {orderItems.map((item, index) => (
                    <div key={index} className="flex justify-between items-center p-2 border rounded">
                      <div className="flex gap-2 items-center">
                        <span>{item.product.name} x{item.quantity}</span>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeOrderItem(item.product.id)}
                        >
                          x
                        </Button>
                      </div>
                      <span>{formatPrice(item.product.price * item.quantity)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewOrderModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateOrder} disabled={orderItems.length === 0}>
              Create Order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Notification Center for MQTT events */}
      <NotificationCenter />
    </AppLayout>
  );
};

export default Orders;
