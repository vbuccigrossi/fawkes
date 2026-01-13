import React, { useState, useEffect } from 'react';
import { Download, RefreshCw, Filter } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { crashesAPI } from '../services/api';

const CrashesPage = () => {
  const [crashes, setCrashes] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    severity: [],
    sanitizer: [],
    unique_only: false,
  });

  useEffect(() => {
    fetchCrashes();
    fetchSummary();
  }, [filters]);

  const fetchCrashes = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await crashesAPI.list(filters);
      setCrashes(response.data.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch crashes');
    } finally {
      setLoading(false);
    }
  };

  const fetchSummary = async () => {
    try {
      const response = await crashesAPI.getSummary();
      setSummary(response.data.data);
    } catch (err) {
      console.error('Failed to fetch crash summary:', err);
    }
  };

  const handleDownload = async (crashId) => {
    try {
      const response = await crashesAPI.downloadTestcase(crashId);
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `testcase_${crashId}.bin`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error('Failed to download testcase:', err);
    }
  };

  if (loading) return <LoadingSpinner size="lg" message="Loading crashes..." />;
  if (error) return <ErrorMessage message={error} onRetry={fetchCrashes} />;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Crashes</h1>
        <p className="text-gray-400 mt-1">Analyze and triage crash reports</p>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="card text-center">
            <p className="text-sm text-gray-400 uppercase">Total Crashes</p>
            <p className="mt-2 text-3xl font-bold text-white">{summary.total}</p>
          </div>
          <div className="card text-center">
            <p className="text-sm text-gray-400 uppercase">Unique</p>
            <p className="mt-2 text-3xl font-bold text-green-400">{summary.unique}</p>
          </div>
          <div className="card text-center">
            <p className="text-sm text-gray-400 uppercase">High Severity</p>
            <p className="mt-2 text-3xl font-bold text-red-400">
              {summary.by_severity?.HIGH || 0}
            </p>
          </div>
          <div className="card text-center">
            <p className="text-sm text-gray-400 uppercase">With Sanitizer</p>
            <p className="mt-2 text-3xl font-bold text-yellow-400">
              {Object.values(summary.by_sanitizer || {}).reduce((a, b) => a + b, 0) -
                (summary.by_sanitizer?.None || 0)}
            </p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="card">
        <div className="flex items-center space-x-4">
          <Filter className="h-5 w-5 text-gray-400" />
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={filters.unique_only}
              onChange={(e) =>
                setFilters({ ...filters, unique_only: e.target.checked })
              }
              className="rounded text-primary-500"
            />
            <span className="text-sm text-gray-300">Unique Only</span>
          </label>
        </div>
      </div>

      {/* Crashes Table */}
      <div className="card">
        {crashes.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-400">No crashes found</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Sanitizer</th>
                <th>Job</th>
                <th>Time</th>
                <th>Unique</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {crashes.map((crash) => (
                <tr key={crash.crash_id}>
                  <td>#{crash.crash_id}</td>
                  <td className="font-medium">{crash.crash_type || 'Unknown'}</td>
                  <td>
                    {crash.severity && (
                      <span
                        className={`badge ${
                          crash.severity === 'HIGH' || crash.severity === 'CRITICAL'
                            ? 'badge-danger'
                            : crash.severity === 'MEDIUM'
                            ? 'badge-warning'
                            : 'badge-info'
                        }`}
                      >
                        {crash.severity}
                      </span>
                    )}
                  </td>
                  <td>
                    {crash.sanitizer_type && (
                      <span className="badge badge-warning">
                        {crash.sanitizer_type}
                      </span>
                    )}
                  </td>
                  <td>#{crash.job_id}</td>
                  <td className="text-sm text-gray-400">
                    {new Date(crash.timestamp * 1000).toLocaleString()}
                  </td>
                  <td>
                    {crash.is_unique ? (
                      <span className="badge badge-success">Yes</span>
                    ) : (
                      <span className="badge badge-gray">
                        Dup ({crash.duplicate_count})
                      </span>
                    )}
                  </td>
                  <td>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleDownload(crash.crash_id)}
                        className="p-2 text-primary-400 hover:bg-primary-900/20 rounded transition-colors"
                        title="Download Testcase"
                      >
                        <Download className="h-4 w-4" />
                      </button>
                      <button
                        className="p-2 text-green-400 hover:bg-green-900/20 rounded transition-colors"
                        title="Reproduce"
                      >
                        <RefreshCw className="h-4 w-4" />
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

export default CrashesPage;
