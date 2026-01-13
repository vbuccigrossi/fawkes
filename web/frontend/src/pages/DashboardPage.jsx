import React, { useState, useEffect } from 'react';
import { Server, Cpu, HardDrive, Zap, AlertTriangle, TrendingUp } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/common/MetricCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { systemAPI, jobsAPI, crashesAPI } from '../services/api';
import wsClient from '../services/websocket';

const DashboardPage = () => {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [recentCrashes, setRecentCrashes] = useState([]);
  const [performanceData, setPerformanceData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch initial data
  useEffect(() => {
    fetchData();
  }, []);

  // Subscribe to WebSocket updates
  useEffect(() => {
    const unsubscribeStats = wsClient.on('stats_update', (data) => {
      setStats(data);

      // Add to performance chart
      setPerformanceData((prev) => {
        const newData = [
          ...prev,
          {
            time: new Date().toLocaleTimeString(),
            execPerSec: data.exec_per_sec || 0,
            timestamp: data.timestamp,
          },
        ];
        // Keep last 20 data points
        return newData.slice(-20);
      });
    });

    const unsubscribeJobs = wsClient.on('jobs_update', (data) => {
      setJobs(Object.values(data));
    });

    const unsubscribeCrashes = wsClient.on('new_crash', (crash) => {
      setRecentCrashes((prev) => [crash, ...prev].slice(0, 5));
    });

    return () => {
      unsubscribeStats();
      unsubscribeJobs();
      unsubscribeCrashes();
    };
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsRes, jobsRes, crashesRes] = await Promise.all([
        systemAPI.getStats(),
        jobsAPI.list(),
        crashesAPI.list({ limit: 5 }),
      ]);

      setStats(statsRes.data.data);
      setJobs(jobsRes.data.data);
      setRecentCrashes(crashesRes.data.data.slice(0, 5));
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch dashboard data');
      console.error('Error fetching dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingSpinner size="lg" message="Loading dashboard..." />;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={fetchData} />;
  }

  const runningJobs = jobs.filter((j) => j.status === 'running');
  const timeCompressionEnabled = stats?.time_compression_enabled || false;

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 mt-1">Real-time fuzzing campaign overview</p>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="VMs Online"
          value={`${stats?.running_vms || 0} / ${stats?.max_vms || 0}`}
          icon={Server}
          color="primary"
          subtitle={`${runningJobs.length} jobs running`}
        />
        <MetricCard
          title="CPU Usage"
          value={`${stats?.cpu_percent?.toFixed(1) || 0}%`}
          icon={Cpu}
          color={stats?.cpu_percent > 80 ? 'warning' : 'success'}
        />
        <MetricCard
          title="RAM Usage"
          value={`${stats?.memory_percent?.toFixed(1) || 0}%`}
          icon={HardDrive}
          color={stats?.memory_percent > 80 ? 'warning' : 'success'}
        />
        <MetricCard
          title="Time Compress"
          value={timeCompressionEnabled ? 'ON' : 'OFF'}
          icon={Zap}
          color={timeCompressionEnabled ? 'success' : 'info'}
          subtitle={timeCompressionEnabled ? '3-10x speedup' : 'Enable for boost'}
        />
      </div>

      {/* Performance Chart */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white flex items-center">
            <TrendingUp className="h-5 w-5 mr-2 text-primary-500" />
            Performance
          </h2>
          <div className="text-sm text-gray-400">Last 2 minutes</div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={performanceData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
            <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
              labelStyle={{ color: '#F3F4F6' }}
            />
            <Line
              type="monotone"
              dataKey="execPerSec"
              stroke="#3B82F6"
              strokeWidth={2}
              dot={false}
              name="Exec/sec"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Active Jobs & Recent Crashes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Jobs */}
        <div className="card">
          <h2 className="text-xl font-semibold text-white mb-4">Active Jobs</h2>
          {runningJobs.length === 0 ? (
            <p className="text-gray-400 text-center py-8">No active jobs</p>
          ) : (
            <div className="space-y-3">
              {runningJobs.slice(0, 5).map((job) => (
                <div
                  key={job.job_id}
                  className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors cursor-pointer"
                >
                  <div className="flex-1">
                    <h3 className="font-medium text-white">{job.name || `Job #${job.job_id}`}</h3>
                    <p className="text-sm text-gray-400">
                      {job.total_testcases?.toLocaleString() || 0} testcases
                    </p>
                  </div>
                  <div className="flex items-center space-x-3">
                    <div className="text-right">
                      <p className="text-sm font-medium text-primary-400">
                        {job.exec_per_sec?.toFixed(1) || 0} exec/s
                      </p>
                      <p className="text-xs text-gray-500">
                        {job.crash_count || 0} crashes
                      </p>
                    </div>
                    <div className="badge badge-success">Running</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Crashes */}
        <div className="card">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center">
            <AlertTriangle className="h-5 w-5 mr-2 text-red-500" />
            Recent Crashes
          </h2>
          {recentCrashes.length === 0 ? (
            <p className="text-gray-400 text-center py-8">No crashes yet</p>
          ) : (
            <div className="space-y-3">
              {recentCrashes.map((crash) => (
                <div
                  key={crash.crash_id}
                  className="flex items-start justify-between p-3 bg-gray-700/50 rounded-lg hover:bg-gray-700 transition-colors cursor-pointer"
                >
                  <div className="flex-1">
                    <h3 className="font-medium text-white">
                      {crash.crash_type || 'Unknown'}
                    </h3>
                    <p className="text-sm text-gray-400">
                      Job #{crash.job_id} •{' '}
                      {new Date(crash.timestamp * 1000).toLocaleTimeString()}
                    </p>
                  </div>
                  <div className="flex items-center space-x-2">
                    {crash.sanitizer_type && (
                      <span className="badge badge-warning text-xs">
                        {crash.sanitizer_type}
                      </span>
                    )}
                    {crash.severity && (
                      <span
                        className={`badge text-xs ${
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
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Statistics Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="card bg-gradient-to-br from-blue-900/20 to-blue-800/10 border border-blue-800/30">
          <div className="text-center">
            <p className="text-sm text-blue-300 uppercase tracking-wide">Total Jobs</p>
            <p className="mt-2 text-4xl font-bold text-white">{stats?.total_jobs || 0}</p>
            <p className="mt-1 text-sm text-gray-400">
              {runningJobs.length} active
            </p>
          </div>
        </div>
        <div className="card bg-gradient-to-br from-red-900/20 to-red-800/10 border border-red-800/30">
          <div className="text-center">
            <p className="text-sm text-red-300 uppercase tracking-wide">Total Crashes</p>
            <p className="mt-2 text-4xl font-bold text-white">{stats?.total_crashes || 0}</p>
            <p className="mt-1 text-sm text-gray-400">
              {stats?.unique_crashes || 0} unique
            </p>
          </div>
        </div>
        <div className="card bg-gradient-to-br from-green-900/20 to-green-800/10 border border-green-800/30">
          <div className="text-center">
            <p className="text-sm text-green-300 uppercase tracking-wide">Total Testcases</p>
            <p className="mt-2 text-4xl font-bold text-white">
              {stats?.total_testcases?.toLocaleString() || 0}
            </p>
            <p className="mt-1 text-sm text-gray-400">executed</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;
