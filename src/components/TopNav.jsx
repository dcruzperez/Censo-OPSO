import { LogOut, Menu, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import './TopNav.css';

export default function TopNav({ toggleSidebar }) {
  const navigate = useNavigate();

  const handleLogout = () => {
    navigate('/login');
  };

  return (
    <header className="topnav glass">
      <div className="topnav-left">
        <button className="menu-btn d-md-none" onClick={toggleSidebar}>
          <Menu size={24} />
        </button>
      </div>
      <div className="topnav-right">
        <div className="user-profile">
          <div className="avatar">
            <User size={18} />
          </div>
          <span className="user-name">Administrador</span>
        </div>
        <button className="btn btn-ghost logout-btn" onClick={handleLogout}>
          <LogOut size={18} />
          <span>Cerrar Sesión</span>
        </button>
      </div>
    </header>
  );
}
