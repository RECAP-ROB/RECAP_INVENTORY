import { NavLink, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Package, 
  ShoppingCart, 
  RefreshCw,
  Settings,
  ChevronLeft,
  Bot
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useState } from 'react';
import { useRobotStatus } from '@/contexts/RobotStatusContext';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Products', href: '/products', icon: Package },
  { name: 'Orders', href: '/orders', icon: ShoppingCart },
  { name: 'Restock Queue', href: '/restock', icon: RefreshCw },
];

export const AppSidebar = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const {
    robotArmStatus,
    robotChassisStatus,
  } = useRobotStatus();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'IDLE':
      case 'READY':
        return 'text-success';
      case 'MOVING':
      case 'BUSY':
        return 'text-info';
      case 'ERROR':
        return 'text-destructive';
      default:
        return 'text-muted-foreground';
    }
  };

  return (
    <aside 
      className={cn(
        "flex flex-col h-screen bg-sidebar transition-all duration-300",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-sidebar-border">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <Bot className="w-5 h-5 text-primary-foreground" />
        </div>
        {!collapsed && (
          <div className="flex flex-col">
            <span className="text-primary font-bold text-lg tracking-tight">
              RECAP
            </span>
            <span className="text-sidebar-muted text-xs">v2.1.0</span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <NavLink
              key={item.name}
              to={item.href}
              className={cn(
                "nav-item",
                isActive && "nav-item-active"
              )}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!collapsed && <span className="font-medium">{item.name}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Robot Status */}
      <div className={cn(
        "mx-3 mb-3 p-3 rounded-lg bg-sidebar-accent",
        collapsed && "p-2"
      )}>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse-subtle" />
          {!collapsed && (
            <span className="text-sidebar-accent-foreground text-sm font-medium">
              Robot Status
            </span>
          )}
        </div>
        {!collapsed && (
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-sidebar-muted">Chassis:</span>
              <span className={getStatusColor(robotChassisStatus)}>{robotChassisStatus}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sidebar-muted">Arm:</span>
              <span className={getStatusColor(robotArmStatus)}>{robotArmStatus}</span>
            </div>
          </div>
        )}
      </div>

      {/* Settings & Collapse */}
      <div className="border-t border-sidebar-border p-3 space-y-1">
        <NavLink
          to="/settings"
          className={cn(
            "nav-item",
            location.pathname === '/settings' && "nav-item-active"
          )}
        >
          <Settings className="w-5 h-5 flex-shrink-0" />
          {!collapsed && <span className="font-medium">Settings</span>}
        </NavLink>
        
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="nav-item w-full justify-center"
        >
          <ChevronLeft className={cn(
            "w-5 h-5 transition-transform",
            collapsed && "rotate-180"
          )} />
        </button>
      </div>
    </aside>
  );
};
