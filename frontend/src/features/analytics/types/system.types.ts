export interface DashboardSystemStatusResponse {
  task_queue: {
    active: number;
    pending: number;
  };
  celery_workers: {
    online: number;
  };
  errors: {
    count_24h: number;
    delta_from_yesterday: number;
  };
  avg_response: {
    avg_ms: number;
    p95_ms: number;
  };
  poll_worker: {
    enabled: boolean;
    running: boolean;
    interval_seconds: number;
    last_run_at: string;
    last_result: Record<string, unknown>;
  };
  checked_at: string;
}
