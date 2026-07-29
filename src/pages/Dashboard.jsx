import { useState, useEffect } from 'react';
import { Plus } from 'lucide-react';
import Sidebar from '../components/Sidebar';
import TopNav from '../components/TopNav';
import ProductModal from '../components/ProductModal';
import InventoryModal from '../components/InventoryModal';
import DeleteModal from '../components/DeleteModal';
import './Dashboard.css';

export default function Dashboard() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [products, setProducts] = useState(() => {
    const saved = localStorage.getItem('stockflow_products');
    if (saved) {
      return JSON.parse(saved);
    }
    return [
      { id: 1, sku: 'PROD-001', name: 'Laptop Pro 15', category: 'Electrónica', price: 1200.00, stock: 10, critical: 5 },
      { id: 2, sku: 'PROD-002', name: 'Silla Ergonómica', category: 'Mobiliario', price: 150.00, stock: 2, critical: 3 }
    ];
  });

  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [isInventoryModalOpen, setIsInventoryModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  
  const [editingProduct, setEditingProduct] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);

  useEffect(() => {
    localStorage.setItem('stockflow_products', JSON.stringify(products));
  }, [products]);

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);

  const handleAddProduct = () => {
    setEditingProduct(null);
    setIsProductModalOpen(true);
  };

  const handleEditProduct = (product) => {
    setEditingProduct(product);
    setIsProductModalOpen(true);
  };

  const handleSaveProduct = (productData) => {
    if (editingProduct) {
      setProducts(products.map(p => p.id === editingProduct.id ? { ...p, ...productData } : p));
    } else {
      const newProduct = {
        id: Date.now(),
        ...productData,
        price: 0,
        stock: 0,
        critical: 0
      };
      setProducts([...products, newProduct]);
    }
  };

  const handleOpenInventory = (product) => {
    setSelectedProduct(product);
    setIsInventoryModalOpen(true);
  };

  const handleSaveInventory = (invData) => {
    setProducts(products.map(p => p.id === selectedProduct.id ? { ...p, ...invData } : p));
  };

  const handleOpenDelete = (product) => {
    setSelectedProduct(product);
    setIsDeleteModalOpen(true);
  };

  const handleConfirmDelete = () => {
    setProducts(products.filter(p => p.id !== selectedProduct.id));
    setIsDeleteModalOpen(false);
  };

  return (
    <div className="dashboard-layout">
      <div className={`sidebar-overlay ${isSidebarOpen ? 'show' : ''}`} onClick={toggleSidebar}></div>
      
      <div className={`sidebar-container ${isSidebarOpen ? 'open' : ''}`}>
        <Sidebar />
      </div>
      
      <div className="main-content">
        <TopNav toggleSidebar={toggleSidebar} />
        
        <main className="dashboard-body">
          <div className="page-header">
            <h1>Resumen General</h1>
          </div>

          <div className="card glass">
            <div className="card-header">
              <h2>Mis Productos</h2>
              <button className="btn btn-primary" onClick={handleAddProduct}>
                <Plus size={18} />
                <span>Agregar Producto</span>
              </button>
            </div>
            <div className="card-body">
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Nombre del Producto</th>
                      <th>Categoría</th>
                      <th className="text-end">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.length === 0 ? (
                      <tr>
                        <td colSpan="4" className="text-center text-muted" style={{ padding: '2rem 0' }}>
                          No hay productos registrados.
                        </td>
                      </tr>
                    ) : (
                      products.map(prod => (
                        <tr key={prod.id}>
                          <td className="fw-bold">{prod.sku}</td>
                          <td>{prod.name}</td>
                          <td><span className="badge badge-primary">{prod.category}</span></td>
                          <td className="text-end actions-cell">
                            <button className="btn btn-outline" onClick={() => handleOpenInventory(prod)}>Inventario</button>
                            <button className="btn btn-outline text-info" onClick={() => handleEditProduct(prod)}>Editar</button>
                            <button className="btn btn-outline text-danger" onClick={() => handleOpenDelete(prod)}>Eliminar</button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="card glass mt-4">
            <div className="card-header">
              <h2>Inventario y Precios</h2>
            </div>
            <div className="card-body">
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Nombre</th>
                      <th>Categoría</th>
                      <th>Precio</th>
                      <th>Stock Actual</th>
                      <th>Stock Crítico</th>
                      <th className="text-end">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.length === 0 ? (
                      <tr>
                        <td colSpan="7" className="text-center text-muted" style={{ padding: '2rem 0' }}>
                          No hay productos en inventario.
                        </td>
                      </tr>
                    ) : (
                      products.map(prod => {
                        const isCritical = prod.stock <= prod.critical;
                        return (
                          <tr key={`inv-${prod.id}`}>
                            <td className="fw-bold">{prod.sku}</td>
                            <td>{prod.name}</td>
                            <td><span className="badge badge-secondary">{prod.category}</span></td>
                            <td>${parseFloat(prod.price).toFixed(2)}</td>
                            <td>
                              {isCritical ? (
                                <span className="badge badge-danger spin-alert" style={{ fontSize: '0.875rem' }}>{prod.stock}</span>
                              ) : (
                                <span className="fw-bold text-success">{prod.stock}</span>
                              )}
                            </td>
                            <td>{prod.critical}</td>
                            <td className="text-end actions-cell">
                              <button className="btn btn-outline text-info" onClick={() => handleOpenInventory(prod)}>Editar</button>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </main>
      </div>

      <ProductModal 
        isOpen={isProductModalOpen} 
        onClose={() => setIsProductModalOpen(false)} 
        onSave={handleSaveProduct}
        editingProduct={editingProduct}
      />

      <InventoryModal
        isOpen={isInventoryModalOpen}
        onClose={() => setIsInventoryModalOpen(false)}
        onSave={handleSaveInventory}
        product={selectedProduct}
      />

      <DeleteModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleConfirmDelete}
        product={selectedProduct}
      />
    </div>
  );
}
