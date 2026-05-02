import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Server, Bot, Bell, Shield } from 'lucide-react';

const Settings = () => {
  return (
    <AppLayout title="Settings" subtitle="Configure system and robot settings">
      <div className="max-w-3xl space-y-6">
        {/* API Configuration */}
        <div className="bg-card rounded-xl border border-border p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
              <Server className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold">API Configuration</h3>
              <p className="text-sm text-muted-foreground">Configure backend API settings</p>
            </div>
          </div>
          <Separator className="my-4" />
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="api-url">Backend API URL</Label>
              <Input
                id="api-url"
                defaultValue="http://localhost:8000"
                placeholder="https://api.example.com"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="api-timeout">Request Timeout (ms)</Label>
              <Input
                id="api-timeout"
                type="number"
                defaultValue="30000"
              />
            </div>
          </div>
        </div>

        {/* Robot Configuration */}
        <div className="bg-card rounded-xl border border-border p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-info/20 flex items-center justify-center">
              <Bot className="w-5 h-5 text-info" />
            </div>
            <div>
              <h3 className="font-semibold">Robot Configuration</h3>
              <p className="text-sm text-muted-foreground">Robot service settings</p>
            </div>
          </div>
          <Separator className="my-4" />
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="ros-uri">Action Server URI</Label>
              <Input
                id="ros-uri"
                defaultValue="ws://localhost:9000"
                placeholder="ws://robot-host:9000"
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Auto-reconnect</p>
                <p className="text-sm text-muted-foreground">Automatically reconnect to ROS2 on disconnect</p>
              </div>
              <Switch defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Emergency Stop Enabled</p>
                <p className="text-sm text-muted-foreground">Enable emergency stop functionality</p>
              </div>
              <Switch defaultChecked />
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="bg-card rounded-xl border border-border p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-warning/20 flex items-center justify-center">
              <Bell className="w-5 h-5 text-warning" />
            </div>
            <div>
              <h3 className="font-semibold">Notifications</h3>
              <p className="text-sm text-muted-foreground">Alert preferences</p>
            </div>
          </div>
          <Separator className="my-4" />
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Low Stock Alerts</p>
                <p className="text-sm text-muted-foreground">Get notified when products are running low</p>
              </div>
              <Switch defaultChecked />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Robot Status Updates</p>
                <p className="text-sm text-muted-foreground">Receive robot operation notifications</p>
              </div>
              <Switch defaultChecked />
            </div>
            <div className="space-y-2">
              <Label htmlFor="stock-threshold">Low Stock Threshold</Label>
              <Input
                id="stock-threshold"
                type="number"
                defaultValue="5"
              />
            </div>
          </div>
        </div>

        {/* Security */}
        <div className="bg-card rounded-xl border border-border p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-destructive/20 flex items-center justify-center">
              <Shield className="w-5 h-5 text-destructive" />
            </div>
            <div>
              <h3 className="font-semibold">Security</h3>
              <p className="text-sm text-muted-foreground">Account security settings</p>
            </div>
          </div>
          <Separator className="my-4" />
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Two-Factor Authentication</p>
                <p className="text-sm text-muted-foreground">Add an extra layer of security</p>
              </div>
              <Switch />
            </div>
            <Button variant="outline">Change Password</Button>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="outline">Reset to Defaults</Button>
          <Button>Save Changes</Button>
        </div>
      </div>
    </AppLayout>
  );
};

export default Settings;
