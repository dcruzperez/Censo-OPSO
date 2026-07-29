import { LayoutDashboard, Settings, PackageOpen } from 'lucide-react';
import './Sidebar.css';

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <PackageOpen size={28} className="sidebar-logo" />
        <h2>StockFlow</h2>
      </div>
      <nav className="sidebar-nav">
        <ul>
          <li>
            <a href="#" className="nav-item active">
              <LayoutDashboard size={20} />
              <span>Dashboard</span>
            </a>
          </li>
          <li>
            <a href="#" className="nav-item">
              <Settings size={20} />
              <span>Ajustes</span>
            </a>
          </li>
        </ul>
      </nav>
    </aside>
  );
}
