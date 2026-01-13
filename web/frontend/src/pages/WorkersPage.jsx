import React, { useState, useEffect } from 'react';
import { Server, Plus, X, Trash2, RefreshCw } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { workersAPI } from '../services/api';

const WorkersPage = () => {
  const [workers, setWorkers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const [newWorkerIP, setNewWorkerIP] = useState('');

  useEffect(() => {
    fetchWorkers();
  }, []);

  const fetchWorkers = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await workersAPI.list();
      setWorkers(response.data.data);
    } catch (err) {
      // If not in controller mode, show appropriate message
      if (err.response?.status === 400) {
        setError('Worker management only available in controller mode');
      } else {
        setError(err.response?.data?.detail || 'Failed to fetch workers');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAddWorker = async (e) => {
    e.preventDefault();
    setAdding(true);
    setAddError(null);

    try {
      await workersAPI.add({ ip_address: newWorkerIP });
      setShowAddModal(false);
      setNewWorkerIP('');
      fetchWorkers();
    } catch (err) {
      setAddError(err.response?.data?.detail || 'Failed to add worker');
    } finally {
      setAdding(false);
    }
  };

  const handleRemoveWorker = async (workerId) => {
    if (!confirm('Are you sure you want to remove this worker?')) return;

    try {
      await workersAPI.remove(workerId);
      fetchWorkers();
    } catch (err) {
      console.error('Failed to remove worker:', err);
    }
  };

  const openAddModal = () => {
    setAddError(null);
    setNewWorkerIP('');
    setShowAddModal(true);
  };

  if (loading) return <LoadingSpinner size="lg" message="Loading workers..." />;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Workers</h1>
          <p className="text-gray-400 mt-1">Monitor and manage distributed workers</p>
        </div>
        <div className="flex items-center space-x-3">
          {!error && (
            <>
              <button
                onClick={fetchWorkers}
                className="btn btn-secondary flex items-center space-x-2"
              >
                <RefreshCw className="h-4 w-4" />
                <span>Refresh</span>
              </button>
              <button
                onClick={openAddModal}
                className="btn btn-primary flex items-center space-x-2"
              >
                <Plus className="h-4 w-4" />
                <span>Add Worker</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Add Worker Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-md mx-4 border border-gray-700">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">Add Worker</h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-gray-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {addError && (
              <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-2 rounded mb-4">
                {addError}
              </div>
            )}

            <form onSubmit={handleAddWorker} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Worker IP Address *
                </label>
                <input
                  type="text"
                  value={newWorkerIP}
                  onChange={(e) => setNewWorkerIP(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                  placeholder="192.168.1.100"
                  required
                  pattern="^(\d{1,3}\.){3}\d{1,3}$"
                  title="Enter a valid IP address (e.g., 192.168.1.100)"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Enter the IP address of the worker machine running fawkes-worker
                </p>
              </div>

              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={adding}
                  className="btn btn-primary disabled:opacity-50"
                >
                  {adding ? 'Adding...' : 'Add Worker'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {error ? (
        <div className="card bg-yellow-900/20 border border-yellow-800">
          <div className="text-center py-8">
            <Server className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
            <p className="text-yellow-400">{error}</p>
            <p className="text-sm text-gray-400 mt-2">
              Switch to controller mode to manage workers
            </p>
          </div>
        </div>
      ) : workers.length === 0 ? (
        <div className="card">
          <div className="text-center py-12">
            <Server className="h-12 w-12 text-gray-500 mx-auto mb-4 opacity-50" />
            <p className="text-gray-400">No workers registered</p>
            <p className="text-sm text-gray-500 mt-1 mb-4">
              Add worker machines to distribute fuzzing workload
            </p>
            <button onClick={openAddModal} className="btn btn-primary">
              Register your first worker
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="card text-center">
              <p className="text-sm text-gray-400 uppercase">Total Workers</p>
              <p className="mt-2 text-3xl font-bold text-white">{workers.length}</p>
            </div>
            <div className="card text-center">
              <p className="text-sm text-gray-400 uppercase">Online</p>
              <p className="mt-2 text-3xl font-bold text-green-400">
                {workers.filter((w) => w.status === 'online').length}
              </p>
            </div>
            <div className="card text-center">
              <p className="text-sm text-gray-400 uppercase">Offline</p>
              <p className="mt-2 text-3xl font-bold text-red-400">
                {workers.filter((w) => w.status === 'offline').length}
              </p>
            </div>
            <div className="card text-center">
              <p className="text-sm text-gray-400 uppercase">Busy</p>
              <p className="mt-2 text-3xl font-bold text-yellow-400">
                {workers.filter((w) => w.status === 'busy').length}
              </p>
            </div>
          </div>

          {/* Workers Table */}
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>IP Address</th>
                  <th>Status</th>
                  <th>Current Job</th>
                  <th>Last Seen</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {workers.map((worker) => (
                  <tr key={worker.worker_id}>
                    <td>#{worker.worker_id}</td>
                    <td className="font-medium">{worker.ip_address}</td>
                    <td>
                      <span
                        className={`badge ${
                          worker.status === 'online'
                            ? 'badge-success'
                            : worker.status === 'busy'
                            ? 'badge-warning'
                            : 'badge-danger'
                        }`}
                      >
                        {worker.status || 'unknown'}
                      </span>
                    </td>
                    <td className="text-sm text-gray-400">
                      {worker.current_job_id ? `Job #${worker.current_job_id}` : '-'}
                    </td>
                    <td className="text-sm text-gray-400">
                      {worker.last_seen
                        ? new Date(worker.last_seen * 1000).toLocaleString()
                        : 'Never'}
                    </td>
                    <td>
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleRemoveWorker(worker.worker_id)}
                          className="p-2 text-red-400 hover:bg-red-900/20 rounded transition-colors"
                          title="Remove Worker"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default WorkersPage;
