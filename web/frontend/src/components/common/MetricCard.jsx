import React from 'react';

const MetricCard = ({ title, value, icon: Icon, color = 'primary', subtitle }) => {
  const colorClasses = {
    primary: 'text-primary-500 bg-primary-900/20',
    success: 'text-green-500 bg-green-900/20',
    warning: 'text-yellow-500 bg-yellow-900/20',
    danger: 'text-red-500 bg-red-900/20',
    info: 'text-blue-500 bg-blue-900/20',
  };

  const colorClass = colorClasses[color] || colorClasses.primary;

  return (
    <div className="card animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-400 uppercase tracking-wide">
            {title}
          </p>
          <p className="mt-2 text-3xl font-bold text-white">{value}</p>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
          )}
        </div>
        {Icon && (
          <div className={`p-3 rounded-lg ${colorClass}`}>
            <Icon className="h-8 w-8" />
          </div>
        )}
      </div>
    </div>
  );
};

export default MetricCard;
