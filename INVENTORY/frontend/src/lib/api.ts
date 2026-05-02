import axios from 'axios';


const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Types based on Django models
export interface Product {
  id?: number;
  name: string;
  description: string;
  price: number;
  stock: number;
  in_stock?: boolean;
  shelf_location?: string;
  image?: string;
}

export interface ProductTemplate {
  id?: number;
  name: string;
  description: string;
  price: number;
  shelf_location?: string;
  image?: string;
}

export interface OrderItem {
  product_name: string;
  product_price: number;
  quantity: number;
  item_subtotal: number;
}

export interface Order {
  order_id: string;
  user: number;
  created_at: string;
  status: 'Pending' | 'Confirmed' | 'Cancelled';
  items: OrderItem[];
  total_price: number;
}

export interface RestockItem {
  id: number;
  product_name: string;
  quantity: number;
  shelf_location: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
}

export interface ProductInfo {
  products: Product[];
  count: number;
  max_price: number;
}

export interface User {
  id: number;
  username: string;
  is_staff: boolean;
}

export interface AuthResponse {
  access: string;
  refresh: string;
}

// Auth API
export const authAPI = {
  login: async (username: string, password: string) => {
    const res = await api.post('/api/token/', { username, password });
    return res.data;
  },

  getMe: async () => {
    const res = await api.get('/user/me/');
    return res.data;
  },

  logout: () => {
    localStorage.clear();
  },

  isAuthenticated: () => !!localStorage.getItem('auth_token'),
};

// Products API
export const productsAPI = {
  getAll: async (params: { page?: number; page_size?: number; search?: string; ordering?: string } = { page: 1, page_size: 1000 }) => {
    const response = await api.get<{ results: Product[]; count: number; next: string | null }>('/products/', { params });
    return response.data;
  },
  
  getById: async (id: number) => {
    const response = await api.get<Product>(`/products/${id}/`);
    return response.data;
  },
  
  getInfo: async () => {
    const response = await api.get<ProductInfo>('/products/info/');
    return response.data;
  },

  getTemplates: async () => {
    const response = await api.get<ProductTemplate[]>('/product-templates/');
    return response.data;
  },
  
  create: async (product: Omit<Product, 'id'>) => {
    const response = await api.post<Product>('/products/', product);
    return response.data;
  },
  
  update: async (id: number, product: Partial<Product>) => {
    const response = await api.patch<Product>(`/products/${id}/`, product);
    return response.data;
  },
  
  delete: async (id: number) => {
    await api.delete(`/products/${id}/`);
  },
};

// Orders API
export const ordersAPI = {
  getAll: async (params: {page?: number; page_size?: number; status?: string; created_at__gt?: string; created_at__lt?: string } = { page: 1, page_size: 1000 }) => {
    const response = await api.get<Order[]>('/orders/', { params });
    return response.data;
  },
  
  getById: async (id: string) => {
    const response = await api.get<Order>(`/orders/${id}/`);
    return response.data;
  },
  
  create: async (order: { items: { product: number; quantity: number }[]; status?: string }) => {
    const response = await api.post<Order>('/orders/', order);
    return response.data;
  },
  
  update: async (id: string, data: Partial<Order>) => {
    const response = await api.patch<Order>(`/orders/${id}/`, data);
    return response.data;
  },
  
  delete: async (id: string) => {
    await api.delete(`/orders/${id}/`);
  },
};

// Restock API
export const restockAPI = {
  getQueue: async () => {
    const response = await api.get<RestockItem[]>('/restock/queue/');
    return response.data;
  },
  
  updateStatus: async (id: number, status: RestockItem['status']) => {
    const response = await api.post(`/restock/${id}/update/`, { status });
    return response.data;
  },
  
  // Trigger robot restock command
  triggerRobotRestock: async (restockItem: RestockItem) => {
    const ROS_BRIDGE_URL = import.meta.env.VITE_ROS_BRIDGE_URL || 'http://localhost:9000';

    // Update restock status in backend first
    await restockAPI.updateStatus(restockItem.id, 'IN_PROGRESS');

    // Send command to ROS Bridge
    await api.post(`${ROS_BRIDGE_URL}/restock`, {
      item_id: restockItem.id.toString(),
      product_name: restockItem.product_name,
      shelf_location: restockItem.shelf_location,
      quantity: restockItem.quantity,
    });

    return { status: 'sent' };
  },
};

// Dashboard API
export const dashboardAPI = {
  getData: async () => {
    const response = await api.get('/dashboard/');
    return response.data;
  },
};

export default api;
