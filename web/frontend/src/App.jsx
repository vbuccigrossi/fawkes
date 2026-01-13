import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Navbar from './components/common/Navbar';
import DashboardPage from './pages/DashboardPage';
import LoginPage from './pages/LoginPage';
import JobsPage from './pages/JobsPage';
import CrashesPage from './pages/CrashesPage';
import WorkersPage from './pages/WorkersPage';
import ConfigPage from './pages/ConfigPage';
import VMViewerPage from './pages/VMViewerPage';
import VMSetupPage from './pages/VMSetupPage';
import VMRunnerPage from './pages/VMRunnerPage';
import { authAPI, getAuthToken } from './services/api';
import wsClient from './services/websocket';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    // Connect to WebSocket if authenticated
    if (user) {
      wsClient.connect();
    } else {
      wsClient.disconnect();
    }

    return () => {
      wsClient.disconnect();
    };
  }, [user]);

  const checkAuth = async () => {
    const token = getAuthToken();

    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const response = await authAPI.getMe();
      setUser(response.data);
    } catch (error) {
      console.error('Auth check failed:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="h-12 w-12 border-4 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="mt-4 text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-900">
        {user ? (
          <>
            <Navbar user={user} />
            <main className="max-w-full mx-auto">
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/jobs" element={<JobsPage />} />
                <Route path="/crashes" element={<CrashesPage />} />
                <Route path="/workers" element={<WorkersPage />} />
                <Route path="/config" element={<ConfigPage />} />
                <Route path="/vm-viewer" element={<VMViewerPage />} />
                <Route path="/vm-setup" element={<VMSetupPage />} />
                <Route path="/vm-runner" element={<VMRunnerPage />} />
                <Route path="/login" element={<Navigate to="/" replace />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </>
        ) : (
          <Routes>
            <Route path="/login" element={<LoginPage onLogin={setUser} />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        )}
      </div>
    </BrowserRouter>
  );
}

export default App;
