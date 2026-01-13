import React, { useState, useEffect } from 'react';
import {
  Save, RotateCcw, Download, Upload, Info, Settings, Server,
  Shield, FolderOpen, Monitor, Clock, Cpu, Bug, Database,
  ChevronDown, ChevronRight, Eye, Zap, HardDrive
} from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { configAPI } from '../services/api';

const ConfigPage = () => {
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    general: true,
    network: true,
    vm: true,
    screenshots: true,
    fuzzer: true,
    advanced: false,
    security: false,
    paths: false
  });

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await configAPI.get();
      setConfig(response.data.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setSaveSuccess(false);
      await configAPI.update(config);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset to default configuration?')) return;

    try {
      setSaving(true);
      await configAPI.reset();
      await fetchConfig();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async () => {
    try {
      const response = await configAPI.export();
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'fawkes_config.json');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to export configuration');
    }
  };

  const updateConfig = (key, value) => {
    setConfig({ ...config, [key]: value });
  };

  const toggleSection = (section) => {
    setExpandedSections({ ...expandedSections, [section]: !expandedSections[section] });
  };

  if (loading) return <LoadingSpinner size="lg" message="Loading configuration..." />;
  if (error) return <ErrorMessage message={error} onRetry={fetchConfig} />;

  const fuzzingMode = config.fuzzing_mode || 'local';
  const isController = fuzzingMode === 'controller';
  const isWorker = fuzzingMode === 'worker';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Configuration</h1>
          <p className="text-gray-400 mt-1">Manage Fawkes settings</p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={handleExport}
            className="btn btn-secondary flex items-center space-x-2"
          >
            <Download className="h-4 w-4" />
            <span>Export</span>
          </button>
          <button
            onClick={handleReset}
            className="btn btn-secondary flex items-center space-x-2"
            disabled={saving}
          >
            <RotateCcw className="h-4 w-4" />
            <span>Reset</span>
          </button>
          <button
            onClick={handleSave}
            className="btn btn-primary flex items-center space-x-2"
            disabled={saving}
          >
            <Save className="h-4 w-4" />
            <span>{saving ? 'Saving...' : 'Save'}</span>
          </button>
        </div>
      </div>

      {saveSuccess && (
        <div className="card bg-green-900/20 border border-green-800">
          <p className="text-green-400">Configuration saved successfully!</p>
        </div>
      )}

      {/* Configuration Sections */}
      <div className="space-y-4">
        {/* General Settings */}
        <ConfigSection
          title="General Settings"
          icon={<Settings className="h-5 w-5" />}
          expanded={expandedSections.general}
          onToggle={() => toggleSection('general')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="label">Fuzzing Mode</label>
              <select
                className="select"
                value={config.fuzzing_mode || 'local'}
                onChange={(e) => updateConfig('fuzzing_mode', e.target.value)}
              >
                <option value="local">Local</option>
                <option value="controller">Controller</option>
                <option value="worker">Worker</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">
                {fuzzingMode === 'local' && 'Run fuzzing on this machine only'}
                {fuzzingMode === 'controller' && 'Act as controller to distribute work'}
                {fuzzingMode === 'worker' && 'Connect to controller for jobs'}
              </p>
            </div>
            <div>
              <label className="label">Log Level</label>
              <select
                className="select"
                value={config.log_level || 'INFO'}
                onChange={(e) => updateConfig('log_level', e.target.value)}
              >
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </div>
            <div>
              <label className="label">Poll Interval (seconds)</label>
              <input
                type="number"
                className="input"
                value={config.poll_interval || 60}
                onChange={(e) => updateConfig('poll_interval', parseInt(e.target.value))}
                min="1"
                max="3600"
              />
              <p className="text-xs text-gray-500 mt-1">Interval for polling operations</p>
            </div>
            <div>
              <label className="label">Max Retries</label>
              <input
                type="number"
                className="input"
                value={config.max_retries || 3}
                onChange={(e) => updateConfig('max_retries', parseInt(e.target.value))}
                min="0"
                max="10"
              />
              <p className="text-xs text-gray-500 mt-1">Max retries for failed operations</p>
            </div>
            <div>
              <label className="label">Job Name</label>
              <input
                type="text"
                className="input"
                value={config.job_name || 'change_me'}
                onChange={(e) => updateConfig('job_name', e.target.value)}
              />
              <p className="text-xs text-gray-500 mt-1">Default name for new jobs</p>
            </div>
          </div>
        </ConfigSection>

        {/* VM Settings */}
        <ConfigSection
          title="Virtual Machine Settings"
          icon={<Cpu className="h-5 w-5" />}
          expanded={expandedSections.vm}
          onToggle={() => toggleSection('vm')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="label">Max Parallel VMs</label>
              <input
                type="number"
                className="input"
                value={config.max_parallel_vms || config.max_vms || 5}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  updateConfig('max_parallel_vms', val);
                  updateConfig('max_vms', val);
                }}
                min="0"
                max="64"
              />
              <p className="text-xs text-gray-500 mt-1">0 = unlimited</p>
            </div>
            <div>
              <label className="label">Architecture</label>
              <select
                className="select"
                value={config.arch || 'x86_64'}
                onChange={(e) => updateConfig('arch', e.target.value)}
              >
                <option value="x86_64">x86_64</option>
                <option value="i386">i386</option>
                <option value="arm">ARM</option>
                <option value="aarch64">AArch64</option>
                <option value="mips">MIPS</option>
                <option value="mipsel">MIPS (Little Endian)</option>
                <option value="ppc">PowerPC</option>
                <option value="ppc64">PowerPC 64</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">Target VM architecture</p>
            </div>
            <div>
              <label className="label">Snapshot Name</label>
              <input
                type="text"
                className="input"
                value={config.snapshot_name || 'clean'}
                onChange={(e) => updateConfig('snapshot_name', e.target.value)}
              />
              <p className="text-xs text-gray-500 mt-1">QEMU snapshot to restore</p>
            </div>
            <div>
              <label className="label">VM Timeout (seconds)</label>
              <input
                type="number"
                className="input"
                value={config.timeout || 60}
                onChange={(e) => updateConfig('timeout', parseInt(e.target.value))}
                min="1"
                max="3600"
              />
              <p className="text-xs text-gray-500 mt-1">Timeout for VM operations</p>
            </div>
            <div>
              <label className="label">Disk Image</label>
              <input
                type="text"
                className="input"
                value={config.disk_image || '~/fawkes_test/target.qcow2'}
                onChange={(e) => updateConfig('disk_image', e.target.value)}
              />
              <p className="text-xs text-gray-500 mt-1">Path to QCOW2 disk image</p>
            </div>
            <div className="space-y-3">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={config.cleanup_stopped_vms || false}
                  onChange={(e) => updateConfig('cleanup_stopped_vms', e.target.checked)}
                  className="rounded text-primary-500"
                />
                <span className="text-sm text-gray-300">Cleanup Stopped VMs</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={config.loop || true}
                  onChange={(e) => updateConfig('loop', e.target.checked)}
                  className="rounded text-primary-500"
                />
                <span className="text-sm text-gray-300">Loop Mode</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={config.no_headless || false}
                  onChange={(e) => updateConfig('no_headless', e.target.checked)}
                  className="rounded text-primary-500"
                />
                <span className="text-sm text-gray-300">Show VM Window</span>
              </label>
            </div>
          </div>
          <div className="mt-4 pt-4 border-t border-gray-700">
            <h4 className="text-sm font-medium text-gray-300 mb-3">File Sharing</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={config.smb !== false}
                  onChange={(e) => updateConfig('smb', e.target.checked)}
                  className="rounded text-primary-500"
                />
                <span className="text-sm text-gray-300">SMB Sharing</span>
                <span className="text-xs text-gray-500">(Windows guests)</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={config.vfs || false}
                  onChange={(e) => updateConfig('vfs', e.target.checked)}
                  className="rounded text-primary-500"
                />
                <span className="text-sm text-gray-300">VirtFS Sharing</span>
                <span className="text-xs text-gray-500">(Linux guests)</span>
              </label>
            </div>
          </div>
        </ConfigSection>

        {/* VM Screenshots */}
        <ConfigSection
          title="VM Screenshots"
          icon={<Monitor className="h-5 w-5" />}
          expanded={expandedSections.screenshots}
          onToggle={() => toggleSection('screenshots')}
          badge={config.enable_vm_screenshots ? 'Enabled' : 'Disabled'}
          badgeColor={config.enable_vm_screenshots ? 'green' : 'gray'}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="md:col-span-2 lg:col-span-3">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={config.enable_vm_screenshots || false}
                  onChange={(e) => updateConfig('enable_vm_screenshots', e.target.checked)}
                  className="rounded text-primary-500"
                />
                <span className="text-sm text-gray-300">Enable VM Screenshots</span>
              </label>
              <p className="text-xs text-gray-500 ml-6 mt-1">
                Adds a VNC display to VMs for capturing screenshots. View them in the VM Viewer tab.
              </p>
            </div>
            <div>
              <label className="label">Screenshot Interval (seconds)</label>
              <input
                type="number"
                className="input"
                value={config.screenshot_interval || 5}
                onChange={(e) => updateConfig('screenshot_interval', parseInt(e.target.value))}
                min="1"
                max="60"
                disabled={!config.enable_vm_screenshots}
              />
              <p className="text-xs text-gray-500 mt-1">How often to capture screenshots</p>
            </div>
            <div>
              <label className="label">Screenshot Directory</label>
              <input
                type="text"
                className="input"
                value={config.screenshot_dir || '~/.fawkes/screenshots'}
                onChange={(e) => updateConfig('screenshot_dir', e.target.value)}
                disabled={!config.enable_vm_screenshots}
              />
              <p className="text-xs text-gray-500 mt-1">Where to store screenshots</p>
            </div>
          </div>
          {!config.enable_vm_screenshots && (
            <div className="mt-4 bg-yellow-900/20 border border-yellow-700 rounded-lg p-3">
              <p className="text-sm text-yellow-300">
                <Eye className="h-4 w-4 inline mr-2" />
                Enable screenshots to visually monitor VM activity in the VM Viewer page.
              </p>
            </div>
          )}
        </ConfigSection>

        {/* Fuzzer Settings */}
        <ConfigSection
          title="Fuzzer Settings"
          icon={<Bug className="h-5 w-5" />}
          expanded={expandedSections.fuzzer}
          onToggle={() => toggleSection('fuzzer')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="label">Fuzzer Type</label>
              <select
                className="select"
                value={config.fuzzer || 'file'}
                onChange={(e) => updateConfig('fuzzer', e.target.value)}
              >
                <option value="file">File Fuzzer</option>
                <option value="network">Network Fuzzer</option>
                <option value="api">API Fuzzer</option>
                <option value="grammar">Grammar Fuzzer</option>
                <option value="intelligent">Intelligent Fuzzer</option>
              </select>
              <p className="text-xs text-gray-500 mt-1">Type of fuzzing to perform</p>
            </div>
            <div className="md:col-span-2">
              <label className="label">Fuzzer Config (JSON)</label>
              <textarea
                className="input font-mono text-sm"
                rows="3"
                value={config.fuzzer_config ? JSON.stringify(config.fuzzer_config, null, 2) : ''}
                onChange={(e) => {
                  try {
                    const parsed = e.target.value ? JSON.parse(e.target.value) : null;
                    updateConfig('fuzzer_config', parsed);
                  } catch {
                    // Invalid JSON, keep the text but don't update
                  }
                }}
                placeholder='{"key": "value"}'
              />
              <p className="text-xs text-gray-500 mt-1">Custom fuzzer configuration</p>
            </div>
          </div>
        </ConfigSection>

        {/* Network Settings */}
        <ConfigSection
          title="Network Settings"
          icon={<Server className="h-5 w-5" />}
          expanded={expandedSections.network}
          onToggle={() => toggleSection('network')}
          badge={fuzzingMode !== 'local' ? fuzzingMode : null}
          badgeColor={isController ? 'blue' : 'yellow'}
        >
          {fuzzingMode === 'local' ? (
            <div className="text-center py-6">
              <Info className="h-8 w-8 text-gray-500 mx-auto mb-2" />
              <p className="text-gray-400">Network settings not used in local mode</p>
              <p className="text-xs text-gray-500 mt-1">
                Switch to controller or worker mode to configure network settings
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label className="label">
                    {isController ? 'Bind Address' : 'Controller Address'}
                  </label>
                  <input
                    type="text"
                    className="input"
                    value={config.controller_host || '0.0.0.0'}
                    onChange={(e) => updateConfig('controller_host', e.target.value)}
                    placeholder={isController ? '0.0.0.0' : '192.168.1.100'}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    {isController
                      ? '0.0.0.0 for all interfaces'
                      : 'IP of controller to connect to'}
                  </p>
                </div>
                <div>
                  <label className="label">
                    {isController ? 'Listen Port' : 'Controller Port'}
                  </label>
                  <input
                    type="number"
                    className="input"
                    value={config.controller_port || 5000}
                    onChange={(e) => updateConfig('controller_port', parseInt(e.target.value))}
                    min="1"
                    max="65535"
                  />
                </div>
              </div>

              {isController && (
                <div className="bg-blue-900/20 border border-blue-800 rounded p-3">
                  <p className="text-sm text-blue-300">
                    <strong>Controller Mode:</strong> This machine will coordinate fuzzing across multiple workers.
                  </p>
                </div>
              )}

              {isWorker && (
                <div className="bg-yellow-900/20 border border-yellow-800 rounded p-3">
                  <p className="text-sm text-yellow-300">
                    <strong>Worker Mode:</strong> This machine will connect to the controller for jobs.
                  </p>
                </div>
              )}
            </div>
          )}
        </ConfigSection>

        {/* Advanced Features */}
        <ConfigSection
          title="Advanced Features"
          icon={<Zap className="h-5 w-5" />}
          expanded={expandedSections.advanced}
          onToggle={() => toggleSection('advanced')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FeatureToggle
              label="Time Compression"
              description="Accelerate guest VM time for faster fuzzing (3-10x speedup)"
              checked={config.enable_time_compression || false}
              onChange={(checked) => updateConfig('enable_time_compression', checked)}
            />
            <FeatureToggle
              label="Persistent Mode"
              description="Keep VM state between test cases for faster execution"
              checked={config.enable_persistent || false}
              onChange={(checked) => updateConfig('enable_persistent', checked)}
            />
            <FeatureToggle
              label="Corpus Synchronization"
              description="Sync interesting test cases across distributed workers"
              checked={config.enable_corpus_sync || false}
              onChange={(checked) => updateConfig('enable_corpus_sync', checked)}
            />
            <FeatureToggle
              label="Stack Deduplication"
              description="Deduplicate crashes based on stack trace similarity"
              checked={config.enable_stack_deduplication || false}
              onChange={(checked) => updateConfig('enable_stack_deduplication', checked)}
            />
            <FeatureToggle
              label="Coverage Tracking"
              description="Track code coverage during fuzzing"
              checked={config.enable_coverage || false}
              onChange={(checked) => updateConfig('enable_coverage', checked)}
            />
            <FeatureToggle
              label="Dictionary Mode"
              description="Use dictionary tokens for smarter mutations"
              checked={config.enable_dictionary || false}
              onChange={(checked) => updateConfig('enable_dictionary', checked)}
            />
          </div>
        </ConfigSection>

        {/* Authentication & Security */}
        <ConfigSection
          title="Authentication & Security"
          icon={<Shield className="h-5 w-5" />}
          expanded={expandedSections.security}
          onToggle={() => toggleSection('security')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FeatureToggle
              label="Authentication Enabled"
              description="Require authentication for controller/worker communication"
              checked={config.auth_enabled || false}
              onChange={(checked) => updateConfig('auth_enabled', checked)}
            />
            <FeatureToggle
              label="TLS Enabled"
              description="Encrypt communication between controller and workers"
              checked={config.tls_enabled || false}
              onChange={(checked) => updateConfig('tls_enabled', checked)}
            />
            {config.tls_enabled && (
              <>
                <div>
                  <label className="label">TLS Certificate Path</label>
                  <input
                    type="text"
                    className="input"
                    value={config.tls_cert || ''}
                    onChange={(e) => updateConfig('tls_cert', e.target.value)}
                    placeholder="/path/to/cert.pem"
                  />
                </div>
                <div>
                  <label className="label">TLS Key Path</label>
                  <input
                    type="text"
                    className="input"
                    value={config.tls_key || ''}
                    onChange={(e) => updateConfig('tls_key', e.target.value)}
                    placeholder="/path/to/key.pem"
                  />
                </div>
              </>
            )}
          </div>
        </ConfigSection>

        {/* Paths & Directories */}
        <ConfigSection
          title="Paths & Directories"
          icon={<FolderOpen className="h-5 w-5" />}
          expanded={expandedSections.paths}
          onToggle={() => toggleSection('paths')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="label">Database Path</label>
              <input
                type="text"
                className="input"
                value={config.db_path || '~/.fawkes/fawkes.db'}
                onChange={(e) => updateConfig('db_path', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Controller Database Path</label>
              <input
                type="text"
                className="input"
                value={config.controller_db_path || '~/.fawkes/controller.db'}
                onChange={(e) => updateConfig('controller_db_path', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Crash Directory</label>
              <input
                type="text"
                className="input"
                value={config.crash_dir || './fawkes/crashes'}
                onChange={(e) => updateConfig('crash_dir', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Input Directory</label>
              <input
                type="text"
                className="input"
                value={config.input_dir || '~/fuzz_inputs'}
                onChange={(e) => updateConfig('input_dir', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Share Directory</label>
              <input
                type="text"
                className="input"
                value={config.share_dir || '~/fawkes_shared'}
                onChange={(e) => updateConfig('share_dir', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Job Directory</label>
              <input
                type="text"
                className="input"
                value={config.job_dir || '~/.fawkes/jobs/'}
                onChange={(e) => updateConfig('job_dir', e.target.value)}
              />
            </div>
            <div>
              <label className="label">Registry File</label>
              <input
                type="text"
                className="input"
                value={config.registry_file || '~/.fawkes/registry.json'}
                onChange={(e) => updateConfig('registry_file', e.target.value)}
              />
            </div>
          </div>
        </ConfigSection>
      </div>
    </div>
  );
};

// Collapsible config section component
const ConfigSection = ({ title, icon, expanded, onToggle, children, badge, badgeColor }) => (
  <div className="card">
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between text-left"
    >
      <div className="flex items-center space-x-3">
        <span className="text-primary-400">{icon}</span>
        <h2 className="text-xl font-semibold text-white">{title}</h2>
        {badge && (
          <span className={`badge badge-${badgeColor || 'gray'} text-xs`}>
            {badge}
          </span>
        )}
      </div>
      {expanded ? (
        <ChevronDown className="h-5 w-5 text-gray-400" />
      ) : (
        <ChevronRight className="h-5 w-5 text-gray-400" />
      )}
    </button>
    {expanded && <div className="mt-4 pt-4 border-t border-gray-700">{children}</div>}
  </div>
);

// Reusable feature toggle component
const FeatureToggle = ({ label, description, checked, onChange }) => (
  <div className="p-3 bg-gray-800/50 rounded-lg">
    <label className="flex items-start space-x-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded text-primary-500 mt-0.5"
      />
      <div>
        <span className="text-sm font-medium text-gray-300">{label}</span>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
    </label>
  </div>
);

export default ConfigPage;
