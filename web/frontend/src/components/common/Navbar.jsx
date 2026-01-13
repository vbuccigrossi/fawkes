import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogOut, Activity, Monitor } from 'lucide-react';
import { clearAuthToken } from '../../services/api';

const Navbar = ({ user }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    clearAuthToken();
    navigate('/login');
  };

  return (
    <nav className="bg-gray-800 border-b border-gray-700">
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center">
            <Link to="/" className="flex items-center space-x-3">
              <Activity className="h-8 w-8 text-primary-500" />
              <div>
                <h1 className="text-xl font-bold text-white">Fawkes</h1>
                <p className="text-xs text-gray-400">Fuzzer Dashboard</p>
              </div>
            </Link>
          </div>

          {/* Navigation Links */}
          <div className="hidden md:flex md:items-center md:space-x-4">
            <NavLink to="/">Dashboard</NavLink>
            <NavLink to="/jobs">Jobs</NavLink>
            <NavLink to="/crashes">Crashes</NavLink>
            <NavLink to="/workers">Workers</NavLink>
            <NavLink to="/vm-viewer">VM Viewer</NavLink>
            <NavLink to="/vm-setup">VM Setup</NavLink>
            <NavLink to="/vm-runner">VM Runner</NavLink>
            <NavLink to="/config">Config</NavLink>
          </div>

          {/* User Menu */}
          <div className="flex items-center space-x-4">
            {user && (
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-300">{user.username}</span>
                <span className="badge badge-info text-xs">{user.role}</span>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center space-x-2 px-3 py-2 text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
            >
              <LogOut className="h-4 w-4" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
};

const NavLink = ({ to, children }) => {
  return (
    <Link
      to={to}
      className="px-3 py-2 text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
    >
      {children}
    </Link>
  );
};

export default Navbar;
