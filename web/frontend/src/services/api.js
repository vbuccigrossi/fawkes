/**
 * API Client for Fawkes Web UI
 *
 * Provides methods for interacting with the FastAPI backend.
 */

import axios from 'axios';

// Create axios instance with default config
const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('fawkes_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      localStorage.removeItem('fawkes_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// System endpoints
export const systemAPI = {
  getStats: () => api.get('/system/stats'),
  getHealth: () => api.get('/system/health'),
  getConfig: () => api.get('/system/config'),
};

// Jobs endpoints
export const jobsAPI = {
  list: () => api.get('/jobs/'),
  get: (id) => api.get(`/jobs/${id}`),
  create: (data, sessionId = null) => {
    const params = sessionId ? { session_id: sessionId } : undefined;
    return api.post('/jobs/', data, { params });
  },
  update: (id, data) => api.put(`/jobs/${id}`, data),
  delete: (id) => api.delete(`/jobs/${id}`),
  start: (id) => api.post(`/jobs/${id}/start`),
  pause: (id) => api.post(`/jobs/${id}/pause`),
  stop: (id) => api.post(`/jobs/${id}/stop`),
};

// Job Input Files (Seed Corpus) endpoints
export const jobInputsAPI = {
  // Session management
  createSession: () => api.post('/jobs/inputs/session'),
  deleteSession: (sessionId) => api.delete(`/jobs/inputs/session/${sessionId}`),

  // List files (supports session_id or job_id)
  list: (sessionId = null, jobId = null) => {
    const params = {};
    if (sessionId) params.session_id = sessionId;
    if (jobId) params.job_id = jobId;
    return api.get('/jobs/inputs/', { params });
  },

  // Upload single file
  upload: (file, onProgress, sessionId = null, jobId = null) => {
    const formData = new FormData();
    formData.append('file', file);
    const params = {};
    if (sessionId) params.session_id = sessionId;
    if (jobId) params.job_id = jobId;
    return api.post('/jobs/inputs/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params,
      onUploadProgress: onProgress,
    });
  },

  // Upload multiple files
  uploadMultiple: (files, onProgress, sessionId = null, jobId = null) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    const params = {};
    if (sessionId) params.session_id = sessionId;
    if (jobId) params.job_id = jobId;
    return api.post('/jobs/inputs/upload-multiple', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params,
      onUploadProgress: onProgress,
    });
  },

  // Download file
  download: (filename, sessionId = null, jobId = null) => {
    const params = { responseType: 'blob' };
    if (sessionId) params.params = { ...params.params, session_id: sessionId };
    if (jobId) params.params = { ...params.params, job_id: jobId };
    return api.get(`/jobs/inputs/${filename}`, params);
  },

  // Delete single file
  delete: (filename, sessionId = null, jobId = null) => {
    const params = {};
    if (sessionId) params.session_id = sessionId;
    if (jobId) params.job_id = jobId;
    return api.delete(`/jobs/inputs/${filename}`, { params });
  },

  // Clear all files
  clearAll: (sessionId = null, jobId = null) => {
    const params = {};
    if (sessionId) params.session_id = sessionId;
    if (jobId) params.job_id = jobId;
    return api.delete('/jobs/inputs/clear', { params });
  },
};

// Crashes endpoints
export const crashesAPI = {
  list: (params) => api.get('/crashes/', { params }),
  get: (id) => api.get(`/crashes/${id}`),
  downloadTestcase: (id) => api.get(`/crashes/${id}/testcase`, { responseType: 'blob' }),
  reproduce: (id) => api.post(`/crashes/${id}/reproduce`),
  updateTriage: (id, data) => api.put(`/crashes/${id}/triage`, data),
  getSummary: () => api.get('/crashes/stats/summary'),
};

// Workers endpoints
export const workersAPI = {
  list: () => api.get('/workers/'),
  get: (id) => api.get(`/workers/${id}`),
  add: (data) => api.post('/workers/', data),
  assign: (workerId, jobId) => api.post(`/workers/${workerId}/assign`, { job_id: jobId }),
  remove: (id) => api.delete(`/workers/${id}`),
};

// VMs endpoints (screenshots)
export const vmsAPI = {
  list: () => api.get('/vms/'),
  get: (id) => api.get(`/vms/${id}`),
  getScreenshot: (id) => api.get(`/vms/${id}/screenshot`, { responseType: 'blob' }),
  getAllScreenshots: () => api.get('/vms/screenshots/all'),
  getScreenshotStatus: () => api.get('/vms/screenshots/status'),
};

// Config endpoints
export const configAPI = {
  get: () => api.get('/config/'),
  update: (data) => api.put('/config/', data),
  export: () => api.get('/config/export', { responseType: 'blob' }),
  import: (data) => api.post('/config/import', data),
  reset: () => api.post('/config/reset'),
};

// Auth endpoints
export const authAPI = {
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
  getMe: () => api.get('/auth/me'),
};

// VM Setup - ISOs endpoints
export const isosAPI = {
  list: () => api.get('/isos/'),
  get: (filename) => api.get(`/isos/${filename}`),
  upload: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/isos/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
  },
  delete: (filename) => api.delete(`/isos/${filename}`),
  getStorageInfo: () => api.get('/isos/storage/info'),
};

// VM Setup - Disk Images endpoints
export const imagesAPI = {
  list: () => api.get('/images/'),
  getInfo: (path) => api.get('/images/info', { params: { path } }),
  create: (data) => api.post('/images/create', data),
  upload: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/images/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
  },
  delete: (path) => api.delete('/images/', { params: { path } }),
  getStorageInfo: () => api.get('/images/storage/info'),
};

// VM Setup - Snapshots endpoints
export const snapshotsAPI = {
  list: (diskPath) => api.get('/snapshots/', { params: { disk_path: diskPath } }),
  get: (diskPath, name) => api.get(`/snapshots/${name}`, { params: { disk_path: diskPath } }),
  create: (diskPath, data) => api.post('/snapshots/', data, { params: { disk_path: diskPath } }),
  delete: (diskPath, name) => api.delete(`/snapshots/${name}`, { params: { disk_path: diskPath } }),
  validate: (diskPath, name) => api.post(`/snapshots/${name}/validate`, null, { params: { disk_path: diskPath } }),
  apply: (diskPath, name) => api.post('/snapshots/apply', null, { params: { disk_path: diskPath, snapshot_name: name } }),
};

// VM Setup - Architectures endpoints
export const architecturesAPI = {
  list: () => api.get('/architectures/'),
  listFamilies: () => api.get('/architectures/families'),
  get: (arch) => api.get(`/architectures/${arch}`),
  check: (arch) => api.get(`/architectures/${arch}/check`),
  checkKvm: () => api.get('/architectures/kvm/check'),
};

// VM Setup - Installation VMs endpoints
export const vmInstallAPI = {
  list: () => api.get('/vm-install/'),
  start: (data) => api.post('/vm-install/start', data),
  get: (vmId) => api.get(`/vm-install/${vmId}`),
  stop: (vmId) => api.post(`/vm-install/${vmId}/stop`),
  createSnapshot: (vmId, name) => api.post(`/vm-install/${vmId}/snapshot`, { name }),
  ejectIso: (vmId) => api.post(`/vm-install/${vmId}/eject-iso`),
  reset: (vmId) => api.post(`/vm-install/${vmId}/reset`),
  sendKey: (vmId, keys) => api.post(`/vm-install/${vmId}/sendkey`, null, { params: { keys } }),
  listPresets: () => api.get('/vm-install/presets/'),
  getPreset: (presetId) => api.get(`/vm-install/presets/${presetId}`),
};

// Paths endpoints
export const pathsAPI = {
  getAll: () => api.get('/paths/'),
  getDirectories: () => api.get('/paths/directories'),
  getSearchPaths: () => api.get('/paths/search'),
  ensureDirectories: () => api.post('/paths/ensure'),
  setPath: (key, value) => api.put(`/paths/${key}`, null, { params: { path_value: value } }),
  resetPath: (key) => api.delete(`/paths/${key}`),
  resetAll: () => api.post('/paths/reset'),
};

// VM Configs endpoints
export const vmConfigsAPI = {
  list: (tag) => api.get('/vm-configs/', { params: tag ? { tag } : undefined }),
  listTags: () => api.get('/vm-configs/tags'),
  get: (configId) => api.get(`/vm-configs/${configId}`),
  create: (data) => api.post('/vm-configs/', data),
  update: (configId, data) => api.put(`/vm-configs/${configId}`, data),
  delete: (configId) => api.delete(`/vm-configs/${configId}`),
  duplicate: (configId, newName) => api.post(`/vm-configs/${configId}/duplicate`, null, { params: newName ? { new_name: newName } : undefined }),
  export: (configId) => api.post(`/vm-configs/${configId}/export`),
  import: (configData) => api.post('/vm-configs/import', configData),
};

// VM Runner endpoints (for agent installation and snapshot creation)
export const vmRunnerAPI = {
  // Running VMs
  list: () => api.get('/vm-runner/'),
  start: (data) => api.post('/vm-runner/start', data),
  get: (vmId) => api.get(`/vm-runner/${vmId}`),
  stop: (vmId) => api.post(`/vm-runner/${vmId}/stop`),
  stopAll: () => api.post('/vm-runner/stop-all'),
  clearStopped: () => api.post('/vm-runner/clear-stopped'),
  createSnapshot: (vmId, data) => api.post(`/vm-runner/${vmId}/snapshot`, data),

  // Shared folder
  listShared: (vmId, subpath = '') => api.get(`/vm-runner/${vmId}/shared`, { params: { subpath } }),
  uploadFile: (vmId, file, subpath, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('subpath', subpath || 'uploads');
    return api.post(`/vm-runner/${vmId}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
  },
  deleteFile: (vmId, filepath) => api.delete(`/vm-runner/${vmId}/shared/${filepath}`),

  // Agents
  listAgents: () => api.get('/vm-runner/agents/list'),
  copyAgents: (configId, targetOs = 'both') => api.post(`/vm-runner/agents/copy/${configId}`, null, { params: { target_os: targetOs } }),
};

// Helper functions
export const setAuthToken = (token) => {
  localStorage.setItem('fawkes_token', token);
};

export const clearAuthToken = () => {
  localStorage.removeItem('fawkes_token');
};

export const getAuthToken = () => {
  return localStorage.getItem('fawkes_token');
};

export default api;
