import { ShoppingCart, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Order } from '@/lib/api';
import { cn } from '@/lib/utils';

interface RecentOrdersProps {
  orders: Order[];
}

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

export const RecentOrders = ({ orders }: RecentOrdersProps) => {
  const formatOrderId = (id: string) => {
    return `ORD-${id.slice(0, 3).toUpperCase()}`;
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
    }).format(price);
  };

  return (
    <div className="bg-card rounded-xl border border-border p-5 animate-slide-up">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-foreground">Recent Orders</h3>
        <Link 
          to="/orders" 
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors"
        >
          View all <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      <div className="space-y-3">
        {orders.length === 0 ? (
          <p className="text-muted-foreground text-sm text-center py-4">No recent orders</p>
        ) : (
          orders.slice(0, 5).map((order) => (
            <div 
              key={order.order_id}
              className="flex items-center gap-4 p-3 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                <ShoppingCart className="w-5 h-5 text-muted-foreground" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-foreground">{formatOrderId(order.order_id)}</p>
                <p className="text-sm text-muted-foreground truncate">
                  {order.items.length} item{order.items.length !== 1 ? 's' : ''}
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-foreground">{formatPrice(order.total_price)}</p>
                <StatusBadge status={order.status} />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
