import { useState } from 'react';
import { useQuery, useMutation, useQueryClient, QueryClient} from '@tanstack/react-query';
import { AppLayout } from '@/components/layout/AppLayout';
import { productsAPI, Product } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Search, Plus, Package, Edit, Trash2, ChevronUp, ChevronDown, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const Products = () => {
  const [search, setSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [selectedBaseProduct, setSelectedBaseProduct] = useState<Product | null>(null);
  const [newProduct, setNewProduct] = useState({ name: '', description: '', price: '', stock: 2, shelf_location: '' });
  const [stockValue, setStockValue] = useState([2]);
  const { user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Fetch products using React Query
  const { data: productsData, isLoading, refetch } = useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const response = await productsAPI.getAll();
      return response.results || [];
    },
    staleTime: Infinity, // Cache never becomes stale
    gcTime: Infinity, // Cache is never garbage collected
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
    refetchOnMount: false, // Don't refetch on mount even if stale
    refetchOnReconnect: false, // Don't refetch when reconnecting
  });

  const products = productsData || [];

  // Create product mutation
  const createProductMutation = useMutation({
    mutationFn: (productData: any) => productsAPI.create(productData),
    onSuccess: (product) => {
      queryClient.setQueryData(['products'], (oldData: Product[] | undefined) => {
        if (!oldData) return [product];
        return [product, ...oldData];
      });
      setShowAddModal(false);
      setSelectedBaseProduct(null);
      setNewProduct({ name: '', description: '', price: '', stock: 2, shelf_location: '' });
      setStockValue([2]);
      toast({
        title: 'Success',
        description: 'Product added successfully',
      });
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to add product',
        variant: 'destructive',
      });
    },
  });

  // Update product mutation
  const updateProductMutation = useMutation({
    mutationFn: (data: { id: number; product: Partial<Product> }) => 
      productsAPI.update(data.id, data.product),
    onSuccess: (updatedProduct) => {
      queryClient.setQueryData(['products'], (oldData: Product[] | undefined) => {
        if (!oldData) return [updatedProduct];
        return oldData.map(p => p.id === updatedProduct.id ? updatedProduct : p);
      });
      setShowAddModal(false);
      setEditingProduct(null);
      setSelectedBaseProduct(null);
      setNewProduct({ name: '', description: '', price: '', stock: 2, shelf_location: '' });
      setStockValue([2]);
      toast({
        title: 'Success',
        description: 'Product updated successfully',
      });
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to update product',
        variant: 'destructive',
      });
    },
  });

  // Delete product mutation
  const deleteProductMutation = useMutation({
    mutationFn: (id: number) => productsAPI.delete(id),
    onSuccess: (_, id) => {
      queryClient.setQueryData(['products'], (oldData: Product[] | undefined) => {
        if (!oldData) return [];
        return oldData.filter(p => p.id !== id);
      });
      toast({
        title: 'Success',
        description: 'Product deleted successfully',
      });
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to delete product',
        variant: 'destructive',
      });
    },
  });

  const handleAddProduct = async () => {
    if (!newProduct.name || !newProduct.price || stockValue[0] === undefined) {
      toast({
        title: 'Validation Error',
        description: 'Please fill in all required fields',
        variant: 'destructive',
      });
      return;
    }

    createProductMutation.mutate({
      name: newProduct.name,
      description: newProduct.description,
      price: parseFloat(newProduct.price),
      stock: stockValue[0],
      shelf_location: newProduct.shelf_location,
    });
  };

  const handleEditProduct = async () => {
    if (!editingProduct || !newProduct.name || !newProduct.price || stockValue[0] === undefined) {
      toast({
        title: 'Validation Error',
        description: 'Please fill in all required fields',
        variant: 'destructive',
      });
      return;
    }

    updateProductMutation.mutate({
      id: editingProduct.id!,
      product: {
        name: newProduct.name,
        description: newProduct.description,
        price: parseFloat(newProduct.price),
        stock: stockValue[0],
        shelf_location: newProduct.shelf_location,
      },
    });
  };

  const handleDeleteProduct = async (product: Product) => {
    if (!confirm(`Are you sure you want to delete ${product.name}?`)) return;
    deleteProductMutation.mutate(product.id!);
  };

  const handleSelectBaseProduct = (product: Product) => {
    setSelectedBaseProduct(product);
    setNewProduct({
      name: product.name,
      description: product.description,
      price: product.price.toString(),
      stock: product.stock,
      shelf_location: product.shelf_location || '',
    });
    setStockValue([product.stock]);
  };

  const handleCloseModal = () => {
    setShowAddModal(false);
    setEditingProduct(null);
    setSelectedBaseProduct(null);
    setNewProduct({ name: '', description: '', price: '', stock: 2, shelf_location: '' });
    setStockValue([2]);
  };

  const filteredProducts = products.filter(p => 
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.description.toLowerCase().includes(search.toLowerCase())
  );

  const getStockBadge = (stock: number) => {
    if (stock === 0) {
      return <Badge variant="destructive">Out of Stock</Badge>;
    }
    if (stock <= 1) {
      return <Badge className="bg-warning text-warning-foreground">Low Stock</Badge>;
    }
    return <Badge className="bg-success text-success-foreground">In Stock</Badge>;
  };

  const formatPrice = (price: number | string) => {
    const numPrice = typeof price === 'string' ? parseFloat(price) : price;
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
    }).format(numPrice);
  };

  return (
    <AppLayout title="Products" subtitle="Manage your product inventory">
      <div className="bg-card rounded-xl border border-border">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 border-b border-border">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search products..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Button 
              variant="outline" 
              size="icon"
              onClick={() => refetch()}
              title="Refresh products list"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
            {user?.is_staff && (
              <Button className="gap-2" onClick={() => setShowAddModal(true)}>
                <Plus className="w-4 h-4" />
                Add Product
              </Button>
            )}
          </div>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Stock</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredProducts.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    No products found
                  </TableCell>
                </TableRow>
              ) : (
                filteredProducts.map((product) => (
                  <TableRow key={product.id || product.name}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                          <Package className="w-5 h-5 text-muted-foreground" />
                        </div>
                        <span className="font-medium">{product.name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground max-w-xs truncate">
                      {product.description}
                    </TableCell>
                    <TableCell className="font-medium">{formatPrice(typeof product.price === 'string' ? parseFloat(product.price) : product.price)}</TableCell>
                    <TableCell>
                      <span className={cn(
                        "font-semibold",
                        product.stock === 0 && "text-destructive",
                        product.stock > 0 && product.stock <= 1 && "text-warning",
                        product.stock > 1 && "text-foreground"
                      )}>
                        {product.stock}
                      </span>
                    </TableCell>
                    <TableCell>{getStockBadge(product.stock)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button 
                          variant="ghost" 
                          size="icon"
                          onClick={() => {
                            setEditingProduct(product);
                            setNewProduct({
                              name: product.name,
                              description: product.description,
                              price: product.price.toString(),
                              stock: product.stock,
                              shelf_location: product.shelf_location || '',
                            });
                            setStockValue([product.stock]);
                            setShowAddModal(true);
                          }}
                        >
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="text-destructive hover:text-destructive"
                          onClick={() => handleDeleteProduct(product)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Add/Edit Product Modal */}
      <Dialog open={showAddModal} onOpenChange={(open) => {
        if (!open) {
          handleCloseModal();
        }
      }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingProduct ? 'Edit Product' : 'Add New Product'}</DialogTitle>
            <DialogDescription>
              {editingProduct ? 'Update the product details.' : 'Select an existing product or customize the details for a new product.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-6">
            {!editingProduct && (
              <div>
                <Label htmlFor="base-product">Select Existing Product (Optional)</Label>
                <Select 
                  value={selectedBaseProduct?.id?.toString() || 'none'} 
                  onValueChange={(id) => {
                    if (id && id !== 'none') {
                      const product = products.find(p => p.id === parseInt(id));
                      if (product) handleSelectBaseProduct(product);
                    } else {
                      setSelectedBaseProduct(null);
                      setNewProduct({ name: '', description: '', price: '', stock: 2, shelf_location: '' });
                      setStockValue([2]);
                    }
                  }}
                >
                  <SelectTrigger id="base-product">
                    <SelectValue placeholder="Choose a product to copy from..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {products.map((product) => (
                      <SelectItem key={product.id} value={product.id!.toString()}>
                        {product.name} - {formatPrice(product.price)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="name">Product Name</Label>
                <Select 
                  value={newProduct.name} 
                  onValueChange={(name) => {
                    const selectedProd = products.find(p => p.name === name);
                    if (selectedProd) {
                      setNewProduct(prev => ({ 
                        ...prev, 
                        name: selectedProd.name,
                        description: selectedProd.description,
                        price: selectedProd.price.toString(),
                        shelf_location: selectedProd.shelf_location || prev.shelf_location
                      }));
                    }
                  }}
                >
                  <SelectTrigger id="name">
                    <SelectValue placeholder="Select product name..." />
                  </SelectTrigger>
                  <SelectContent>
                    {products.map((product) => (
                      <SelectItem key={product.id} value={product.name}>
                        {product.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="price">Price</Label>
                <Select 
                  value={newProduct.price} 
                  onValueChange={(price) => {
                    setNewProduct(prev => ({ ...prev, price }));
                  }}
                >
                  <SelectTrigger id="price">
                    <SelectValue placeholder="Select price..." />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from(new Set(products.map(p => p.price.toString()))).map((price) => (
                      <SelectItem key={price} value={price}>
                        {formatPrice(parseFloat(price))}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label htmlFor="description">Description</Label>
              <Select 
                value={newProduct.description} 
                onValueChange={(description) => {
                  setNewProduct(prev => ({ ...prev, description }));
                }}
              >
                <SelectTrigger id="description">
                  <SelectValue placeholder="Select description..." />
                </SelectTrigger>
                <SelectContent>
                  {Array.from(new Set(products.map(p => p.description).filter(desc => desc && desc.trim()))).map((desc) => (
                    <SelectItem key={desc} value={desc}>
                      {desc.substring(0, 50)}{desc.length > 50 ? '...' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="shelf_location">Shelf Location</Label>
              <Select 
                value={newProduct.shelf_location || 'none'} 
                onValueChange={(shelf_location) => {
                  setNewProduct(prev => ({ ...prev, shelf_location: shelf_location === 'none' ? '' : shelf_location }));
                }}
              >
                <SelectTrigger id="shelf_location">
                  <SelectValue placeholder="Select shelf location..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {Array.from(new Set(products.filter(p => p.shelf_location).map(p => p.shelf_location!))).map((location) => (
                    <SelectItem key={location} value={location}>
                      {location}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <div className="flex items-center justify-between mb-3">
                <Label htmlFor="stock">Stock Quantity</Label>
                <div className="text-lg font-semibold text-primary">{stockValue[0]} units</div>
              </div>
              <div className="flex items-center gap-4 px-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => setStockValue([Math.max(0, stockValue[0] - 1)])}
                >
                  <ChevronDown className="w-4 h-4" />
                </Button>
                <Slider
                  id="stock"
                  min={0}
                  max={100}
                  step={1}
                  value={stockValue}
                  onValueChange={setStockValue}
                  className="flex-1"
                />
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => setStockValue([Math.min(100, stockValue[0] + 1)])}
                >
                  <ChevronUp className="w-4 h-4" />
                </Button>
              </div>
              <div className="flex gap-2 mt-3 text-xs text-muted-foreground">
                <button 
                  onClick={() => setStockValue([5])}
                  className="px-2 py-1 rounded border border-border hover:bg-accent"
                >
                  5
                </button>
                <button 
                  onClick={() => setStockValue([10])}
                  className="px-2 py-1 rounded border border-border hover:bg-accent"
                >
                  10
                </button>
                <button 
                  onClick={() => setStockValue([20])}
                  className="px-2 py-1 rounded border border-border hover:bg-accent"
                >
                  20
                </button>
                <button 
                  onClick={() => setStockValue([50])}
                  className="px-2 py-1 rounded border border-border hover:bg-accent"
                >
                  50
                </button>
                <button 
                  onClick={() => setStockValue([100])}
                  className="px-2 py-1 rounded border border-border hover:bg-accent"
                >
                  100
                </button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={handleCloseModal}>
              Cancel
            </Button>
            <Button onClick={editingProduct ? handleEditProduct : handleAddProduct}>
              {editingProduct ? 'Update' : 'Add'} Product
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
};

export default Products;
function useEffect(arg0: () => () => void, arg1: QueryClient[]) {
  throw new Error('Function not implemented.');
}

