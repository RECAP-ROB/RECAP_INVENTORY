import { AlertTriangle, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Product } from '@/lib/api';
import { cn } from '@/lib/utils';

interface LowStockAlertsProps {
  products: Product[];
  threshold?: number;
}

export const LowStockAlerts = ({ products, threshold = 1 }: LowStockAlertsProps) => {
  const lowStockProducts = products
    .filter(p => p.stock <= threshold)
    .sort((a, b) => a.stock - b.stock);

  const getStockColor = (stock: number) => {
    if (stock == 0) return 'text-destructive';
    if (stock <= 1) return 'text-warning';
    return 'text-muted-foreground';
  };

  const getShelfLocation = (product: Product) => {
    return product.shelf_location || 'Unknown';
  };

  return (
    <div className="bg-card rounded-xl border border-border p-5 animate-slide-up" style={{ animationDelay: '0.1s' }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-warning" />
          <h3 className="text-lg font-semibold text-foreground">Low Stock Alerts</h3>
        </div>
        <Link 
          to="/products?filter=low-stock" 
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors"
        >
          View all <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      <div className="space-y-3">
        {lowStockProducts.length == 0 ? (
          <p className="text-muted-foreground text-sm text-center py-4">All products well stocked</p>
        ) : (
          lowStockProducts.slice(0, 5).map((product, index) => (
            <div 
              key={product.name}
              className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium text-foreground">{product.name}</p>
                <p className="text-sm text-muted-foreground">
                  Shelf: {getShelfLocation(product)}
                </p>
              </div>
              <div className="text-right">
                <p className={cn("text-xl font-bold", getStockColor(product.stock))}>
                  {product.stock}
                </p>
                <p className="text-xs text-muted-foreground">of {threshold} min</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
