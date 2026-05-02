import { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: {
    value: string;
    positive: boolean;
  };
  icon: LucideIcon;
  variant?: 'default' | 'primary' | 'warning';
}

export const StatCard = ({ 
  title, 
  value, 
  subtitle, 
  trend, 
  icon: Icon,
  variant = 'default' 
}: StatCardProps) => {
  return (
    <div className={cn(
      "stat-card group animate-fade-in",
      variant === 'primary' && "stat-card-primary",
      variant === 'warning' && "stat-card-warning"
    )}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-muted-foreground text-sm font-medium">{title}</p>
          <p className="text-3xl font-bold text-foreground mt-1">{value}</p>
          {subtitle && (
            <p className="text-muted-foreground text-sm mt-1">{subtitle}</p>
          )}
          {trend && (
            <p className={cn(
              "text-sm mt-2 font-medium",
              trend.positive ? "text-success" : "text-destructive"
            )}>
              {trend.positive ? '↑' : '↓'} {trend.value}
            </p>
          )}
        </div>
        <div className={cn(
          "w-10 h-10 rounded-xl flex items-center justify-center transition-transform group-hover:scale-110",
          variant === 'primary' && "bg-primary/20 text-primary",
          variant === 'warning' && "bg-warning/20 text-warning",
          variant === 'default' && "bg-muted text-muted-foreground"
        )}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
};
