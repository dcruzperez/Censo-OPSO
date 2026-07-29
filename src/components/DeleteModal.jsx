import { Trash2, X } from 'lucide-react';
import './Modal.css';

export default function DeleteModal({ isOpen, onClose, onConfirm, product }) {
  if (!isOpen || !product) return null;

  return (
    <div className="modal-backdrop animate-fade-in">
      <div className="modal-content glass" style={{ maxWidth: '400px' }}>
        <div className="modal-header">
          <h3 className="text-danger">Confirmar Eliminación</h3>
          <button className="btn-close" onClick={onClose}><X size={20} /></button>
        </div>
        <div className="modal-body">
          <p>¿Estás seguro de que deseas eliminar este producto?</p>
          <p className="fw-bold" style={{ margin: '1rem 0 0 0' }}>
            {product.sku} - {product.name}
          </p>
        </div>
        <div className="modal-footer">
          <button className="btn btn-outline" onClick={onClose}>Cancelar</button>
          <button className="btn btn-danger" onClick={onConfirm}>
            <Trash2 size={18} />
            <span>Eliminar</span>
          </button>
        </div>
      </div>
    </div>
  );
}
