import { ReactNode } from 'react';
import { AppSidebar } from './AppSidebar';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { LogOut, RefreshCw, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface AppLayoutProps {
  children: ReactNode;
  title: string;
  subtitle?: string;
  onSync?: () => void;
  syncing?: boolean;
}

export const AppLayout = ({ children, title, subtitle, onSync, syncing }: AppLayoutProps) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex h-screen w-full bg-background">
      <AppSidebar />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between px-8 py-5 border-b border-border bg-card">
          <div>
            <h1 className="text-2xl font-bold text-foreground">{title}</h1>
            {subtitle && (
              <p className="text-muted-foreground text-sm mt-0.5">{subtitle}</p>
            )}
          </div>
          
          <div className="flex items-center gap-3">
            {onSync && (
              <Button
                onClick={onSync}
                disabled={syncing}
                className="gap-2"
                variant="default"
              >
                <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
                Sync Data
              </Button>
            )}
            
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted">
              <User className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium">{user?.username || 'User'}</span>
            </div>
            
            <Button
              variant="ghost"
              size="icon"
              onClick={handleLogout}
              className="text-muted-foreground hover:text-destructive"
            >
              <LogOut className="w-5 h-5" />
            </Button>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-8">
          {children}
        </main>
      </div>
    </div>
  );
};
