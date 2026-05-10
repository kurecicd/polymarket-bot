const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { next: { revalidate: 5 } });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json();
}

export async function getStats() {
  return apiFetch<{
    total_trades: number;
    wins: number;
    losses: number;
    win_rate: number;
    total_pnl: number;
    avg_hold_hours: number;
    open_positions: number;
    daily_trades: number;
    whale_count: number;
    execution_mode: string;
  }>("/api/stats");
}

export async function getPositions() {
  return apiFetch<{
    open: Position[];
    closed: Position[];
  }>("/api/positions");
}

export async function getWhales() {
  return apiFetch<{
    updated_at: string;
    count: number;
    whales: Whale[];
  }>("/api/whales");
}

export async function getActivity(limit = 30) {
  return apiFetch<ActivityEvent[]>(`/api/activity?limit=${limit}`);
}

export async function getConsensusLog(limit = 15) {
  return apiFetch<ActivityEvent[]>(`/api/activity/consensus?limit=${limit}`);
}

export async function getBotStatus() {
  return apiFetch<{
    execution_mode: string;
    whales_loaded: boolean;
    whale_count: number;
    last_poll: string | null;
    open_positions: number;
    data_ready: boolean;
  }>("/api/actions/status");
}

export async function triggerAction(action: string, execute = false) {
  const res = await fetch(`${API_BASE}/api/actions/${action}?execute=${execute}`, {
    method: "POST",
  });
  return res.json();
}

export interface Position {
  position_id: string;
  market_question: string;
  token_id: string;
  whale_address: string;
  entry_price: number;
  size_usdc: number;
  size_shares: number;
  profit_target_price: number;
  end_date_iso: string;
  opened_at: string;
  status: string;
  close_reason?: string;
  exit_price?: number;
  realized_pnl?: number;
  strategy?: string;
}

export interface Whale {
  address: string;
  win_rate: number;
  total_profit_usdc: number;
  avg_position_size_usdc: number;
  total_trades: number;
  roi_pct: number;
}

export interface ActivityEvent {
  time: string;
  script: string;
  event: string;
  details: Record<string, unknown>;
}
