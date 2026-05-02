import { Bot, ArrowRight, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { RestockItem } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface RobotOperationsProps {
  restockItems: RestockItem[];
  robotArmStatus?: 'READY' | 'BUSY' | 'ERROR' | 'IDLE';
  robotChassisStatus?: 'IDLE' | 'MOVING' | 'ERROR';
  robotStep?: string;
  robotProgress?: number;
  onTriggerRestock?: (item: RestockItem) => void;
}

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

export const RobotOperations = ({ restockItems, robotArmStatus = 'IDLE', robotChassisStatus = 'IDLE', robotStep = 'Idle', robotProgress = 0, onTriggerRestock }: RobotOperationsProps) => {
  const activeItems = restockItems.filter(
    item => item.status === 'PENDING' || item.status === 'IN_PROGRESS'
  );

  return (
    <div className="bg-card rounded-xl border border-border p-5 animate-slide-up" style={{ animationDelay: '0.2s' }}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-semibold text-foreground">Robot Operations</h3>
        </div>
        <Link to="/restock">
          <Button variant="outline" size="sm" className="gap-2">
            Manage Queue <ArrowRight className="w-4 h-4" />
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div className="px-3 py-2 rounded-lg bg-muted border border-border">
          <p className="text-xs text-muted-foreground">Chassis</p>
          <p className="font-semibold">{robotChassisStatus}</p>
        </div>
        <div className="px-3 py-2 rounded-lg bg-muted border border-border">
          <p className="text-xs text-muted-foreground">Arm</p>
          <p className="font-semibold">{robotArmStatus}</p>
        </div>
        <div className="px-3 py-2 rounded-lg bg-muted border border-border">
          <p className="text-xs text-muted-foreground">Step</p>
          <p className="font-semibold">{robotStep}</p>
          <p className="text-xs">Progress: {Math.round(robotProgress * 100)}%</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {activeItems.length === 0 ? (
          <p className="text-muted-foreground text-sm text-center py-4 col-span-2">
            No active robot operations
          </p>
        ) : (
          activeItems.slice(0, 4).map((item) => (
            <div 
              key={item.id}
              className="flex items-center gap-3 p-4 rounded-lg bg-muted/30 border border-border"
            >
              <div className={cn(
                "w-10 h-10 rounded-lg flex items-center justify-center",
                item.status === 'IN_PROGRESS' 
                  ? "bg-info/20 text-info" 
                  : "bg-muted text-muted-foreground"
              )}>
                <RefreshCw className={cn(
                  "w-5 h-5",
                  item.status === 'IN_PROGRESS' && "animate-spin"
                )} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-foreground">{item.product_name}</p>
                <p className="text-sm text-muted-foreground">
                  Qty: {item.quantity} → {item.shelf_location}
                </p>
              </div>
              <StatusBadge status={item.status} />
            </div>
          ))
        )}
      </div>
    </div>
  );
};
