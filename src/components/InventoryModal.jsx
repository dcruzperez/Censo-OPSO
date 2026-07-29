import { useState, useEffect } from 'react';
import { Save, X } from 'lucide-react';
import './Modal.css';

export default function InventoryModal({ isOpen, onClose, onSave, product }) {
  const [price, setPrice] = useState('');
  const [stock, setStock] = useState('');
  const [critical, setCritical] = useState('');
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (product) {
      setPrice(product.price || 0);
      setStock(product.stock || 0);
      setCritical(product.critical || 0);
    }
    setErrors({});
  }, [product, isOpen]);

  if (!isOpen || !product) return null;

  const validate = () => {
    const newErrors = {};
    const priceVal = parseFloat(price);
    const stockVal = parseInt(stock);
    const criticalVal = parseInt(critical);

    if (isNaN(priceVal) || priceVal < 0) newErrors.price = 'Ingresa un precio válido';
    if (isNaN(stockVal) || stockVal < 0) newErrors.stock = 'Requerido';
    if (isNaN(criticalVal) || criticalVal < 0) newErrors.critical = 'Requerido';

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (validate()) {
      onSave({ price: parseFloat(price), stock: parseInt(stock), critical: parseInt(critical) });
      onClose();
    }
  };

  return (
    <div className="modal-backdrop animate-fade-in">
      <div className="modal-content glass">
        <div className="modal-header">
          <h3>Registrar Inventario</h3>
          <button className="btn-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <p className="text-muted" style={{ marginBottom: '1.5rem', fontWeight: 500 }}>
            {product.sku} - {product.name}
          </p>
          <form onSubmit={handleSubmit} noValidate>
            <div className="input-group">
              <label className="input-label">Precio ($)</label>
              <input
                type="number"
                min="0"
                step="0.01"
                className={`input-field ${errors.price ? 'input-error' : ''}`}
                value={price}
                onChange={(e) => { setPrice(e.target.value); if(errors.price) setErrors({...errors, price: null}) }}
              />
              {errors.price && <span className="error-text">{errors.price}</span>}
            </div>
            
            <div style={{ display: 'flex', gap: '1rem' }}>
              <div className="input-group" style={{ flex: 1 }}>
                <label className="input-label">Stock Actual</label>
                <input
                  type="number"
                  min="0"
                  className={`input-field ${errors.stock ? 'input-error' : ''}`}
                  value={stock}
                  onChange={(e) => { setStock(e.target.value); if(errors.stock) setErrors({...errors, stock: null}) }}
                />
                {errors.stock && <span className="error-text">{errors.stock}</span>}
              </div>

              <div className="input-group" style={{ flex: 1, marginBottom: '1.5rem' }}>
                <label className="input-label">Stock Crítico</label>
                <input
                  type="number"
                  min="0"
                  className={`input-field ${errors.critical ? 'input-error' : ''}`}
                  value={critical}
                  onChange={(e) => { setCritical(e.target.value); if(errors.critical) setErrors({...errors, critical: null}) }}
                />
                {errors.critical && <span className="error-text">{errors.critical}</span>}
              </div>
            </div>

            <div className="modal-footer">
              <button type="button" className="btn btn-outline" onClick={onClose}>Cancelar</button>
              <button type="submit" className="btn btn-success">
                <Save size={18} />
                <span>Guardar Inventario</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
