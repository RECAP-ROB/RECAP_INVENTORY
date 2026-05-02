import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Bot, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

const Login = () => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const { login } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();

    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault();
      
      if (!username || !password) {
        toast({
          title: 'Validation Error',
          description: 'Please enter both username and password',
          variant: 'destructive',
        });
        return;
      }

    setIsLoading(true);
    
    try {
      await login(username, password);
      toast({
        title: 'Welcome back!',
        description: 'Successfully logged in to RECAP',
      });
      window.location.href = '/';
    } catch (error: any) {
      toast({
        title: 'Login Failed',
        description: error.response?.data?.non_field_errors?.[0] || 'Invalid credentials',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };


  return (
    <div className="min-h-screen flex">
      {/* Left Panel - Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-sidebar flex-col justify-between p-12">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center">
              <Bot className="w-7 h-7 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-primary">
                RECAP
              </h1>
              <p className="text-sidebar-muted text-sm">Inventory Management System</p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <h2 className="text-4xl font-bold text-sidebar-accent-foreground leading-tight">
            Automated Shelf<br />Restocking System
          </h2>
          <p className="text-sidebar-foreground text-lg max-w-md">
            Monitor your inventory with our integrated robotic system.
          </p>
          
          <div className="grid grid-cols-2 gap-4 pt-4">
            <div className="p-4 rounded-lg bg-sidebar-accent">
              <p className="text-3xl font-bold text-primary">0.8%</p>
              <p className="text-sidebar-muted text-sm">Downtime</p>
            </div>
            <div className="p-4 rounded-lg bg-sidebar-accent">
              <p className="text-3xl font-bold text-success">99.2%</p>
              <p className="text-sidebar-muted text-sm">Uptime</p>
            </div>
          </div>
        </div>

        <p className="text-sidebar-muted text-sm">
          © 2026 RECAP. Robotic Inventory Solutions.
          Made in Kenya.
        </p>
      </div>

      {/* Right Panel - Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-md space-y-8">
          <div className="text-center lg:text-left">
            <div className="lg:hidden flex items-center justify-center gap-3 mb-8">
              <div className="w-10 h-10 rounded-lg bg-primary flex items-center justify-center">
                <Bot className="w-6 h-6 text-primary-foreground" />
              </div>
              <span className="text-xl font-bold text-primary">
                RE<span className="text-foreground">CAP</span>
              </span>
            </div>
            <h2 className="text-2xl font-bold text-foreground">Welcome back</h2>
            <p className="text-muted-foreground mt-2">
              Sign in to your account to continue
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="h-12"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-12 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-12 text-base font-medium"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Signing in...
                </>
              ) : (
                'Sign in'
              )}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            <span className="font-medium text-foreground"></span>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
