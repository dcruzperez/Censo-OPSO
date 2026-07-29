import { useState, useEffect } from 'react';
import { PackagePlus, X } from 'lucide-react';
import './Modal.css';

export default function ProductModal({ isOpen, onClose, onSave, editingProduct }) {
  const [sku, setSku] = useState('');
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (editingProduct) {
      setSku(editingProduct.sku || '');
      setName(editingProduct.name || '');
      setCategory(editingProduct.category || '');
    } else {
      setSku('');
      setName('');
      setCategory('');
    }
    setErrors({});
  }, [editingProduct, isOpen]);

  if (!isOpen) return null;

  const validate = () => {
    const newErrors = {};
    if (!sku.trim()) newErrors.sku = 'El SKU es requerido';
    if (!name.trim()) newErrors.name = 'El nombre es obligatorio';
    if (!category.trim()) newErrors.category = 'La categoría es obligatoria';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (validate()) {
      onSave({ sku, name, category });
      onClose();
    }
  };

  return (
    <div className="modal-backdrop animate-fade-in">
      <div className="modal-content glass">
        <div className="modal-header">
          <h3>{editingProduct ? 'Editar Producto' : 'Nuevo Producto'}</h3>
          <button className="btn-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <form onSubmit={handleSubmit} noValidate>
            <div className="input-group">
              <label className="input-label">SKU</label>
              <input
                type="text"
                className={`input-field ${errors.sku ? 'input-error' : ''}`}
                placeholder="Ej. PROD-123"
                value={sku}
                onChange={(e) => { setSku(e.target.value); if(errors.sku) setErrors({...errors, sku: null}) }}
              />
              {errors.sku && <span className="error-text">{errors.sku}</span>}
            </div>
            
            <div className="input-group">
              <label className="input-label">Nombre del Producto</label>
              <input
                type="text"
                className={`input-field ${errors.name ? 'input-error' : ''}`}
                placeholder="Ej. Teclado Mecánico"
                value={name}
                onChange={(e) => { setName(e.target.value); if(errors.name) setErrors({...errors, name: null}) }}
              />
              {errors.name && <span className="error-text">{errors.name}</span>}
            </div>

            <div className="input-group" style={{ marginBottom: '1.5rem' }}>
              <label className="input-label">Categoría</label>
              <input
                type="text"
                className={`input-field ${errors.category ? 'input-error' : ''}`}
                placeholder="Ej. Informática"
                value={category}
                onChange={(e) => { setCategory(e.target.value); if(errors.category) setErrors({...errors, category: null}) }}
              />
              {errors.category && <span className="error-text">{errors.category}</span>}
            </div>

            <div className="modal-footer">
              <button type="button" className="btn btn-outline" onClick={onClose}>Cancelar</button>
              <button type="submit" className="btn btn-primary">
                <PackagePlus size={18} />
                <span>Guardar Producto</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
