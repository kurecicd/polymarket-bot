import { ActivityEvent } from "../lib/api";

const EVENT_LABELS: Record<string, { label: string; color: string }> = {
  copy_trade_opened: { label: "TRADE OPEN", color: "text-green-300" },
  position_closed: { label: "TRADE CLOSE", color: "text-green-400" },
  vote_complete: { label: "CONSENSUS", color: "text-blue-400" },
  order_failed: { label: "ORDER FAIL", color: "text-red-400" },
  sell_order_failed: { label: "SELL FAIL", color: "text-red-400" },
  daily_limit_reached: { label: "LIMIT HIT", color: "text-yellow-400" },
  quick_bet_placed: { label: "QUICK BET", color: "text-cyan-400" },
};

export default function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="border border-green-900 rounded p-2">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        ACTIVITY LOG
      </h2>
      <div className="grid grid-cols-1 gap-0.5 text-xs max-h-32 overflow-auto">
        {events.length === 0 && (
          <p className="text-green-800 py-2 text-center">Waiting for activity…</p>
        )}
        {events.map((e, i) => {
          const meta = EVENT_LABELS[e.event] ?? { label: e.event, color: "text-green-700" };
          const time = e.time?.slice(11, 19) ?? "?";
          const d = e.details as Record<string, unknown>;
          const detail =
            (d.market as string)?.slice(0, 60) ??
            (d.reason as string) ??
            (d.error as string) ??
            "";
          return (
            <div key={i} className="flex items-center gap-3 border-b border-green-950 py-0.5">
              <span className="text-green-800 shrink-0">{time}</span>
              <span className={`shrink-0 font-bold ${meta.color}`}>{meta.label}</span>
              <span className="text-green-700 truncate">{detail}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
