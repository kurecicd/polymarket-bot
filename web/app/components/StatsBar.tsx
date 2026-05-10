interface Stats {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_hold_hours: number;
  open_positions: number;
  daily_trades: number;
  whale_count: number;
}

export default function StatsBar({ stats }: { stats: Stats }) {
  const winColor = stats.win_rate >= 0.6 ? "text-green-300" : stats.win_rate >= 0.5 ? "text-green-400" : "text-yellow-400";
  const pnlColor = stats.total_pnl >= 0 ? "text-green-300" : "text-red-400";

  return (
    <div className="grid grid-cols-8 gap-2 border border-green-900 rounded p-3 bg-green-950/20">
      <Stat label="TOTAL TRADES" value={stats.total_trades.toString()} />
      <Stat label="WIN RATE" value={`${(stats.win_rate * 100).toFixed(1)}%`} color={winColor} />
      <Stat label="W / L" value={`${stats.wins} / ${stats.losses}`} />
      <Stat label="TOTAL P&L" value={`$${stats.total_pnl >= 0 ? "+" : ""}${stats.total_pnl.toFixed(2)}`} color={pnlColor} />
      <Stat label="AVG HOLD" value={`${stats.avg_hold_hours}h`} />
      <Stat label="OPEN" value={stats.open_positions.toString()} color="text-cyan-400" />
      <Stat label="TODAY" value={`${stats.daily_trades}/10`} color="text-yellow-400" />
      <Stat label="WHALES" value={stats.whale_count.toString()} />
    </div>
  );
}

function Stat({ label, value, color = "text-green-300" }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <div className="text-xs text-green-700">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  );
}
