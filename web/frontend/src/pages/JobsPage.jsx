import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, Square, Trash2, Plus, X, ChevronDown, ChevronUp, Settings, HardDrive, Cpu, Network, Zap, Upload, File, FolderOpen } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { jobsAPI, vmConfigsAPI, imagesAPI, jobInputsAPI } from '../services/api';

const JobsPage = () => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [actionInProgress, setActionInProgress] = useState(null); // Track which job action is in progress
  const [actionError, setActionError] = useState(null); // Show action errors to user

  // VM Config selection state
  const [vmConfigs, setVmConfigs] = useState([]);
  const [vmConfigsLoading, setVmConfigsLoading] = useState(false);
  const [selectedVmConfig, setSelectedVmConfig] = useState('');

  // Disk images state
  const [diskImages, setDiskImages] = useState([]);
  const [diskImagesLoading, setDiskImagesLoading] = useState(false);

  // Input files (seed corpus) state
  const [inputFiles, setInputFiles] = useState([]);
  const [inputFilesLoading, setInputFilesLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const fileInputRef = useRef(null);

  // Expanded sections in modal
  const [expandedSections, setExpandedSections] = useState({
    basic: true,
    vm: true,
    fuzzer: true,
    advanced: false,
    network: false,
  });

  // Full job configuration
  const [newJob, setNewJob] = useState({
    // Basic settings
    name: '',

    // VM settings
    disk_image: '',
    snapshot_name: 'clean',
    arch: 'x86_64',
    max_parallel_vms: 4,
    no_headless: false,
    vm_params: '',

    // Directory settings
    input_dir: '~/fuzz_inputs',
    share_dir: '~/fawkes_shared',
    crash_dir: './fawkes/crashes',

    // Fuzzer settings
    fuzzer_type: 'intelligent',
    timeout: 60,
    loop: true,

    // Intelligent fuzzer specific
    mutations_per_seed: 1000,
    auto_extract_tokens: true,
    dictionary: '',

    // Network fuzzing
    network_mode: false,
    packets_per_conversation: 1,

    // Advanced settings
    poll_interval: 60,
    max_retries: 3,
    cleanup_stopped_vms: false,
    vfs: false,
    smb: true,
  });

  useEffect(() => {
    fetchJobs();
  }, []);

  const fetchJobs = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await jobsAPI.list();
      setJobs(response.data.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch jobs');
    } finally {
      setLoading(false);
    }
  };

  const fetchVmConfigs = async () => {
    try {
      setVmConfigsLoading(true);
      const response = await vmConfigsAPI.list();
      setVmConfigs(response.data.data || []);
    } catch (err) {
      console.error('Failed to load VM configs:', err);
      setVmConfigs([]);
    } finally {
      setVmConfigsLoading(false);
    }
  };

  const fetchDiskImages = async () => {
    try {
      setDiskImagesLoading(true);
      const response = await imagesAPI.list();
      setDiskImages(response.data.data || []);
    } catch (err) {
      console.error('Failed to load disk images:', err);
      setDiskImages([]);
    } finally {
      setDiskImagesLoading(false);
    }
  };

  const fetchInputFiles = async (sid = null) => {
    try {
      setInputFilesLoading(true);
      const response = await jobInputsAPI.list(sid || sessionId);
      setInputFiles(response.data.data || []);
    } catch (err) {
      console.error('Failed to load input files:', err);
      setInputFiles([]);
    } finally {
      setInputFilesLoading(false);
    }
  };

  const handleFileUpload = async (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setUploadProgress(0);

    try {
      if (files.length === 1) {
        await jobInputsAPI.upload(files[0], (progressEvent) => {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(percent);
        }, sessionId);
      } else {
        await jobInputsAPI.uploadMultiple(Array.from(files), (progressEvent) => {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(percent);
        }, sessionId);
      }
      // Refresh the file list
      await fetchInputFiles();
    } catch (err) {
      console.error('Failed to upload files:', err);
      setCreateError(err.response?.data?.detail || 'Failed to upload files');
    } finally {
      setUploading(false);
      setUploadProgress(0);
      // Clear the file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDeleteInputFile = async (filename) => {
    try {
      await jobInputsAPI.delete(filename, sessionId);
      await fetchInputFiles();
    } catch (err) {
      console.error('Failed to delete file:', err);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleVmConfigSelect = (configId) => {
    setSelectedVmConfig(configId);

    if (!configId) {
      // Reset to defaults if "Manual Configuration" is selected
      return;
    }

    const config = vmConfigs.find(c => c.id === configId);
    if (config) {
      // Auto-populate form fields from VM config
      setNewJob(prev => ({
        ...prev,
        name: prev.name || config.name, // Only set name if empty
        disk_image: config.disk_image || '',
        snapshot_name: config.snapshot_name || 'clean',
        arch: config.arch || 'x86_64',
        timeout: config.timeout || 60,
        fuzzer_type: config.fuzzer_type || 'intelligent',
        // Optional fields from config
        ...(config.memory && { vm_params: `-m ${config.memory}${config.cpu_cores ? ` -smp ${config.cpu_cores}` : ''}` }),
      }));
    }
  };

  const handleDiskImageSelect = (diskImagePath) => {
    setNewJob(prev => ({ ...prev, disk_image: diskImagePath }));

    // Check if there's a VM config that uses this disk image
    if (diskImagePath && vmConfigs.length > 0) {
      const matchingConfig = vmConfigs.find(c => c.disk_image === diskImagePath);
      if (matchingConfig && !selectedVmConfig) {
        // Auto-select the matching VM config if one exists and none is currently selected
        setSelectedVmConfig(matchingConfig.id);
        // Auto-populate the rest of the fields from the config
        setNewJob(prev => ({
          ...prev,
          disk_image: diskImagePath, // Keep the selected disk image
          name: prev.name || matchingConfig.name,
          snapshot_name: matchingConfig.snapshot_name || 'clean',
          arch: matchingConfig.arch || 'x86_64',
          timeout: matchingConfig.timeout || 60,
          fuzzer_type: matchingConfig.fuzzer_type || 'intelligent',
          ...(matchingConfig.memory && { vm_params: `-m ${matchingConfig.memory}${matchingConfig.cpu_cores ? ` -smp ${matchingConfig.cpu_cores}` : ''}` }),
        }));
      }
    }
  };

  const handleStart = async (jobId) => {
    setActionInProgress(`start-${jobId}`);
    setActionError(null);
    try {
      await jobsAPI.start(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Failed to start job:', err);
      setActionError(`Failed to start job ${jobId}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handlePause = async (jobId) => {
    setActionInProgress(`pause-${jobId}`);
    setActionError(null);
    try {
      await jobsAPI.pause(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Failed to pause job:', err);
      setActionError(`Failed to pause job ${jobId}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleStop = async (jobId) => {
    setActionInProgress(`stop-${jobId}`);
    setActionError(null);
    try {
      await jobsAPI.stop(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Failed to stop job:', err);
      setActionError(`Failed to stop job ${jobId}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDelete = async (jobId) => {
    if (!confirm('Are you sure you want to delete this job?')) return;

    setActionInProgress(`delete-${jobId}`);
    setActionError(null);
    try {
      await jobsAPI.delete(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Failed to delete job:', err);
      setActionError(`Failed to delete job ${jobId}: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleCreateJob = async (e) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);

    try {
      // Build the job config object
      const jobConfig = {
        name: newJob.name,
        disk: newJob.disk_image,
        snapshot: newJob.snapshot_name,
        fuzzer_type: newJob.fuzzer_type,
        fuzzer_config: {
          // Directory settings
          input_dir: newJob.input_dir,
          share_dir: newJob.share_dir,
          crash_dir: newJob.crash_dir,

          // VM settings
          arch: newJob.arch,
          max_parallel_vms: newJob.max_parallel_vms,
          no_headless: newJob.no_headless,
          vm_params: newJob.vm_params || null,

          // Fuzzer settings
          timeout: newJob.timeout,
          loop: newJob.loop,
          mutations_per_seed: newJob.mutations_per_seed,
          auto_extract_tokens: newJob.auto_extract_tokens,
          dictionary: newJob.dictionary || null,

          // Network settings
          network_mode: newJob.network_mode,
          packets_per_conversation: newJob.packets_per_conversation,

          // Advanced settings
          poll_interval: newJob.poll_interval,
          max_retries: newJob.max_retries,
          cleanup_stopped_vms: newJob.cleanup_stopped_vms,
          vfs: newJob.vfs,
          smb: newJob.smb,
        }
      };

      // Pass session_id so backend moves files to job directory
      await jobsAPI.create(jobConfig, sessionId);
      setSessionId(null);  // Clear session ID after successful creation
      setShowCreateModal(false);
      resetForm();
      fetchJobs();
    } catch (err) {
      setCreateError(err.response?.data?.detail || 'Failed to create job');
    } finally {
      setCreating(false);
    }
  };

  const resetForm = () => {
    setNewJob({
      name: '',
      disk_image: '',
      snapshot_name: 'clean',
      arch: 'x86_64',
      max_parallel_vms: 4,
      no_headless: false,
      vm_params: '',
      input_dir: '~/fuzz_inputs',
      share_dir: '~/fawkes_shared',
      crash_dir: './fawkes/crashes',
      fuzzer_type: 'intelligent',
      timeout: 60,
      loop: true,
      mutations_per_seed: 1000,
      auto_extract_tokens: true,
      dictionary: '',
      network_mode: false,
      packets_per_conversation: 1,
      poll_interval: 60,
      max_retries: 3,
      cleanup_stopped_vms: false,
      vfs: false,
      smb: true,
    });
  };

  const openCreateModal = async () => {
    setCreateError(null);
    setSelectedVmConfig('');
    setInputFiles([]);

    // Create a new session for file uploads
    try {
      const response = await jobInputsAPI.createSession();
      const newSessionId = response.data.session_id;
      setSessionId(newSessionId);
      // Update input_dir to point to the session directory
      setNewJob(prev => ({
        ...prev,
        input_dir: `~/.fawkes/job_inputs/session_${newSessionId}`
      }));
    } catch (err) {
      console.error('Failed to create session:', err);
    }

    fetchVmConfigs();
    fetchDiskImages();
    setShowCreateModal(true);
  };

  const closeCreateModal = async () => {
    // Clean up session if user cancels
    if (sessionId) {
      try {
        await jobInputsAPI.deleteSession(sessionId);
      } catch (err) {
        console.error('Failed to delete session:', err);
      }
      setSessionId(null);
    }
    setShowCreateModal(false);
    resetForm();
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const SectionHeader = ({ title, section, icon: Icon }) => (
    <button
      type="button"
      onClick={() => toggleSection(section)}
      className="w-full flex items-center justify-between py-3 px-4 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors"
    >
      <div className="flex items-center space-x-2">
        <Icon className="h-4 w-4 text-blue-400" />
        <span className="font-medium text-white">{title}</span>
      </div>
      {expandedSections[section] ? (
        <ChevronUp className="h-4 w-4 text-gray-400" />
      ) : (
        <ChevronDown className="h-4 w-4 text-gray-400" />
      )}
    </button>
  );

  if (loading) return <LoadingSpinner size="lg" message="Loading jobs..." />;
  if (error) return <ErrorMessage message={error} onRetry={fetchJobs} />;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Jobs</h1>
          <p className="text-gray-400 mt-1">Manage and monitor fuzzing jobs</p>
        </div>
        <button onClick={openCreateModal} className="btn btn-primary flex items-center space-x-2">
          <Plus className="h-4 w-4" />
          <span>Create Job</span>
        </button>
      </div>

      {/* Action Error Alert */}
      {actionError && (
        <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-3 rounded-lg flex items-center justify-between">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="text-red-400 hover:text-red-300"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Create Job Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden border border-gray-700 flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-700">
              <h2 className="text-xl font-bold text-white">Create New Fuzzing Job</h2>
              <button
                onClick={closeCreateModal}
                className="text-gray-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body - Scrollable */}
            <div className="flex-1 overflow-y-auto p-6">
              {createError && (
                <div className="bg-red-900/20 border border-red-500 text-red-400 px-4 py-2 rounded mb-4">
                  {createError}
                </div>
              )}

              <form id="createJobForm" onSubmit={handleCreateJob} className="space-y-4">
                {/* VM Config Selection */}
                <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4 mb-2">
                  <label className="block text-sm font-medium text-blue-300 mb-2">
                    Load from VM Configuration
                  </label>
                  <select
                    value={selectedVmConfig}
                    onChange={(e) => handleVmConfigSelect(e.target.value)}
                    className="w-full bg-gray-700 border border-blue-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                    disabled={vmConfigsLoading}
                  >
                    <option value="">-- Manual Configuration --</option>
                    {vmConfigs.map((config) => (
                      <option key={config.id} value={config.id}>
                        {config.name} ({config.arch}) {config.tags?.length > 0 && `[${config.tags.join(', ')}]`}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-blue-400 mt-2">
                    {vmConfigsLoading ? 'Loading VM configs...' :
                      selectedVmConfig ? 'VM settings auto-populated. You can still modify them below.' :
                      'Select a saved VM configuration to auto-fill settings, or configure manually.'}
                  </p>
                </div>

                {/* Basic Settings */}
                <div className="space-y-3">
                  <SectionHeader title="Basic Settings" section="basic" icon={Settings} />
                  {expandedSections.basic && (
                    <div className="pl-4 space-y-4 pt-2">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">
                          Job Name *
                        </label>
                        <input
                          type="text"
                          value={newJob.name}
                          onChange={(e) => setNewJob({ ...newJob, name: e.target.value })}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          placeholder="My Fuzzing Campaign"
                          required
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Input Directory *
                          </label>
                          <div className="flex items-center space-x-2 mb-2">
                            <input
                              type="checkbox"
                              id="useUploadedSeeds"
                              checked={newJob.input_dir.includes('session_') || newJob.input_dir.includes('job_')}
                              onChange={(e) => setNewJob({
                                ...newJob,
                                input_dir: e.target.checked && sessionId
                                  ? `~/.fawkes/job_inputs/session_${sessionId}`
                                  : '~/fuzz_inputs'
                              })}
                              className="form-checkbox h-4 w-4 text-green-500 bg-gray-700 border-gray-600 rounded focus:ring-green-500"
                            />
                            <label htmlFor="useUploadedSeeds" className="text-sm text-green-400 cursor-pointer">
                              Use uploaded seed files ({inputFiles.length} files)
                            </label>
                          </div>
                          <input
                            type="text"
                            value={newJob.input_dir}
                            onChange={(e) => setNewJob({ ...newJob, input_dir: e.target.value })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            placeholder="~/fuzz_inputs"
                            required
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            {newJob.input_dir.includes('session_') || newJob.input_dir.includes('job_')
                              ? 'Using uploaded seed files (will be moved to job directory)'
                              : 'Custom seed corpus directory'}
                          </p>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Crash Directory
                          </label>
                          <input
                            type="text"
                            value={newJob.crash_dir}
                            onChange={(e) => setNewJob({ ...newJob, crash_dir: e.target.value })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            placeholder="./fawkes/crashes"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">
                          Share Directory
                        </label>
                        <input
                          type="text"
                          value={newJob.share_dir}
                          onChange={(e) => setNewJob({ ...newJob, share_dir: e.target.value })}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          placeholder="~/fawkes_shared"
                        />
                        <p className="text-xs text-gray-500 mt-1">Shared directory between host and guest VM</p>
                      </div>

                      {/* Seed Files Upload Section */}
                      <div className="bg-green-900/20 border border-green-700 rounded-lg p-4">
                        <label className="block text-sm font-medium text-green-300 mb-2">
                          <div className="flex items-center space-x-2">
                            <FolderOpen className="h-4 w-4" />
                            <span>Seed Files (Corpus)</span>
                            {sessionId && (
                              <span className="text-xs bg-green-800 text-green-200 px-2 py-0.5 rounded">
                                Session: {sessionId}
                              </span>
                            )}
                          </div>
                        </label>
                        <p className="text-xs text-green-400 mb-3">
                          Upload initial test case files to use as fuzzer seeds. Files are stored in a job-specific directory.
                        </p>

                        {/* Upload Area */}
                        <div className="mb-3">
                          <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            onChange={handleFileUpload}
                            className="hidden"
                            id="seedFileUpload"
                            disabled={uploading}
                          />
                          <label
                            htmlFor="seedFileUpload"
                            className={`flex items-center justify-center w-full px-4 py-3 border-2 border-dashed rounded-lg cursor-pointer transition-colors ${
                              uploading
                                ? 'border-gray-600 bg-gray-700/50 cursor-not-allowed'
                                : 'border-green-600 hover:border-green-500 hover:bg-green-900/30'
                            }`}
                          >
                            {uploading ? (
                              <div className="flex items-center space-x-2 text-gray-400">
                                <LoadingSpinner size="sm" />
                                <span>Uploading... {uploadProgress}%</span>
                              </div>
                            ) : (
                              <div className="flex items-center space-x-2 text-green-400">
                                <Upload className="h-5 w-5" />
                                <span>Click to upload seed files (or drag & drop)</span>
                              </div>
                            )}
                          </label>
                        </div>

                        {/* Progress Bar */}
                        {uploading && (
                          <div className="mb-3">
                            <div className="w-full bg-gray-700 rounded-full h-2">
                              <div
                                className="bg-green-500 h-2 rounded-full transition-all duration-300"
                                style={{ width: `${uploadProgress}%` }}
                              />
                            </div>
                          </div>
                        )}

                        {/* Uploaded Files List */}
                        {inputFilesLoading ? (
                          <div className="text-center py-2">
                            <LoadingSpinner size="sm" />
                          </div>
                        ) : inputFiles.length > 0 ? (
                          <div className="space-y-2 max-h-40 overflow-y-auto">
                            <p className="text-xs text-gray-400 mb-1">Uploaded files ({inputFiles.length}):</p>
                            {inputFiles.map((file) => (
                              <div
                                key={file.filename}
                                className="flex items-center justify-between bg-gray-700/50 rounded px-3 py-2"
                              >
                                <div className="flex items-center space-x-2 min-w-0">
                                  <File className="h-4 w-4 text-green-400 flex-shrink-0" />
                                  <span className="text-sm text-gray-300 truncate">{file.filename}</span>
                                  <span className="text-xs text-gray-500 flex-shrink-0">
                                    ({formatFileSize(file.size)})
                                  </span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => handleDeleteInputFile(file.filename)}
                                  className="text-red-400 hover:text-red-300 p-1 flex-shrink-0"
                                  title="Delete file"
                                >
                                  <X className="h-4 w-4" />
                                </button>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-gray-500 text-center py-2">
                            No seed files uploaded yet. Upload files to start fuzzing.
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* VM Settings */}
                <div className="space-y-3">
                  <SectionHeader title="Virtual Machine" section="vm" icon={HardDrive} />
                  {expandedSections.vm && (
                    <div className="pl-4 space-y-4 pt-2">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">
                          Disk Image *
                        </label>
                        <select
                          value={newJob.disk_image}
                          onChange={(e) => handleDiskImageSelect(e.target.value)}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          disabled={diskImagesLoading}
                          required
                        >
                          <option value="">{diskImagesLoading ? 'Loading disk images...' : '-- Select a Disk Image --'}</option>
                          {diskImages.map((image) => {
                            const hasConfig = vmConfigs.some(c => c.disk_image === image.path);
                            return (
                              <option key={image.path} value={image.path}>
                                {image.filename} ({image.format || 'qcow2'}, {image.virtual_size_human || 'N/A'}){hasConfig ? ' [has config]' : ''}
                              </option>
                            );
                          })}
                        </select>
                        <p className="text-xs text-gray-500 mt-1">
                          {diskImages.length === 0 && !diskImagesLoading
                            ? 'No disk images found. Create one in VM Setup first.'
                            : vmConfigs.some(c => c.disk_image === newJob.disk_image)
                              ? 'VM config found and auto-loaded for this disk image'
                              : 'Select a QEMU disk image (.qcow2)'}
                        </p>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Snapshot Name *
                          </label>
                          <input
                            type="text"
                            value={newJob.snapshot_name}
                            onChange={(e) => setNewJob({ ...newJob, snapshot_name: e.target.value })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            placeholder="clean"
                            required
                          />
                          <p className="text-xs text-gray-500 mt-1">VM snapshot to restore</p>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Architecture
                          </label>
                          <select
                            value={newJob.arch}
                            onChange={(e) => setNewJob({ ...newJob, arch: e.target.value })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          >
                            <option value="x86_64">x86_64 (64-bit)</option>
                            <option value="i386">i386 (32-bit)</option>
                            <option value="arm">ARM</option>
                            <option value="aarch64">AArch64 (ARM64)</option>
                            <option value="mips">MIPS</option>
                            <option value="ppc">PowerPC</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Parallel VMs
                          </label>
                          <input
                            type="number"
                            min="1"
                            max="32"
                            value={newJob.max_parallel_vms}
                            onChange={(e) => setNewJob({ ...newJob, max_parallel_vms: parseInt(e.target.value) || 1 })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          />
                          <p className="text-xs text-gray-500 mt-1">Max concurrent VMs</p>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Execution Timeout
                          </label>
                          <div className="flex items-center space-x-2">
                            <input
                              type="number"
                              min="1"
                              max="3600"
                              value={newJob.timeout}
                              onChange={(e) => setNewJob({ ...newJob, timeout: parseInt(e.target.value) || 60 })}
                              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            />
                            <span className="text-gray-400 text-sm">sec</span>
                          </div>
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">
                          Custom VM Parameters
                        </label>
                        <input
                          type="text"
                          value={newJob.vm_params}
                          onChange={(e) => setNewJob({ ...newJob, vm_params: e.target.value })}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          placeholder="-m 2048 -smp 2"
                        />
                        <p className="text-xs text-gray-500 mt-1">Additional QEMU parameters</p>
                      </div>

                      <div className="flex items-center space-x-4">
                        <label className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={!newJob.no_headless}
                            onChange={(e) => setNewJob({ ...newJob, no_headless: !e.target.checked })}
                            className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-300">Headless Mode</span>
                        </label>
                      </div>
                    </div>
                  )}
                </div>

                {/* Fuzzer Settings */}
                <div className="space-y-3">
                  <SectionHeader title="Fuzzer Configuration" section="fuzzer" icon={Zap} />
                  {expandedSections.fuzzer && (
                    <div className="pl-4 space-y-4 pt-2">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">
                          Fuzzer Type
                        </label>
                        <select
                          value={newJob.fuzzer_type}
                          onChange={(e) => setNewJob({ ...newJob, fuzzer_type: e.target.value })}
                          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                        >
                          <option value="intelligent">Intelligent Fuzzer (Crash-Guided)</option>
                          <option value="file">File Fuzzer (Basic Mutation)</option>
                        </select>
                        <p className="text-xs text-gray-500 mt-1">
                          {newJob.fuzzer_type === 'intelligent'
                            ? 'Adaptive fuzzer with crash feedback and dictionary support'
                            : 'Simple mutation-based file fuzzer'}
                        </p>
                      </div>

                      {newJob.fuzzer_type === 'intelligent' && (
                        <>
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="block text-sm font-medium text-gray-300 mb-1">
                                Mutations per Seed
                              </label>
                              <input
                                type="number"
                                min="1"
                                max="100000"
                                value={newJob.mutations_per_seed}
                                onChange={(e) => setNewJob({ ...newJob, mutations_per_seed: parseInt(e.target.value) || 1000 })}
                                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                              />
                            </div>
                            <div>
                              <label className="block text-sm font-medium text-gray-300 mb-1">
                                Dictionary File
                              </label>
                              {inputFiles.filter(f => f.filename.endsWith('.dict') || f.filename.endsWith('.txt')).length > 0 ? (
                                <select
                                  value={newJob.dictionary}
                                  onChange={(e) => setNewJob({ ...newJob, dictionary: e.target.value })}
                                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                                >
                                  <option value="">-- No dictionary --</option>
                                  <option value="__custom__">Custom path...</option>
                                  {inputFiles
                                    .filter(f => f.filename.endsWith('.dict') || f.filename.endsWith('.txt'))
                                    .map(f => (
                                      <option key={f.path} value={f.path}>
                                        {f.filename} ({formatFileSize(f.size)})
                                      </option>
                                    ))
                                  }
                                </select>
                              ) : (
                                <input
                                  type="text"
                                  value={newJob.dictionary}
                                  onChange={(e) => setNewJob({ ...newJob, dictionary: e.target.value })}
                                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                                  placeholder="~/dictionaries/http.dict"
                                />
                              )}
                              <p className="text-xs text-gray-500 mt-1">
                                Upload .dict or .txt files above to select here
                              </p>
                            </div>
                          </div>
                          {newJob.dictionary === '__custom__' && (
                            <div>
                              <label className="block text-sm font-medium text-gray-300 mb-1">
                                Custom Dictionary Path
                              </label>
                              <input
                                type="text"
                                value={newJob.customDictionary || ''}
                                onChange={(e) => setNewJob({ ...newJob, customDictionary: e.target.value })}
                                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                                placeholder="~/dictionaries/http.dict"
                              />
                            </div>
                          )}

                          <div className="flex items-center space-x-4">
                            <label className="flex items-center space-x-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={newJob.auto_extract_tokens}
                                onChange={(e) => setNewJob({ ...newJob, auto_extract_tokens: e.target.checked })}
                                className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                              />
                              <span className="text-sm text-gray-300">Auto-extract dictionary tokens from corpus</span>
                            </label>
                          </div>
                        </>
                      )}

                      <div className="flex items-center space-x-4">
                        <label className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newJob.loop}
                            onChange={(e) => setNewJob({ ...newJob, loop: e.target.checked })}
                            className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-300">Continuous Loop Mode</span>
                        </label>
                      </div>
                    </div>
                  )}
                </div>

                {/* Network Fuzzing */}
                <div className="space-y-3">
                  <SectionHeader title="Network Fuzzing" section="network" icon={Network} />
                  {expandedSections.network && (
                    <div className="pl-4 space-y-4 pt-2">
                      <div className="flex items-center space-x-4">
                        <label className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newJob.network_mode}
                            onChange={(e) => setNewJob({ ...newJob, network_mode: e.target.checked })}
                            className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-300">Enable Network Fuzzing Mode</span>
                        </label>
                      </div>

                      {newJob.network_mode && (
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Packets per Conversation
                          </label>
                          <input
                            type="number"
                            min="1"
                            max="100"
                            value={newJob.packets_per_conversation}
                            onChange={(e) => setNewJob({ ...newJob, packets_per_conversation: parseInt(e.target.value) || 1 })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          />
                          <p className="text-xs text-gray-500 mt-1">Number of packets to fuzz per conversation</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Advanced Settings */}
                <div className="space-y-3">
                  <SectionHeader title="Advanced Settings" section="advanced" icon={Cpu} />
                  {expandedSections.advanced && (
                    <div className="pl-4 space-y-4 pt-2">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Poll Interval
                          </label>
                          <div className="flex items-center space-x-2">
                            <input
                              type="number"
                              min="1"
                              max="3600"
                              value={newJob.poll_interval}
                              onChange={(e) => setNewJob({ ...newJob, poll_interval: parseInt(e.target.value) || 60 })}
                              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                            />
                            <span className="text-gray-400 text-sm">sec</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-300 mb-1">
                            Max Retries
                          </label>
                          <input
                            type="number"
                            min="0"
                            max="10"
                            value={newJob.max_retries}
                            onChange={(e) => setNewJob({ ...newJob, max_retries: parseInt(e.target.value) || 3 })}
                            className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                          />
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newJob.smb}
                            onChange={(e) => setNewJob({ ...newJob, smb: e.target.checked })}
                            className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-300">Enable SMB sharing</span>
                        </label>

                        <label className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newJob.vfs}
                            onChange={(e) => setNewJob({ ...newJob, vfs: e.target.checked })}
                            className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-300">Use VirtFS (9P) instead of SMB</span>
                        </label>

                        <label className="flex items-center space-x-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={newJob.cleanup_stopped_vms}
                            onChange={(e) => setNewJob({ ...newJob, cleanup_stopped_vms: e.target.checked })}
                            className="form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-300">Auto-cleanup stopped VMs</span>
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              </form>
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end space-x-3 p-6 border-t border-gray-700 bg-gray-800">
              <button
                type="button"
                onClick={closeCreateModal}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="createJobForm"
                disabled={creating}
                className="btn btn-primary disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create Job'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Jobs Table */}
      <div className="card">
        {jobs.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-gray-500 mb-4">
              <Zap className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p className="text-gray-400">No fuzzing jobs yet</p>
            </div>
            <button onClick={openCreateModal} className="btn btn-primary">
              Create your first job
            </button>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Fuzzer</th>
                <th>Testcases</th>
                <th>Crashes</th>
                <th>VMs</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id}>
                  <td>#{job.job_id}</td>
                  <td className="font-medium">{job.name || 'Unnamed Job'}</td>
                  <td>
                    <span
                      className={`badge ${
                        job.status === 'running'
                          ? 'badge-success'
                          : job.status === 'paused'
                          ? 'badge-warning'
                          : 'badge-gray'
                      }`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="text-gray-400 text-sm">{job.fuzzer_type || 'file'}</td>
                  <td>{job.total_testcases?.toLocaleString() || 0}</td>
                  <td>{job.crash_count || 0}</td>
                  <td>{job.vm_count || 0}</td>
                  <td>
                    <div className="flex items-center space-x-2">
                      {job.status !== 'running' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleStart(job.job_id); }}
                          disabled={actionInProgress !== null}
                          className={`p-2 text-green-400 hover:bg-green-900/20 rounded transition-colors ${actionInProgress === `start-${job.job_id}` ? 'animate-pulse' : ''} ${actionInProgress !== null ? 'opacity-50 cursor-not-allowed' : ''}`}
                          title="Start"
                        >
                          <Play className="h-4 w-4" />
                        </button>
                      )}
                      {job.status === 'running' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handlePause(job.job_id); }}
                          disabled={actionInProgress !== null}
                          className={`p-2 text-yellow-400 hover:bg-yellow-900/20 rounded transition-colors ${actionInProgress === `pause-${job.job_id}` ? 'animate-pulse' : ''} ${actionInProgress !== null ? 'opacity-50 cursor-not-allowed' : ''}`}
                          title="Pause"
                        >
                          <Pause className="h-4 w-4" />
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleStop(job.job_id); }}
                        disabled={actionInProgress !== null}
                        className={`p-2 text-red-400 hover:bg-red-900/20 rounded transition-colors ${actionInProgress === `stop-${job.job_id}` ? 'animate-pulse' : ''} ${actionInProgress !== null ? 'opacity-50 cursor-not-allowed' : ''}`}
                        title="Stop"
                      >
                        <Square className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(job.job_id); }}
                        disabled={actionInProgress !== null}
                        className={`p-2 text-gray-400 hover:bg-gray-700 rounded transition-colors ${actionInProgress === `delete-${job.job_id}` ? 'animate-pulse' : ''} ${actionInProgress !== null ? 'opacity-50 cursor-not-allowed' : ''}`}
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default JobsPage;
