import React, { useState, useEffect, useRef } from 'react';
import {
  isosAPI,
  imagesAPI,
  snapshotsAPI,
  architecturesAPI,
  vmInstallAPI,
  vmConfigsAPI,
} from '../services/api';

// Icons (using simple SVG or text for now)
const Icons = {
  Upload: () => <span className="text-xl">+</span>,
  Trash: () => <span className="text-red-400">x</span>,
  Play: () => <span className="text-green-400">{'▶'}</span>,
  Stop: () => <span className="text-red-400">{'■'}</span>,
  Refresh: () => <span className="text-blue-400">↻</span>,
  Check: () => <span className="text-green-400">✓</span>,
  Warning: () => <span className="text-yellow-400">⚠</span>,
  Error: () => <span className="text-red-400">✗</span>,
  ChevronDown: () => <span>▼</span>,
  ChevronRight: () => <span>▶</span>,
};

// Default install form configuration
const defaultInstallForm = {
  disk_image: '',
  iso_path: '',
  arch: 'x86_64',
  memory: '4G',
  cpu_cores: 2,
  cpu_model: '',
  cpu_features: '',
  enable_kvm: true,
  enable_hax: false,
  boot_order: 'dc',
  boot_menu: false,
  uefi: false,
  secure_boot: false,
  display: 'vnc',
  vga: 'std',
  disk_interface: 'virtio',
  disk_cache: 'writeback',
  disk_aio: 'threads',
  cdrom_interface: 'ide',
  network_type: 'user',
  network_model: 'virtio-net-pci',
  mac_address: '',
  usb_enabled: true,
  usb_tablet: true,
  usb_keyboard: false,
  audio_enabled: false,
  audio_device: 'intel-hda',
  serial_enabled: false,
  serial_device: 'pty',
  parallel_enabled: false,
  tpm_enabled: false,
  tpm_version: '2.0',
  machine_type: '',
  rtc_base: 'utc',
  no_shutdown: false,
  no_reboot: false,
  snapshot_mode: false,
  smbios_manufacturer: '',
  smbios_product: '',
  smbios_version: '',
  smbios_serial: '',
  smbios_uuid: '',
  extra_args: '',
};

function VMSetupPage() {
  // Tab state
  const [activeTab, setActiveTab] = useState('configs');

  // Data states
  const [isos, setIsos] = useState([]);
  const [images, setImages] = useState([]);
  const [architectures, setArchitectures] = useState([]);
  const [installVMs, setInstallVMs] = useState([]);
  const [selectedImage, setSelectedImage] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [kvmStatus, setKvmStatus] = useState(null);
  const [presets, setPresets] = useState([]);
  const [savedConfigs, setSavedConfigs] = useState([]);
  const [configTags, setConfigTags] = useState([]);
  const [selectedConfigTag, setSelectedConfigTag] = useState('');

  // Loading states
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Form states
  const [newDiskName, setNewDiskName] = useState('');
  const [newDiskSize, setNewDiskSize] = useState(60);
  const [snapshotName, setSnapshotName] = useState('');

  // Installation VM form
  const [installForm, setInstallForm] = useState({ ...defaultInstallForm });
  const [selectedPreset, setSelectedPreset] = useState('custom');

  // Save config options
  const [saveConfig, setSaveConfig] = useState(true);
  const [configName, setConfigName] = useState('');
  const [configDescription, setConfigDescription] = useState('');
  const [configTagsInput, setConfigTagsInput] = useState('');

  // Expanded sections in advanced config
  const [expandedSections, setExpandedSections] = useState({
    cpu: false,
    boot: false,
    storage: false,
    network: false,
    display: false,
    devices: false,
    advanced: false,
  });

  // Messages
  const [message, setMessage] = useState(null);

  // File input refs
  const isoInputRef = useRef(null);
  const imageInputRef = useRef(null);

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  // Load snapshots when image selected
  useEffect(() => {
    if (selectedImage) {
      loadSnapshots(selectedImage.path);
    }
  }, [selectedImage]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [isosRes, imagesRes, archRes, kvmRes, installRes, presetsRes, configsRes, tagsRes] = await Promise.all([
        isosAPI.list(),
        imagesAPI.list(),
        architecturesAPI.list(),
        architecturesAPI.checkKvm(),
        vmInstallAPI.list(),
        vmInstallAPI.listPresets(),
        vmConfigsAPI.list(selectedConfigTag || undefined),
        vmConfigsAPI.listTags(),
      ]);
      setIsos(isosRes.data.data || []);
      setImages(imagesRes.data.data || []);
      setArchitectures(archRes.data.data || []);
      setKvmStatus(kvmRes.data.data);
      setInstallVMs(installRes.data.data || []);
      setPresets(presetsRes.data.data || []);
      setSavedConfigs(configsRes.data.data || []);
      setConfigTags(tagsRes.data.data || []);
    } catch (error) {
      console.error('Error loading data:', error);
      showMessage('Error loading data: ' + (error.response?.data?.detail || error.message), 'error');
    } finally {
      setLoading(false);
    }
  };

  // Load configs when tag filter changes
  const loadConfigs = async (tag) => {
    try {
      const res = await vmConfigsAPI.list(tag || undefined);
      setSavedConfigs(res.data.data || []);
    } catch (error) {
      console.error('Error loading configs:', error);
    }
  };

  const loadSnapshots = async (diskPath) => {
    try {
      const res = await snapshotsAPI.list(diskPath);
      setSnapshots(res.data.data || []);
    } catch (error) {
      console.error('Error loading snapshots:', error);
      setSnapshots([]);
    }
  };

  const showMessage = (text, type = 'info') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  // Apply preset configuration
  const applyPreset = (presetId) => {
    setSelectedPreset(presetId);
    const preset = presets.find(p => p.id === presetId);
    if (preset) {
      setInstallForm({
        ...defaultInstallForm,
        ...preset.config,
        disk_image: installForm.disk_image, // Keep current disk selection
        iso_path: installForm.iso_path, // Keep current ISO selection
      });
    } else if (presetId === 'custom') {
      setInstallForm({ ...defaultInstallForm });
    }
  };

  // Toggle section expansion
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Update form field
  const updateForm = (field, value) => {
    setInstallForm(prev => ({ ...prev, [field]: value }));
  };

  // ISO handlers
  const handleIsoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    try {
      await isosAPI.upload(file, (progressEvent) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(progress);
      });
      showMessage(`ISO '${file.name}' uploaded successfully`, 'success');
      loadData();
    } catch (error) {
      showMessage('Error uploading ISO: ' + (error.response?.data?.detail || error.message), 'error');
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (isoInputRef.current) isoInputRef.current.value = '';
    }
  };

  const handleIsoDelete = async (filename) => {
    if (!confirm(`Delete ISO '${filename}'?`)) return;
    try {
      await isosAPI.delete(filename);
      showMessage(`ISO '${filename}' deleted`, 'success');
      loadData();
    } catch (error) {
      showMessage('Error deleting ISO: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Image handlers
  const handleImageUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    try {
      await imagesAPI.upload(file, (progressEvent) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(progress);
      });
      showMessage(`Disk image '${file.name}' uploaded successfully`, 'success');
      loadData();
    } catch (error) {
      showMessage('Error uploading image: ' + (error.response?.data?.detail || error.message), 'error');
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (imageInputRef.current) imageInputRef.current.value = '';
    }
  };

  const handleCreateDisk = async () => {
    if (!newDiskName) {
      showMessage('Please enter a disk name', 'error');
      return;
    }
    try {
      await imagesAPI.create({ name: newDiskName, size_gb: newDiskSize });
      showMessage(`Disk '${newDiskName}' created (${newDiskSize}GB)`, 'success');
      setNewDiskName('');
      loadData();
    } catch (error) {
      showMessage('Error creating disk: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  const handleImageDelete = async (path) => {
    if (!confirm('Delete this disk image?')) return;
    try {
      await imagesAPI.delete(path);
      showMessage('Disk image deleted', 'success');
      if (selectedImage?.path === path) setSelectedImage(null);
      loadData();
    } catch (error) {
      showMessage('Error deleting image: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Snapshot handlers
  const handleValidateSnapshot = async (name) => {
    if (!selectedImage) return;
    try {
      const res = await snapshotsAPI.validate(selectedImage.path, name);
      const validation = res.data.data;
      if (validation.is_valid) {
        showMessage(`Snapshot '${name}' is valid for fuzzing!`, 'success');
      } else {
        showMessage(`Snapshot '${name}' is NOT valid: ${validation.warnings?.join(', ') || 'Missing VM state'}`, 'warning');
      }
    } catch (error) {
      showMessage('Error validating snapshot: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  const handleDeleteSnapshot = async (name) => {
    if (!selectedImage || !confirm(`Delete snapshot '${name}'?`)) return;
    try {
      await snapshotsAPI.delete(selectedImage.path, name);
      showMessage(`Snapshot '${name}' deleted`, 'success');
      loadSnapshots(selectedImage.path);
    } catch (error) {
      showMessage('Error deleting snapshot: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // Installation VM handlers
  const handleStartInstallVM = async () => {
    if (!installForm.disk_image) {
      showMessage('Please select a disk image', 'error');
      return;
    }
    try {
      // Build the request, parsing extra_args if provided
      const request = { ...installForm };
      if (request.extra_args) {
        request.extra_args = request.extra_args.split(' ').filter(a => a.trim());
      } else {
        delete request.extra_args;
      }
      // Remove empty string values
      Object.keys(request).forEach(key => {
        if (request[key] === '') delete request[key];
      });

      // Add save config options
      request.save_config = saveConfig;
      if (saveConfig) {
        if (configName) request.config_name = configName;
        if (configDescription) request.config_description = configDescription;
        if (configTagsInput) {
          request.config_tags = configTagsInput.split(',').map(t => t.trim()).filter(t => t);
        }
      }

      const res = await vmInstallAPI.start(request);
      const message = saveConfig && res.data.config_saved
        ? 'Configuration saved! Installation VM started - connect via VNC to install OS.'
        : 'Installation VM started! Connect via VNC to install OS.';
      showMessage(message, 'success');
      loadData();

      // Reset save config form
      if (saveConfig) {
        setConfigName('');
        setConfigDescription('');
        setConfigTagsInput('');
      }
    } catch (error) {
      showMessage('Error starting VM: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  const handleStopInstallVM = async (vmId) => {
    try {
      await vmInstallAPI.stop(vmId);
      showMessage('VM stopped', 'success');
      loadData();
    } catch (error) {
      showMessage('Error stopping VM: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  const handleCreateVMSnapshot = async (vmId) => {
    const name = prompt('Enter snapshot name:', 'fuzzing-ready');
    if (!name) return;
    try {
      await vmInstallAPI.createSnapshot(vmId, name);
      showMessage(`Snapshot '${name}' created with VM state!`, 'success');
      loadData();
    } catch (error) {
      showMessage('Error creating snapshot: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  // VM Config handlers
  const handleLoadConfig = async (config) => {
    // Apply config values to the install form
    setInstallForm({
      ...defaultInstallForm,
      disk_image: config.disk_image || '',
      iso_path: config.iso_path || '',
      arch: config.arch || 'x86_64',
      memory: config.memory || '4G',
      cpu_cores: config.cpu_cores || 2,
      cpu_model: config.cpu_model || '',
      cpu_features: config.cpu_features || '',
      enable_kvm: config.enable_kvm !== false,
      enable_hax: config.enable_hax || false,
      boot_order: config.boot_order || 'dc',
      boot_menu: config.boot_menu || false,
      uefi: config.uefi || false,
      secure_boot: config.secure_boot || false,
      display: config.display || 'vnc',
      vga: config.vga || 'std',
      disk_interface: config.disk_interface || 'virtio',
      disk_cache: config.disk_cache || 'writeback',
      disk_aio: config.disk_aio || 'threads',
      cdrom_interface: config.cdrom_interface || 'ide',
      network_type: config.network_type || 'user',
      network_model: config.network_model || 'virtio-net-pci',
      mac_address: config.mac_address || '',
      usb_enabled: config.usb_enabled !== false,
      usb_tablet: config.usb_tablet !== false,
      usb_keyboard: config.usb_keyboard || false,
      audio_enabled: config.audio_enabled || false,
      audio_device: config.audio_device || 'intel-hda',
      serial_enabled: config.serial_enabled || false,
      serial_device: config.serial_device || 'pty',
      parallel_enabled: config.parallel_enabled || false,
      tpm_enabled: config.tpm_enabled || false,
      tpm_version: config.tpm_version || '2.0',
      machine_type: config.machine_type || '',
      rtc_base: config.rtc_base || 'utc',
      no_shutdown: config.no_shutdown || false,
      no_reboot: config.no_reboot || false,
      snapshot_mode: config.snapshot_mode || false,
      smbios_manufacturer: config.smbios_manufacturer || '',
      smbios_product: config.smbios_product || '',
      smbios_version: config.smbios_version || '',
      smbios_serial: config.smbios_serial || '',
      smbios_uuid: config.smbios_uuid || '',
      extra_args: Array.isArray(config.extra_args) ? config.extra_args.join(' ') : (config.extra_args || ''),
    });
    setSelectedPreset('custom');
    setConfigName(config.name || '');
    setConfigDescription(config.description || '');
    setConfigTagsInput((config.tags || []).join(', '));
    setActiveTab('install');
    showMessage(`Loaded config: ${config.name}`, 'success');
  };

  const handleDeleteConfig = async (configId) => {
    if (!confirm('Delete this VM configuration?')) return;
    try {
      await vmConfigsAPI.delete(configId);
      showMessage('Configuration deleted', 'success');
      loadData();
    } catch (error) {
      showMessage('Error deleting config: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  const handleDuplicateConfig = async (configId, currentName) => {
    const newName = prompt('Enter name for duplicate:', `${currentName} (Copy)`);
    if (!newName) return;
    try {
      await vmConfigsAPI.duplicate(configId, newName);
      showMessage(`Configuration duplicated as: ${newName}`, 'success');
      loadData();
    } catch (error) {
      showMessage('Error duplicating config: ' + (error.response?.data?.detail || error.message), 'error');
    }
  };

  const handleFilterByTag = (tag) => {
    setSelectedConfigTag(tag);
    loadConfigs(tag);
  };

  // Collapsible Section Component
  const Section = ({ title, name, children }) => (
    <div className="border border-gray-600 rounded-lg mb-2">
      <button
        onClick={() => toggleSection(name)}
        className="w-full px-4 py-3 flex items-center justify-between text-left bg-gray-700 hover:bg-gray-650 rounded-t-lg"
      >
        <span className="text-sm font-medium text-gray-200">{title}</span>
        {expandedSections[name] ? <Icons.ChevronDown /> : <Icons.ChevronRight />}
      </button>
      {expandedSections[name] && (
        <div className="p-4 bg-gray-750">
          {children}
        </div>
      )}
    </div>
  );

  // Form Input Components
  const SelectInput = ({ label, value, onChange, options, help }) => (
    <div className="mb-3">
      <label className="block text-sm text-gray-400 mb-1">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
      >
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {help && <div className="text-xs text-gray-500 mt-1">{help}</div>}
    </div>
  );

  const TextInput = ({ label, value, onChange, placeholder, help }) => (
    <div className="mb-3">
      <label className="block text-sm text-gray-400 mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white text-sm placeholder-gray-400 focus:outline-none focus:border-primary-500"
      />
      {help && <div className="text-xs text-gray-500 mt-1">{help}</div>}
    </div>
  );

  const CheckboxInput = ({ label, checked, onChange, help }) => (
    <div className="mb-3">
      <label className="flex items-center space-x-2 cursor-pointer">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 rounded"
        />
        <span className="text-sm text-gray-300">{label}</span>
      </label>
      {help && <div className="text-xs text-gray-500 mt-1 ml-6">{help}</div>}
    </div>
  );

  // Render tabs
  const tabs = [
    { id: 'configs', label: 'Saved Configs' },
    { id: 'isos', label: 'ISO Files' },
    { id: 'images', label: 'Disk Images' },
    { id: 'snapshots', label: 'Snapshots' },
    { id: 'install', label: 'Install VM' },
    { id: 'architectures', label: 'Architectures' },
  ];

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-2">VM Setup</h1>
        <p className="text-gray-400">Manage ISOs, disk images, and create VMs for fuzzing</p>
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

      {/* Tabs */}
      <div className="flex space-x-1 mb-6 bg-gray-800 p-1 rounded-lg">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-primary-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
        <button
          onClick={loadData}
          className="ml-auto px-3 py-2 text-gray-400 hover:text-white"
          title="Refresh"
        >
          <Icons.Refresh />
        </button>
      </div>

      {/* Tab Content */}
      <div className="bg-gray-800 rounded-lg p-6">
        {/* Saved Configs Tab */}
        {activeTab === 'configs' && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-white">Saved VM Configurations</h2>
              <button
                onClick={() => setActiveTab('install')}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                Create New Config
              </button>
            </div>

            {/* Tag Filter */}
            {configTags.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                <button
                  onClick={() => handleFilterByTag('')}
                  className={`px-3 py-1 rounded-full text-sm ${
                    selectedConfigTag === ''
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  All
                </button>
                {configTags.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => handleFilterByTag(tag)}
                    className={`px-3 py-1 rounded-full text-sm ${
                      selectedConfigTag === tag
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}

            {loading ? (
              <div className="text-center py-8 text-gray-400">Loading...</div>
            ) : savedConfigs.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <div className="text-5xl mb-4">{'{'}</div>
                <p className="text-lg">No saved VM configurations found</p>
                <p className="text-sm mt-2">Create a VM and save its configuration to see it here.</p>
                <button
                  onClick={() => setActiveTab('install')}
                  className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                >
                  Create Your First Config
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {savedConfigs.map((config) => (
                  <div
                    key={config.id}
                    className="p-4 bg-gray-700 rounded-lg hover:bg-gray-650 transition-colors"
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-white font-medium truncate flex-1">{config.name}</h3>
                      <div className="flex space-x-1 ml-2">
                        <button
                          onClick={() => handleLoadConfig(config)}
                          className="p-1.5 text-green-400 hover:text-green-300 hover:bg-gray-600 rounded"
                          title="Load this config"
                        >
                          <Icons.Play />
                        </button>
                        <button
                          onClick={() => handleDuplicateConfig(config.id, config.name)}
                          className="p-1.5 text-blue-400 hover:text-blue-300 hover:bg-gray-600 rounded"
                          title="Duplicate"
                        >
                          {'++'}
                        </button>
                        <button
                          onClick={() => handleDeleteConfig(config.id)}
                          className="p-1.5 text-red-400 hover:text-red-300 hover:bg-gray-600 rounded"
                          title="Delete"
                        >
                          <Icons.Trash />
                        </button>
                      </div>
                    </div>

                    {config.description && (
                      <p className="text-sm text-gray-400 mb-2 line-clamp-2">{config.description}</p>
                    )}

                    <div className="text-xs text-gray-500 space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-gray-400">Arch:</span>
                        <span className="text-gray-300">{config.arch || 'x86_64'}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-400">RAM:</span>
                        <span className="text-gray-300">{config.memory || '4G'}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-400">CPU:</span>
                        <span className="text-gray-300">{config.cpu_cores || 2}</span>
                      </div>
                      <div className="truncate">
                        <span className="text-gray-400">Disk:</span>{' '}
                        <span className="text-gray-300">{config.disk_image?.split('/').pop() || 'None'}</span>
                      </div>
                      {config.snapshot_name && (
                        <div>
                          <span className="text-gray-400">Snapshot:</span>{' '}
                          <span className="text-green-400">{config.snapshot_name}</span>
                        </div>
                      )}
                    </div>

                    {config.tags && config.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {config.tags.map((tag) => (
                          <span
                            key={tag}
                            className="px-2 py-0.5 bg-gray-600 text-gray-300 text-xs rounded"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="mt-2 pt-2 border-t border-gray-600 text-xs text-gray-500">
                      Created: {new Date(config.created_at).toLocaleDateString()}
                      {config.updated_at !== config.created_at && (
                        <span> | Updated: {new Date(config.updated_at).toLocaleDateString()}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ISOs Tab */}
        {activeTab === 'isos' && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-white">ISO Files</h2>
              <div>
                <input
                  type="file"
                  ref={isoInputRef}
                  accept=".iso"
                  onChange={handleIsoUpload}
                  className="hidden"
                />
                <button
                  onClick={() => isoInputRef.current?.click()}
                  disabled={uploading}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  Upload ISO
                </button>
              </div>
            </div>

            {loading ? (
              <div className="text-center py-8 text-gray-400">Loading...</div>
            ) : isos.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                No ISO files found. Upload an ISO to get started.
              </div>
            ) : (
              <div className="space-y-2">
                {isos.map((iso) => (
                  <div
                    key={iso.path}
                    className="flex items-center justify-between p-4 bg-gray-700 rounded-lg"
                  >
                    <div>
                      <div className="text-white font-medium">{iso.filename}</div>
                      <div className="text-sm text-gray-400">{iso.size_human}</div>
                    </div>
                    <button
                      onClick={() => handleIsoDelete(iso.filename)}
                      className="p-2 text-red-400 hover:text-red-300"
                    >
                      <Icons.Trash />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Disk Images Tab */}
        {activeTab === 'images' && (
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-white">Disk Images</h2>
              <div className="flex space-x-2">
                <input
                  type="file"
                  ref={imageInputRef}
                  accept=".qcow2,.qcow,.img"
                  onChange={handleImageUpload}
                  className="hidden"
                />
                <button
                  onClick={() => imageInputRef.current?.click()}
                  disabled={uploading}
                  className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-500 disabled:opacity-50"
                >
                  Upload Image
                </button>
              </div>
            </div>

            {/* Create new disk form */}
            <div className="mb-6 p-4 bg-gray-700 rounded-lg">
              <h3 className="text-sm font-medium text-gray-300 mb-3">Create New Disk</h3>
              <div className="flex space-x-4">
                <input
                  type="text"
                  value={newDiskName}
                  onChange={(e) => setNewDiskName(e.target.value)}
                  placeholder="Disk name"
                  className="flex-1 px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
                />
                <div className="flex items-center space-x-2">
                  <input
                    type="number"
                    value={newDiskSize}
                    onChange={(e) => setNewDiskSize(parseInt(e.target.value) || 1)}
                    min="1"
                    max="2000"
                    className="w-24 px-3 py-2 bg-gray-600 border border-gray-500 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  />
                  <span className="text-gray-400">GB</span>
                </div>
                <button
                  onClick={handleCreateDisk}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                >
                  Create
                </button>
              </div>
            </div>

            {loading ? (
              <div className="text-center py-8 text-gray-400">Loading...</div>
            ) : images.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                No disk images found. Create or upload a disk image.
              </div>
            ) : (
              <div className="space-y-2">
                {images.map((img) => (
                  <div
                    key={img.path}
                    onClick={() => setSelectedImage(img)}
                    className={`flex items-center justify-between p-4 rounded-lg cursor-pointer ${
                      selectedImage?.path === img.path
                        ? 'bg-primary-900/50 border border-primary-600'
                        : 'bg-gray-700 hover:bg-gray-600'
                    }`}
                  >
                    <div>
                      <div className="text-white font-medium">{img.filename}</div>
                      <div className="text-sm text-gray-400">
                        {img.virtual_size_human} virtual | {img.actual_size_human} actual | {img.snapshot_count} snapshots
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleImageDelete(img.path); }}
                      className="p-2 text-red-400 hover:text-red-300"
                    >
                      <Icons.Trash />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Snapshots Tab */}
        {activeTab === 'snapshots' && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">Snapshots</h2>

            {!selectedImage ? (
              <div className="text-center py-8 text-gray-400">
                Select a disk image in the "Disk Images" tab to view snapshots.
              </div>
            ) : (
              <div>
                <div className="mb-4 p-4 bg-gray-700 rounded-lg">
                  <span className="text-gray-400">Selected disk: </span>
                  <span className="text-white font-medium">{selectedImage.filename}</span>
                </div>

                {snapshots.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">
                    No snapshots found. Create a snapshot by installing an OS in the "Install VM" tab.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {snapshots.map((snap) => (
                      <div
                        key={snap.name}
                        className="flex items-center justify-between p-4 bg-gray-700 rounded-lg"
                      >
                        <div className="flex items-center space-x-4">
                          <div>
                            {snap.has_vm_state ? (
                              <span className="text-green-400"><Icons.Check /></span>
                            ) : (
                              <span className="text-yellow-400"><Icons.Warning /></span>
                            )}
                          </div>
                          <div>
                            <div className="text-white font-medium">{snap.name}</div>
                            <div className="text-sm text-gray-400">
                              VM State: {snap.vm_state_size} |
                              {snap.has_vm_state ? ' Ready for fuzzing' : ' Disk-only (not usable for fuzzing)'}
                            </div>
                          </div>
                        </div>
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleValidateSnapshot(snap.name)}
                            className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                          >
                            Validate
                          </button>
                          <button
                            onClick={() => handleDeleteSnapshot(snap.name)}
                            className="p-2 text-red-400 hover:text-red-300"
                          >
                            <Icons.Trash />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Install VM Tab - ENHANCED */}
        {activeTab === 'install' && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">Install VM</h2>

            {/* KVM Status */}
            {kvmStatus && (
              <div className={`mb-4 p-4 rounded-lg ${
                kvmStatus.kvm_usable
                  ? 'bg-green-900/30 border border-green-700'
                  : 'bg-yellow-900/30 border border-yellow-700'
              }`}>
                <div className="flex items-center space-x-2">
                  {kvmStatus.kvm_usable ? (
                    <Icons.Check />
                  ) : (
                    <Icons.Warning />
                  )}
                  <span className={kvmStatus.kvm_usable ? 'text-green-300' : 'text-yellow-300'}>
                    {kvmStatus.kvm_usable
                      ? 'KVM acceleration available - VMs will run at near-native speed'
                      : kvmStatus.error_message || 'KVM not available - VMs will be slower'}
                  </span>
                </div>
              </div>
            )}

            {/* Running VMs */}
            {installVMs.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-medium text-gray-300 mb-3">Running Installation VMs</h3>
                <div className="space-y-2">
                  {installVMs.map((vm) => (
                    <div
                      key={vm.vm_id}
                      className="p-4 bg-gray-700 rounded-lg"
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="text-white font-medium">VM #{vm.vm_id}</div>
                          <div className="text-sm text-gray-400">
                            VNC Port: {vm.vnc_port} |
                            Status: <span className={vm.status === 'running' ? 'text-green-400' : 'text-red-400'}>{vm.status}</span>
                          </div>
                          {vm.vnc_websocket_port && (
                            <div className="text-sm text-blue-400 mt-1">
                              noVNC: <a href={`http://${window.location.hostname}:${vm.vnc_websocket_port}/vnc.html`} target="_blank" rel="noopener noreferrer" className="underline">
                                Open Console
                              </a>
                            </div>
                          )}
                        </div>
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleCreateVMSnapshot(vm.vm_id)}
                            className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                          >
                            Create Snapshot
                          </button>
                          <button
                            onClick={() => handleStopInstallVM(vm.vm_id)}
                            className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
                          >
                            Stop
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Start new VM form */}
            <div className="p-4 bg-gray-700 rounded-lg">
              <h3 className="text-sm font-medium text-gray-300 mb-4">Start New Installation</h3>

              {/* Preset Selection */}
              <div className="mb-6">
                <label className="block text-sm text-gray-400 mb-2">Configuration Preset</label>
                <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                  {presets.map((preset) => (
                    <button
                      key={preset.id}
                      onClick={() => applyPreset(preset.id)}
                      className={`p-3 rounded-lg text-left transition-colors ${
                        selectedPreset === preset.id
                          ? 'bg-primary-600 text-white border-2 border-primary-400'
                          : 'bg-gray-600 text-gray-300 hover:bg-gray-550 border-2 border-transparent'
                      }`}
                    >
                      <div className="font-medium text-sm">{preset.name}</div>
                      <div className="text-xs opacity-75 truncate">{preset.description}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Basic Configuration */}
              <div className="grid grid-cols-2 gap-4 mb-6">
                <SelectInput
                  label="Disk Image *"
                  value={installForm.disk_image}
                  onChange={(v) => updateForm('disk_image', v)}
                  options={[
                    { value: '', label: 'Select disk image...' },
                    ...images.map(img => ({ value: img.path, label: img.filename }))
                  ]}
                />

                <SelectInput
                  label="ISO File (optional)"
                  value={installForm.iso_path}
                  onChange={(v) => updateForm('iso_path', v)}
                  options={[
                    { value: '', label: 'No ISO (boot from disk)' },
                    ...isos.map(iso => ({ value: iso.path, label: iso.filename }))
                  ]}
                  help="Leave empty to boot from existing disk"
                />

                <SelectInput
                  label="Architecture"
                  value={installForm.arch}
                  onChange={(v) => updateForm('arch', v)}
                  options={architectures.filter(a => a.available).map(arch => ({
                    value: arch.name,
                    label: arch.display_name
                  }))}
                />

                <SelectInput
                  label="Memory"
                  value={installForm.memory}
                  onChange={(v) => updateForm('memory', v)}
                  options={[
                    { value: '256M', label: '256 MB' },
                    { value: '512M', label: '512 MB' },
                    { value: '1G', label: '1 GB' },
                    { value: '2G', label: '2 GB' },
                    { value: '4G', label: '4 GB' },
                    { value: '8G', label: '8 GB' },
                    { value: '16G', label: '16 GB' },
                    { value: '32G', label: '32 GB' },
                  ]}
                />

                <SelectInput
                  label="CPU Cores"
                  value={installForm.cpu_cores}
                  onChange={(v) => updateForm('cpu_cores', parseInt(v))}
                  options={[1,2,4,8,16,32].map(n => ({ value: n, label: `${n} Core${n > 1 ? 's' : ''}` }))}
                />

                <div className="flex items-center space-x-4">
                  <CheckboxInput
                    label="Enable KVM"
                    checked={installForm.enable_kvm}
                    onChange={(v) => updateForm('enable_kvm', v)}
                  />
                  <CheckboxInput
                    label="UEFI Boot"
                    checked={installForm.uefi}
                    onChange={(v) => updateForm('uefi', v)}
                  />
                </div>
              </div>

              {/* Advanced Configuration Sections */}
              <div className="mb-4">
                <h4 className="text-sm font-medium text-gray-400 mb-2">Advanced Configuration</h4>

                {/* CPU Section */}
                <Section title="CPU Settings" name="cpu">
                  <div className="grid grid-cols-2 gap-4">
                    <TextInput
                      label="CPU Model"
                      value={installForm.cpu_model}
                      onChange={(v) => updateForm('cpu_model', v)}
                      placeholder="e.g., host, qemu64, Skylake-Client"
                      help="Leave empty for auto-detection"
                    />
                    <TextInput
                      label="CPU Features"
                      value={installForm.cpu_features}
                      onChange={(v) => updateForm('cpu_features', v)}
                      placeholder="e.g., +vmx,-svm"
                      help="Features to enable/disable"
                    />
                    <CheckboxInput
                      label="Enable HAXM (Windows/macOS)"
                      checked={installForm.enable_hax}
                      onChange={(v) => updateForm('enable_hax', v)}
                    />
                  </div>
                </Section>

                {/* Boot Section */}
                <Section title="Boot Configuration" name="boot">
                  <div className="grid grid-cols-2 gap-4">
                    <TextInput
                      label="Boot Order"
                      value={installForm.boot_order}
                      onChange={(v) => updateForm('boot_order', v)}
                      placeholder="dc"
                      help="d=cdrom, c=disk, n=network (e.g., 'dc', 'cdn')"
                    />
                    <SelectInput
                      label="Machine Type"
                      value={installForm.machine_type}
                      onChange={(v) => updateForm('machine_type', v)}
                      options={[
                        { value: '', label: 'Auto (q35 for x86)' },
                        { value: 'pc', label: 'PC (i440FX)' },
                        { value: 'q35', label: 'Q35 (Modern)' },
                        { value: 'virt', label: 'virt (ARM/RISC-V)' },
                        { value: 'malta', label: 'Malta (MIPS)' },
                        { value: 'raspi3', label: 'Raspberry Pi 3' },
                      ]}
                    />
                    <CheckboxInput
                      label="Boot Menu (F12)"
                      checked={installForm.boot_menu}
                      onChange={(v) => updateForm('boot_menu', v)}
                    />
                    <CheckboxInput
                      label="Secure Boot"
                      checked={installForm.secure_boot}
                      onChange={(v) => updateForm('secure_boot', v)}
                      help="Requires UEFI"
                    />
                  </div>
                </Section>

                {/* Storage Section */}
                <Section title="Storage Configuration" name="storage">
                  <div className="grid grid-cols-2 gap-4">
                    <SelectInput
                      label="Disk Interface"
                      value={installForm.disk_interface}
                      onChange={(v) => updateForm('disk_interface', v)}
                      options={[
                        { value: 'virtio', label: 'VirtIO (Fast)' },
                        { value: 'ide', label: 'IDE (Compatible)' },
                        { value: 'scsi', label: 'SCSI' },
                        { value: 'nvme', label: 'NVMe' },
                        { value: 'sd', label: 'SD Card' },
                      ]}
                    />
                    <SelectInput
                      label="Disk Cache"
                      value={installForm.disk_cache}
                      onChange={(v) => updateForm('disk_cache', v)}
                      options={[
                        { value: 'writeback', label: 'Writeback (Fast)' },
                        { value: 'writethrough', label: 'Writethrough (Safe)' },
                        { value: 'none', label: 'None (Direct)' },
                        { value: 'unsafe', label: 'Unsafe (Fastest)' },
                      ]}
                    />
                    <SelectInput
                      label="Disk AIO"
                      value={installForm.disk_aio}
                      onChange={(v) => updateForm('disk_aio', v)}
                      options={[
                        { value: 'threads', label: 'Threads (Default)' },
                        { value: 'native', label: 'Native (Linux)' },
                        { value: 'io_uring', label: 'io_uring (Fast)' },
                      ]}
                    />
                    <SelectInput
                      label="CD-ROM Interface"
                      value={installForm.cdrom_interface}
                      onChange={(v) => updateForm('cdrom_interface', v)}
                      options={[
                        { value: 'ide', label: 'IDE' },
                        { value: 'scsi', label: 'SCSI' },
                      ]}
                    />
                    <CheckboxInput
                      label="Snapshot Mode (no disk writes)"
                      checked={installForm.snapshot_mode}
                      onChange={(v) => updateForm('snapshot_mode', v)}
                    />
                  </div>
                </Section>

                {/* Network Section */}
                <Section title="Network Configuration" name="network">
                  <div className="grid grid-cols-2 gap-4">
                    <SelectInput
                      label="Network Type"
                      value={installForm.network_type}
                      onChange={(v) => updateForm('network_type', v)}
                      options={[
                        { value: 'user', label: 'User Mode (NAT)' },
                        { value: 'tap', label: 'TAP Interface' },
                        { value: 'bridge', label: 'Bridged' },
                        { value: 'none', label: 'No Network' },
                      ]}
                    />
                    <SelectInput
                      label="Network Model"
                      value={installForm.network_model}
                      onChange={(v) => updateForm('network_model', v)}
                      options={[
                        { value: 'virtio-net-pci', label: 'VirtIO (Fast)' },
                        { value: 'e1000', label: 'Intel E1000' },
                        { value: 'e1000e', label: 'Intel E1000E' },
                        { value: 'rtl8139', label: 'Realtek RTL8139' },
                      ]}
                    />
                    <TextInput
                      label="MAC Address"
                      value={installForm.mac_address}
                      onChange={(v) => updateForm('mac_address', v)}
                      placeholder="Auto-generated"
                      help="Leave empty for auto-generated MAC"
                    />
                  </div>
                </Section>

                {/* Display Section */}
                <Section title="Display & Graphics" name="display">
                  <div className="grid grid-cols-2 gap-4">
                    <SelectInput
                      label="Display Type"
                      value={installForm.display}
                      onChange={(v) => updateForm('display', v)}
                      options={[
                        { value: 'vnc', label: 'VNC' },
                        { value: 'spice', label: 'SPICE' },
                        { value: 'none', label: 'None (Headless)' },
                      ]}
                    />
                    <SelectInput
                      label="VGA Type"
                      value={installForm.vga}
                      onChange={(v) => updateForm('vga', v)}
                      options={[
                        { value: 'std', label: 'Standard VGA' },
                        { value: 'cirrus', label: 'Cirrus (Legacy)' },
                        { value: 'vmware', label: 'VMware SVGA' },
                        { value: 'qxl', label: 'QXL (SPICE)' },
                        { value: 'virtio', label: 'VirtIO GPU' },
                        { value: 'none', label: 'None' },
                      ]}
                    />
                  </div>
                </Section>

                {/* Devices Section */}
                <Section title="Devices & Peripherals" name="devices">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h5 className="text-sm text-gray-300 mb-2">USB</h5>
                      <CheckboxInput
                        label="USB Controller"
                        checked={installForm.usb_enabled}
                        onChange={(v) => updateForm('usb_enabled', v)}
                      />
                      <CheckboxInput
                        label="USB Tablet (better mouse)"
                        checked={installForm.usb_tablet}
                        onChange={(v) => updateForm('usb_tablet', v)}
                      />
                      <CheckboxInput
                        label="USB Keyboard"
                        checked={installForm.usb_keyboard}
                        onChange={(v) => updateForm('usb_keyboard', v)}
                      />
                    </div>
                    <div>
                      <h5 className="text-sm text-gray-300 mb-2">Audio</h5>
                      <CheckboxInput
                        label="Enable Audio"
                        checked={installForm.audio_enabled}
                        onChange={(v) => updateForm('audio_enabled', v)}
                      />
                      {installForm.audio_enabled && (
                        <SelectInput
                          label="Audio Device"
                          value={installForm.audio_device}
                          onChange={(v) => updateForm('audio_device', v)}
                          options={[
                            { value: 'intel-hda', label: 'Intel HDA' },
                            { value: 'ac97', label: 'AC97' },
                            { value: 'es1370', label: 'ES1370' },
                          ]}
                        />
                      )}
                    </div>
                    <div>
                      <h5 className="text-sm text-gray-300 mb-2">Serial/Parallel</h5>
                      <CheckboxInput
                        label="Serial Port"
                        checked={installForm.serial_enabled}
                        onChange={(v) => updateForm('serial_enabled', v)}
                      />
                      <CheckboxInput
                        label="Parallel Port"
                        checked={installForm.parallel_enabled}
                        onChange={(v) => updateForm('parallel_enabled', v)}
                      />
                    </div>
                    <div>
                      <h5 className="text-sm text-gray-300 mb-2">TPM (Windows 11)</h5>
                      <CheckboxInput
                        label="Enable TPM"
                        checked={installForm.tpm_enabled}
                        onChange={(v) => updateForm('tpm_enabled', v)}
                        help="Required for Windows 11"
                      />
                      {installForm.tpm_enabled && (
                        <SelectInput
                          label="TPM Version"
                          value={installForm.tpm_version}
                          onChange={(v) => updateForm('tpm_version', v)}
                          options={[
                            { value: '2.0', label: 'TPM 2.0' },
                            { value: '1.2', label: 'TPM 1.2' },
                          ]}
                        />
                      )}
                    </div>
                  </div>
                </Section>

                {/* Advanced Section */}
                <Section title="Advanced Options" name="advanced">
                  <div className="grid grid-cols-2 gap-4">
                    <SelectInput
                      label="RTC Base"
                      value={installForm.rtc_base}
                      onChange={(v) => updateForm('rtc_base', v)}
                      options={[
                        { value: 'utc', label: 'UTC' },
                        { value: 'localtime', label: 'Local Time (Windows)' },
                      ]}
                    />
                    <div>
                      <CheckboxInput
                        label="No Shutdown"
                        checked={installForm.no_shutdown}
                        onChange={(v) => updateForm('no_shutdown', v)}
                        help="Don't exit QEMU on guest shutdown"
                      />
                      <CheckboxInput
                        label="No Reboot"
                        checked={installForm.no_reboot}
                        onChange={(v) => updateForm('no_reboot', v)}
                        help="Exit instead of rebooting"
                      />
                    </div>
                  </div>
                  <div className="mt-4">
                    <h5 className="text-sm text-gray-300 mb-2">SMBIOS/DMI (System Info)</h5>
                    <div className="grid grid-cols-2 gap-4">
                      <TextInput
                        label="Manufacturer"
                        value={installForm.smbios_manufacturer}
                        onChange={(v) => updateForm('smbios_manufacturer', v)}
                        placeholder="e.g., Dell Inc."
                      />
                      <TextInput
                        label="Product Name"
                        value={installForm.smbios_product}
                        onChange={(v) => updateForm('smbios_product', v)}
                        placeholder="e.g., OptiPlex 7080"
                      />
                      <TextInput
                        label="Version"
                        value={installForm.smbios_version}
                        onChange={(v) => updateForm('smbios_version', v)}
                        placeholder="e.g., 1.0"
                      />
                      <TextInput
                        label="Serial Number"
                        value={installForm.smbios_serial}
                        onChange={(v) => updateForm('smbios_serial', v)}
                        placeholder="e.g., ABC123"
                      />
                    </div>
                  </div>
                  <div className="mt-4">
                    <TextInput
                      label="Extra QEMU Arguments"
                      value={installForm.extra_args}
                      onChange={(v) => updateForm('extra_args', v)}
                      placeholder="e.g., -device virtio-balloon"
                      help="Space-separated additional QEMU command-line arguments"
                    />
                  </div>
                </Section>
              </div>

              {/* Save Configuration Section */}
              <div className="mt-6 p-4 bg-gray-600 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-medium text-gray-200">Save Configuration</h4>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={saveConfig}
                      onChange={(e) => setSaveConfig(e.target.checked)}
                      className="w-4 h-4 rounded"
                    />
                    <span className="text-sm text-gray-300">Save this config for later use</span>
                  </label>
                </div>

                {saveConfig && (
                  <div className="grid grid-cols-2 gap-4">
                    <TextInput
                      label="Config Name"
                      value={configName}
                      onChange={setConfigName}
                      placeholder="e.g., Windows 11 Fuzzing VM"
                      help="A descriptive name for this configuration"
                    />
                    <TextInput
                      label="Tags (comma-separated)"
                      value={configTagsInput}
                      onChange={setConfigTagsInput}
                      placeholder="e.g., windows, fuzzing, test"
                      help="Tags help organize and filter configs"
                    />
                    <div className="col-span-2">
                      <TextInput
                        label="Description (optional)"
                        value={configDescription}
                        onChange={setConfigDescription}
                        placeholder="Describe this VM configuration..."
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-4">
                <button
                  onClick={handleStartInstallVM}
                  disabled={!installForm.disk_image}
                  className="w-full px-4 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {saveConfig ? 'Save Config & Start Installation VM' : 'Start Installation VM'}
                </button>
              </div>

              <div className="mt-4 p-3 bg-gray-600 rounded-lg text-sm text-gray-300">
                <strong>Instructions:</strong>
                <ol className="list-decimal list-inside mt-2 space-y-1">
                  <li>Select or create a disk image</li>
                  <li>Choose a preset or customize settings</li>
                  <li>Optionally select an ISO to boot from</li>
                  <li>Click "Start Installation VM"</li>
                  <li>Connect via VNC to complete OS installation</li>
                  <li>Once installed, click "Create Snapshot" to save the VM state</li>
                  <li>Use the snapshot in Jobs for fuzzing!</li>
                </ol>
              </div>
            </div>
          </div>
        )}

        {/* Architectures Tab */}
        {activeTab === 'architectures' && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">Supported Architectures</h2>

            {loading ? (
              <div className="text-center py-8 text-gray-400">Loading...</div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {architectures.map((arch) => (
                  <div
                    key={arch.name}
                    className={`p-4 rounded-lg ${
                      arch.available
                        ? 'bg-gray-700'
                        : 'bg-gray-700 opacity-50'
                    }`}
                  >
                    <div className="flex items-center space-x-2">
                      {arch.available ? (
                        <span className="text-green-400"><Icons.Check /></span>
                      ) : (
                        <span className="text-red-400"><Icons.Error /></span>
                      )}
                      <span className="text-white font-medium">{arch.name}</span>
                    </div>
                    <div className="text-sm text-gray-400 mt-1">{arch.display_name}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {arch.word_size}-bit | {arch.endianness} endian
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default VMSetupPage;
