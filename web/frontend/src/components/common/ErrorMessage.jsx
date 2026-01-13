import React from 'react';
import { AlertCircle } from 'lucide-react';

const ErrorMessage = ({ message, onRetry }) => {
  return (
    <div className="card bg-red-900/20 border border-red-800">
      <div className="flex items-start space-x-3">
        <AlertCircle className="h-6 w-6 text-red-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1">
          <h3 className="text-sm font-medium text-red-400">Error</h3>
          <p className="mt-1 text-sm text-gray-300">{message}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 btn btn-danger text-sm"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ErrorMessage;
