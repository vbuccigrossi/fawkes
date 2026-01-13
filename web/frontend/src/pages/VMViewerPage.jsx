import React, { useState, useEffect, useCallback } from 'react';
import { Monitor, RefreshCw, Settings, AlertCircle, Play, Square, Eye, EyeOff } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { vmsAPI, configAPI } from '../services/api';

const VMViewerPage = () => {
  const [vms, setVms] = useState([]);
  const [screenshots, setScreenshots] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [screenshotStatus, setScreenshotStatus] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(5);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Fetch VM list
  const fetchVMs = useCallback(async () => {
    try {
      const response = await vmsAPI.list();
      setVms(response.data.data || []);
    } catch (err) {
      console.error('Failed to fetch VMs:', err);
    }
  }, []);

  // Fetch screenshot status
  const fetchScreenshotStatus = useCallback(async () => {
    try {
      const response = await vmsAPI.getScreenshotStatus();
      setScreenshotStatus(response.data.data);
      if (response.data.data?.interval) {
        setRefreshInterval(response.data.data.interval);
      }
    } catch (err) {
      console.error('Failed to fetch screenshot status:', err);
    }
  }, []);

  // Fetch all screenshots
  const fetchScreenshots = useCallback(async () => {
    try {
      const response = await vmsAPI.getAllScreenshots();
      if (response.data.success) {
        setScreenshots(response.data.data || {});
        setLastUpdate(new Date());
      }
    } catch (err) {
      console.error('Failed to fetch screenshots:', err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        await Promise.all([fetchVMs(), fetchScreenshotStatus(), fetchScreenshots()]);
      } catch (err) {
        setError('Failed to load VM data');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [fetchVMs, fetchScreenshotStatus, fetchScreenshots]);

  // Auto-refresh screenshots
  useEffect(() => {
    if (!autoRefresh || !screenshotStatus?.enabled) return;

    const interval = setInterval(() => {
      fetchScreenshots();
      fetchVMs();
    }, refreshInterval * 1000);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, screenshotStatus?.enabled, fetchScreenshots, fetchVMs]);

  // Manual refresh
  const handleRefresh = async () => {
    await Promise.all([fetchVMs(), fetchScreenshots()]);
  };

  // Get running VMs with screenshots
  const runningVMs = vms.filter(vm => vm.status === 'Running');
  const vmsWithScreenshots = runningVMs.filter(vm => vm.screenshots_enabled);

  if (loading) return <LoadingSpinner size="lg" message="Loading VM viewer..." />;
  if (error) return <ErrorMessage message={error} onRetry={() => window.location.reload()} />;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">VM Viewer</h1>
          <p className="text-gray-400 mt-1">Live screenshots of running virtual machines</p>
        </div>
        <div className="flex items-center space-x-4">
          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center space-x-2 px-3 py-2 rounded-lg transition-colors ${
              autoRefresh
                ? 'bg-green-900/30 text-green-400 border border-green-700'
                : 'bg-gray-700 text-gray-400 border border-gray-600'
            }`}
          >
            {autoRefresh ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            <span className="text-sm">Auto-refresh {autoRefresh ? 'ON' : 'OFF'}</span>
          </button>

          {/* Manual refresh */}
          <button
            onClick={handleRefresh}
            className="btn btn-secondary flex items-center space-x-2"
          >
            <RefreshCw className="h-4 w-4" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Status Banner */}
      {!screenshotStatus?.enabled && (
        <div className="bg-yellow-900/20 border border-yellow-600 rounded-lg p-4 flex items-start space-x-3">
          <AlertCircle className="h-5 w-5 text-yellow-400 mt-0.5" />
          <div>
            <h3 className="text-yellow-400 font-medium">Screenshots Disabled</h3>
            <p className="text-yellow-200/70 text-sm mt-1">
              VM screenshots are currently disabled. Enable them in the Config page by setting
              <code className="bg-gray-800 px-1 mx-1 rounded">enable_vm_screenshots</code> to true.
              This feature adds a VNC display to VMs for visual monitoring.
            </p>
          </div>
        </div>
      )}

      {/* Stats Bar */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card bg-gray-800/50">
          <div className="flex items-center space-x-3">
            <Monitor className="h-8 w-8 text-blue-400" />
            <div>
              <p className="text-2xl font-bold text-white">{vms.length}</p>
              <p className="text-sm text-gray-400">Total VMs</p>
            </div>
          </div>
        </div>
        <div className="card bg-gray-800/50">
          <div className="flex items-center space-x-3">
            <Play className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-2xl font-bold text-white">{runningVMs.length}</p>
              <p className="text-sm text-gray-400">Running</p>
            </div>
          </div>
        </div>
        <div className="card bg-gray-800/50">
          <div className="flex items-center space-x-3">
            <Eye className="h-8 w-8 text-purple-400" />
            <div>
              <p className="text-2xl font-bold text-white">{vmsWithScreenshots.length}</p>
              <p className="text-sm text-gray-400">With Screenshots</p>
            </div>
          </div>
        </div>
        <div className="card bg-gray-800/50">
          <div className="flex items-center space-x-3">
            <RefreshCw className="h-8 w-8 text-orange-400" />
            <div>
              <p className="text-2xl font-bold text-white">{refreshInterval}s</p>
              <p className="text-sm text-gray-400">Refresh Interval</p>
            </div>
          </div>
        </div>
      </div>

      {/* Last update time */}
      {lastUpdate && (
        <p className="text-sm text-gray-500">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </p>
      )}

      {/* Screenshot Grid */}
      {vmsWithScreenshots.length === 0 ? (
        <div className="card text-center py-12">
          <Monitor className="h-16 w-16 mx-auto text-gray-600 mb-4" />
          <h3 className="text-xl text-gray-400 mb-2">No VMs with Screenshots</h3>
          <p className="text-gray-500 max-w-md mx-auto">
            {runningVMs.length === 0
              ? 'No VMs are currently running. Start a job to see VM screenshots.'
              : 'Running VMs do not have screenshots enabled. Enable screenshots in Config and restart the job.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {vmsWithScreenshots.map((vm) => (
            <VMScreenshotCard
              key={vm.vm_id}
              vm={vm}
              screenshot={screenshots[String(vm.vm_id)]}
            />
          ))}
        </div>
      )}

      {/* All VMs Table (collapsed by default) */}
      <details className="card">
        <summary className="cursor-pointer text-lg font-medium text-white hover:text-blue-400 transition-colors">
          All VMs ({vms.length})
        </summary>
        <div className="mt-4 overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>VM ID</th>
                <th>Status</th>
                <th>Arch</th>
                <th>PID</th>
                <th>Screenshots</th>
                <th>VNC Port</th>
                <th>Monitor Port</th>
              </tr>
            </thead>
            <tbody>
              {vms.map((vm) => (
                <tr key={vm.vm_id}>
                  <td>#{vm.vm_id}</td>
                  <td>
                    <span
                      className={`badge ${
                        vm.status === 'Running' ? 'badge-success' : 'badge-gray'
                      }`}
                    >
                      {vm.status}
                    </span>
                  </td>
                  <td className="text-gray-400">{vm.arch}</td>
                  <td className="text-gray-400">{vm.pid || '-'}</td>
                  <td>
                    {vm.screenshots_enabled ? (
                      <span className="text-green-400">Enabled</span>
                    ) : (
                      <span className="text-gray-500">Disabled</span>
                    )}
                  </td>
                  <td className="text-gray-400">{vm.vnc_port || '-'}</td>
                  <td className="text-gray-400">{vm.monitor_port || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
};

// Individual VM Screenshot Card
const VMScreenshotCard = ({ vm, screenshot }) => {
  const [imageUrl, setImageUrl] = useState(null);
  const [imageError, setImageError] = useState(false);

  useEffect(() => {
    if (screenshot?.image_base64) {
      setImageUrl(`data:image/png;base64,${screenshot.image_base64}`);
      setImageError(false);
    } else {
      setImageUrl(null);
    }
  }, [screenshot]);

  return (
    <div className="card overflow-hidden">
      {/* Card Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <Monitor className="h-5 w-5 text-blue-400" />
          <span className="font-medium text-white">VM #{vm.vm_id}</span>
        </div>
        <span className="badge badge-success">Running</span>
      </div>

      {/* Screenshot */}
      <div className="bg-black rounded-lg overflow-hidden aspect-video flex items-center justify-center">
        {imageUrl && !imageError ? (
          <img
            src={imageUrl}
            alt={`VM ${vm.vm_id} screenshot`}
            className="w-full h-full object-contain"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="text-center text-gray-500">
            <Monitor className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p className="text-sm">
              {imageError ? 'Failed to load screenshot' : 'Waiting for screenshot...'}
            </p>
          </div>
        )}
      </div>

      {/* VM Details */}
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Arch:</span>
          <span className="text-gray-300 ml-2">{vm.arch}</span>
        </div>
        <div>
          <span className="text-gray-500">PID:</span>
          <span className="text-gray-300 ml-2">{vm.pid}</span>
        </div>
        <div>
          <span className="text-gray-500">VNC:</span>
          <span className="text-gray-300 ml-2">{vm.vnc_port || 'N/A'}</span>
        </div>
        <div>
          <span className="text-gray-500">Monitor:</span>
          <span className="text-gray-300 ml-2">{vm.monitor_port || 'N/A'}</span>
        </div>
      </div>
    </div>
  );
};

export default VMViewerPage;
