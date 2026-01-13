import React, { useState, useEffect, useRef } from 'react';
import { vmConfigsAPI, vmRunnerAPI } from '../services/api';

// Icons
const Icons = {
  Play: () => <span className="text-green-400">{'>'}</span>,
  Stop: () => <span className="text-red-400">{'[]'}</span>,
  Refresh: () => <span className="text-blue-400">{'~'}</span>,
  Upload: () => <span className="text-blue-400">{'+'}</span>,
  Folder: () => <span className="text-yellow-400">{'[]'}</span>,
  File: () => <span className="text-gray-400">{'='}</span>,
  Trash: () => <span className="text-red-400">{'x'}</span>,
  Camera: () => <span className="text-purple-400">{'@'}</span>,
  Check: () => <span className="text-green-400">{'OK'}</span>,
  Warning: () => <span className="text-yellow-400">{'!!'}</span>,
  Link: () => <span className="text-blue-400">{'->'}</span>,
  Terminal: () => <span className="text-green-400">{'$_'}</span>,
  Clear: () => <span className="text-gray-400">{'--'}</span>,
  Power: () => <span className="text-red-500">{'O'}</span>,
};

function VMRunnerPage() {
  // State
  const [configs, setConfigs] = useState([]);
  const [runningVMs, setRunningVMs] = useState([]);
  const [selectedConfig, setSelectedConfig] = useState(null);
  const [selectedVM, setSelectedVM] = useState(null);
  const [sharedFiles, setSharedFiles] = useState([]);
  const [currentPath, setCurrentPath] = useState('');
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [message, setMessage] = useState(null);
  const [snapshotName, setSnapshotName] = useState('fuzzing-ready');
  const [targetOs, setTargetOs] = useState('both');

  const fileInputRef = useRef(null);

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  // Load shared files when VM selected
  useEffect(() => {
    if (selectedVM) {
      loadSharedFiles(selectedVM.vm_id, currentPath);
    }
  }, [selectedVM, currentPath]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [configsRes, vmsRes, agentsRes] = await Promise.all([
        vmConfigsAPI.list(),
        vmRunnerAPI.list(),
        vmRunnerAPI.listAgents(),
      ]);
      setConfigs(configsRes.data.data || []);
      setRunningVMs(vmsRes.data.data || []);
      setAgents(agentsRes.data.data || []);

      // Auto-select first running VM
      if (vmsRes.data.data?.length > 0 && !selectedVM) {
        setSelectedVM(vmsRes.data.data[0]);
      }
    } catch (error) {
      console.error('Error loading data:', error);
      showMessage('Error loading data: ' + (error.response?.data?.detail || error.message), 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadSharedFiles = async (vmId, path = '') => {
    try {
      const res = await vmRunnerAPI.listShared(vmId, path);
      setSharedFiles(res.data.data || []);
    } catch (error) {
      console.error('Error loading shared files:', error);
      setSharedFiles([]);
    }
  };

  const showMessage = (text, type = 'info') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  // Start a VM for preparation
  const handleStartVM = async () => {
    if (!selectedConfig) {
      showMessage('Please select a VM configuration', 'error');
      return;
    }

    try {
      const res = await vmRunnerAPI.start({
        config_id: selectedConfig.id,
        copy_agents: true,
        target_os: targetOs,
      });

      showMessage(`VM started! VNC port: ${res.data.data.vnc_port}`, 'success');
      loadData();

      // Select the new VM
      const newVmId = res.data.data.vm_id;
      setTimeout(() => {
        const vm = runningVMs.find(v => v.vm_id === newVmId) || res.data.data;
        setSelectedVM({ ...vm, ...res.data.data });
      }, 500);
    } catch (error) {
      showMessage('Error starting VM: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Stop a VM with confirmation
  const handleStopVM = async (vmId, vmName = 'this VM') => {
    if (!confirm(`Are you sure you want to stop ${vmName}?\n\nThis will terminate the VM process. Any unsaved work will be lost.`)) {
      return;
    }

    try {
      await vmRunnerAPI.stop(vmId);
      showMessage('VM stopped successfully', 'success');
      if (selectedVM?.vm_id === vmId) {
        setSelectedVM(null);
        setSharedFiles([]);
      }
      loadData();
    } catch (error) {
      showMessage('Error stopping VM: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Clear stopped VMs from the list
  const handleClearStoppedVMs = async () => {
    const stoppedVMs = runningVMs.filter(vm => vm.status !== 'running');
    if (stoppedVMs.length === 0) {
      showMessage('No stopped VMs to clear', 'info');
      return;
    }

    if (!confirm(`Clear ${stoppedVMs.length} stopped VM(s) from the list?`)) {
      return;
    }

    try {
      await vmRunnerAPI.clearStopped();
      showMessage(`Cleared ${stoppedVMs.length} stopped VM(s)`, 'success');
      if (selectedVM && stoppedVMs.some(vm => vm.vm_id === selectedVM.vm_id)) {
        setSelectedVM(null);
        setSharedFiles([]);
      }
      loadData();
    } catch (error) {
      showMessage('Error clearing stopped VMs: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Stop all VMs
  const handleStopAllVMs = async () => {
    const runningCount = runningVMs.filter(vm => vm.status === 'running').length;
    if (runningCount === 0) {
      showMessage('No running VMs to stop', 'info');
      return;
    }

    if (!confirm(`Stop ALL ${runningCount} running VM(s)?\n\nThis will terminate all VM processes. Any unsaved work will be lost.`)) {
      return;
    }

    try {
      await vmRunnerAPI.stopAll();
      showMessage(`Stopped ${runningCount} VM(s)`, 'success');
      setSelectedVM(null);
      setSharedFiles([]);
      loadData();
    } catch (error) {
      showMessage('Error stopping VMs: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Create snapshot
  const handleCreateSnapshot = async () => {
    if (!selectedVM) return;
    if (!snapshotName.trim()) {
      showMessage('Please enter a snapshot name', 'error');
      return;
    }

    try {
      const res = await vmRunnerAPI.createSnapshot(selectedVM.vm_id, {
        vm_id: selectedVM.vm_id,
        snapshot_name: snapshotName,
        update_config: true,
      });

      if (res.data.success) {
        showMessage(`Snapshot '${snapshotName}' created successfully!`, 'success');
      } else {
        showMessage(res.data.message || 'Snapshot creation may have failed', 'warning');
      }
    } catch (error) {
      showMessage('Error creating snapshot: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // File upload
  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file || !selectedVM) return;

    setUploading(true);
    setUploadProgress(0);

    try {
      await vmRunnerAPI.uploadFile(selectedVM.vm_id, file, currentPath || 'uploads', (progressEvent) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(progress);
      });

      showMessage(`File '${file.name}' uploaded`, 'success');
      loadSharedFiles(selectedVM.vm_id, currentPath);
    } catch (error) {
      showMessage('Error uploading file: ' + (error.response?.data?.detail || error.message), 'error');
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Delete file
  const handleDeleteFile = async (filepath) => {
    if (!selectedVM || !confirm(`Delete '${filepath}'?`)) return;

    try {
      await vmRunnerAPI.deleteFile(selectedVM.vm_id, filepath);
      showMessage('File deleted', 'success');
      loadSharedFiles(selectedVM.vm_id, currentPath);
    } catch (error) {
      showMessage('Error deleting file: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Navigate to folder
  const handleNavigate = (path) => {
    if (path === '..') {
      const parts = currentPath.split('/').filter(p => p);
      parts.pop();
      setCurrentPath(parts.join('/'));
    } else {
      setCurrentPath(path);
    }
  };

  // Format file size
  const formatSize = (bytes) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-2">VM Runner</h1>
        <p className="text-gray-400">Run VMs, install crash agents, upload files, and create fuzzing-ready snapshots</p>
      </div>

      {/* Message */}
      {message && (
        <div className={`mb-4 p-4 rounded-lg ${
          message.type === 'success' ? 'bg-green-900/50 text-green-300 border border-green-700' :
          message.type === 'error' ? 'bg-red-900/50 text-red-300 border border-red-700' :
          message.type === 'warning' ? 'bg-yellow-900/50 text-yellow-300 border border-yellow-700' :
          'bg-blue-900/50 text-blue-300 border border-blue-700'
        }`}>
          {message.text}
        </div>
      )}

      {/* Upload Progress */}
      {uploading && (
        <div className="mb-4 bg-gray-800 rounded-lg p-4">
          <div className="flex justify-between text-sm text-gray-400 mb-2">
            <span>Uploading...</span>
            <span>{uploadProgress}%</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-2">
            <div
              className="bg-primary-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel - VM Selection & Start */}
        <div className="lg:col-span-1 space-y-4">
          {/* Start New VM */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold text-white mb-4">Start Preparation VM</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-2">Select Configuration</label>
                <select
                  value={selectedConfig?.id || ''}
                  onChange={(e) => {
                    const config = configs.find(c => c.id === e.target.value);
                    setSelectedConfig(config);
                  }}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                >
                  <option value="">Choose a VM config...</option>
                  {configs.map((config) => (
                    <option key={config.id} value={config.id}>
                      {config.name} ({config.arch}, {config.memory})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Target OS</label>
                <select
                  value={targetOs}
                  onChange={(e) => setTargetOs(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                >
                  <option value="both">Both (Windows & Linux agents)</option>
                  <option value="windows">Windows only</option>
                  <option value="linux">Linux only</option>
                </select>
              </div>

              <button
                onClick={handleStartVM}
                disabled={!selectedConfig || loading}
                className="w-full px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center justify-center space-x-2"
              >
                <Icons.Play />
                <span>Start VM</span>
              </button>
            </div>
          </div>

          {/* Running VMs */}
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-white">Running VMs</h2>
              <div className="flex items-center space-x-2">
                <button
                  onClick={loadData}
                  className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                  title="Refresh list"
                >
                  <Icons.Refresh />
                </button>
                {runningVMs.length > 0 && (
                  <>
                    <button
                      onClick={handleClearStoppedVMs}
                      className="p-1.5 text-gray-400 hover:text-yellow-400 hover:bg-gray-700 rounded"
                      title="Clear stopped VMs from list"
                    >
                      <Icons.Clear />
                    </button>
                    <button
                      onClick={handleStopAllVMs}
                      className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded"
                      title="Stop all VMs"
                    >
                      <Icons.Power />
                    </button>
                  </>
                )}
              </div>
            </div>

            {runningVMs.length === 0 ? (
              <p className="text-gray-400 text-sm">No VMs in list</p>
            ) : (
              <div className="space-y-2">
                {runningVMs.map((vm) => (
                  <div
                    key={vm.vm_id}
                    className={`rounded-lg overflow-hidden transition-colors ${
                      selectedVM?.vm_id === vm.vm_id
                        ? 'bg-primary-900/50 border border-primary-600'
                        : 'bg-gray-700'
                    }`}
                  >
                    {/* VM Info - clickable */}
                    <div
                      onClick={() => setSelectedVM(vm)}
                      className="p-3 cursor-pointer hover:bg-gray-600/50"
                    >
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="text-white font-medium text-sm">{vm.config_name}</div>
                          <div className="text-xs text-gray-400">
                            VNC: {vm.vnc_port} | Agent: {vm.agent_port}
                          </div>
                        </div>
                        <div className={`px-2 py-0.5 rounded text-xs font-medium ${
                          vm.status === 'running'
                            ? 'bg-green-900/50 text-green-400 border border-green-700'
                            : 'bg-red-900/50 text-red-400 border border-red-700'
                        }`}>
                          {vm.status}
                        </div>
                      </div>
                    </div>

                    {/* Stop Button - always visible */}
                    {vm.status === 'running' && (
                      <div className="px-3 pb-3">
                        <button
                          onClick={(e) => { e.stopPropagation(); handleStopVM(vm.vm_id, vm.config_name); }}
                          className="w-full px-3 py-2 bg-red-600/20 hover:bg-red-600/40 text-red-400 hover:text-red-300 rounded border border-red-700/50 text-sm font-medium flex items-center justify-center space-x-2 transition-colors"
                        >
                          <Icons.Power />
                          <span>Stop VM</span>
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Action buttons at bottom - always visible */}
            <div className="mt-4 pt-4 border-t border-gray-700 space-y-2">
              <button
                onClick={handleClearStoppedVMs}
                className="w-full px-3 py-2 bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-400 rounded border border-yellow-800/50 text-sm font-medium flex items-center justify-center space-x-2"
              >
                <span className="text-lg">🗑</span>
                <span>Clear Stopped VMs</span>
              </button>
              {runningVMs.some(vm => vm.status === 'running') && (
                <button
                  onClick={handleStopAllVMs}
                  className="w-full px-3 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded border border-red-800/50 text-sm font-medium flex items-center justify-center space-x-2"
                >
                  <span className="text-lg">⏹</span>
                  <span>Stop All VMs</span>
                </button>
              )}
            </div>
          </div>

          {/* Available Agents */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold text-white mb-4">Crash Agents</h2>
            <div className="space-y-2">
              {agents.map((agent, idx) => (
                <div key={idx} className="p-3 bg-gray-700 rounded-lg">
                  <div className="flex items-center space-x-2">
                    {agent.exists ? <Icons.Check /> : <Icons.Warning />}
                    <span className="text-white text-sm">{agent.name}</span>
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {agent.platform === 'windows' ? 'Windows' : 'Linux'} |{' '}
                    {agent.exists ? (agent.size ? formatSize(agent.size) : 'Source') : 'Not found'}
                  </div>
                  {agent.note && (
                    <div className="text-xs text-gray-500 mt-1">{agent.note}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Panel - VM Details & Files */}
        <div className="lg:col-span-2 space-y-4">
          {selectedVM ? (
            <>
              {/* VM Details */}
              <div className="bg-gray-800 rounded-lg p-4">
                <h2 className="text-lg font-semibold text-white mb-4">VM: {selectedVM.config_name}</h2>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div className="bg-gray-700 p-3 rounded-lg">
                    <div className="text-xs text-gray-400">VNC Port</div>
                    <div className="text-white font-mono">{selectedVM.vnc_port}</div>
                  </div>
                  <div className="bg-gray-700 p-3 rounded-lg">
                    <div className="text-xs text-gray-400">Agent Port</div>
                    <div className="text-white font-mono">{selectedVM.agent_port}</div>
                  </div>
                  <div className="bg-gray-700 p-3 rounded-lg">
                    <div className="text-xs text-gray-400">Memory</div>
                    <div className="text-white">{selectedVM.memory}</div>
                  </div>
                  <div className="bg-gray-700 p-3 rounded-lg">
                    <div className="text-xs text-gray-400">Status</div>
                    <div className={selectedVM.status === 'running' ? 'text-green-400' : 'text-red-400'}>
                      {selectedVM.status}
                    </div>
                  </div>
                </div>

                {/* Connection Instructions */}
                <div className="bg-gray-700 p-4 rounded-lg mb-4">
                  <h3 className="text-sm font-medium text-gray-200 mb-2">Connection Instructions</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-start space-x-2">
                      <Icons.Terminal />
                      <div>
                        <span className="text-gray-400">VNC:</span>{' '}
                        <code className="text-green-400">vncviewer localhost:{selectedVM.vnc_port}</code>
                      </div>
                    </div>
                    <div className="flex items-start space-x-2">
                      <Icons.Folder />
                      <div>
                        <span className="text-gray-400">Windows Share:</span>{' '}
                        <code className="text-green-400">\\10.0.2.4\qemu</code>
                      </div>
                    </div>
                    <div className="flex items-start space-x-2">
                      <Icons.Folder />
                      <div>
                        <span className="text-gray-400">Linux Mount:</span>{' '}
                        <code className="text-green-400">mount -t 9p -o trans=virtio hostshare /mnt/virtfs</code>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Create Snapshot */}
                <div className="bg-gray-700 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-200 mb-3">Create Fuzzing Snapshot</h3>
                  <div className="flex space-x-2">
                    <input
                      type="text"
                      value={snapshotName}
                      onChange={(e) => setSnapshotName(e.target.value)}
                      placeholder="Snapshot name"
                      className="flex-1 px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
                    />
                    <button
                      onClick={handleCreateSnapshot}
                      className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center space-x-2"
                    >
                      <Icons.Camera />
                      <span>Create Snapshot</span>
                    </button>
                  </div>
                  <p className="text-xs text-gray-400 mt-2">
                    Make sure the crash agent is running and the system is configured before creating the snapshot.
                  </p>
                </div>
              </div>

              {/* Shared Folder */}
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-semibold text-white">Shared Folder</h2>
                  <div className="flex space-x-2">
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center space-x-1"
                    >
                      <Icons.Upload />
                      <span>Upload File</span>
                    </button>
                    <button
                      onClick={() => loadSharedFiles(selectedVM.vm_id, currentPath)}
                      className="px-3 py-1.5 bg-gray-700 text-gray-300 text-sm rounded-lg hover:bg-gray-600"
                    >
                      <Icons.Refresh />
                    </button>
                  </div>
                </div>

                {/* Breadcrumb */}
                <div className="flex items-center space-x-2 mb-3 text-sm">
                  <button
                    onClick={() => setCurrentPath('')}
                    className="text-blue-400 hover:text-blue-300"
                  >
                    root
                  </button>
                  {currentPath.split('/').filter(p => p).map((part, idx, arr) => (
                    <React.Fragment key={idx}>
                      <span className="text-gray-500">/</span>
                      <button
                        onClick={() => setCurrentPath(arr.slice(0, idx + 1).join('/'))}
                        className="text-blue-400 hover:text-blue-300"
                      >
                        {part}
                      </button>
                    </React.Fragment>
                  ))}
                </div>

                {/* File List */}
                <div className="bg-gray-700 rounded-lg overflow-hidden">
                  {currentPath && (
                    <div
                      onClick={() => handleNavigate('..')}
                      className="flex items-center space-x-3 p-3 hover:bg-gray-600 cursor-pointer border-b border-gray-600"
                    >
                      <Icons.Folder />
                      <span className="text-gray-300">..</span>
                    </div>
                  )}

                  {sharedFiles.length === 0 && !currentPath ? (
                    <div className="p-4 text-center text-gray-400">
                      Shared folder is empty. Upload files or check agent installation.
                    </div>
                  ) : (
                    sharedFiles.map((file) => (
                      <div
                        key={file.path}
                        className="flex items-center justify-between p-3 hover:bg-gray-600 border-b border-gray-600 last:border-0"
                      >
                        <div
                          className="flex items-center space-x-3 flex-1 cursor-pointer"
                          onClick={() => file.is_dir && handleNavigate(file.path)}
                        >
                          {file.is_dir ? <Icons.Folder /> : <Icons.File />}
                          <span className={file.is_dir ? 'text-blue-400' : 'text-gray-300'}>
                            {file.name}
                          </span>
                          {!file.is_dir && (
                            <span className="text-xs text-gray-500">{formatSize(file.size)}</span>
                          )}
                        </div>
                        {!file.is_dir && file.name !== 'README.md' && (
                          <button
                            onClick={() => handleDeleteFile(file.path)}
                            className="p-1 text-red-400 hover:text-red-300"
                          >
                            <Icons.Trash />
                          </button>
                        )}
                      </div>
                    ))
                  )}
                </div>

                <div className="mt-3 text-xs text-gray-500">
                  Path on host: {selectedVM.shared_folder}
                </div>
              </div>

              {/* Installation Instructions */}
              <div className="bg-gray-800 rounded-lg p-4">
                <h2 className="text-lg font-semibold text-white mb-4">Setup Checklist</h2>
                <div className="space-y-3">
                  <div className="flex items-start space-x-3">
                    <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center text-sm text-white">1</div>
                    <div>
                      <div className="text-white">Connect to VM via VNC</div>
                      <div className="text-sm text-gray-400">Use a VNC client to connect to port {selectedVM.vnc_port}</div>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3">
                    <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center text-sm text-white">2</div>
                    <div>
                      <div className="text-white">Access the shared folder</div>
                      <div className="text-sm text-gray-400">
                        Windows: <code className="bg-gray-700 px-1 rounded">\\10.0.2.4\qemu</code> |
                        Linux: <code className="bg-gray-700 px-1 rounded">mount -t 9p hostshare /mnt</code>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3">
                    <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center text-sm text-white">3</div>
                    <div>
                      <div className="text-white">Install the crash agent</div>
                      <div className="text-sm text-gray-400">
                        Copy and run the agent from the 'agents' folder in the shared directory
                      </div>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3">
                    <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center text-sm text-white">4</div>
                    <div>
                      <div className="text-white">Install target software</div>
                      <div className="text-sm text-gray-400">Upload and install any software you want to fuzz</div>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3">
                    <div className="w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center text-sm text-white">5</div>
                    <div>
                      <div className="text-white">Disable interruptions</div>
                      <div className="text-sm text-gray-400">Turn off screensaver, sleep mode, auto-updates, etc.</div>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3">
                    <div className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center text-sm text-white">6</div>
                    <div>
                      <div className="text-white">Create the snapshot</div>
                      <div className="text-sm text-gray-400">Click "Create Snapshot" above to save the VM state for fuzzing</div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <div className="text-4xl mb-4">{'>'}</div>
              <h2 className="text-xl font-semibold text-white mb-2">No VM Selected</h2>
              <p className="text-gray-400 mb-4">
                Select a running VM from the list or start a new one to begin setup.
              </p>
              {configs.length === 0 && (
                <p className="text-sm text-yellow-400">
                  No VM configurations found. Create one in VM Setup first.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default VMRunnerPage;
