import { ActivityEvent } from "../lib/api";

const EVENT_LABELS: Record<string, { label: string; color: string }> = {
  copy_trade_opened: { label: "TRADE OPEN", color: "text-green-300" },
  position_closed:  { label: "TRADE CLOSE", color: "text-green-400" },
  vote_complete:    { label: "CONSENSUS",   color: "text-blue-400" },
  order_failed:     { label: "ORDER FAIL",  color: "text-red-400" },
  sell_order_failed:{ label: "SELL FAIL",   color: "text-red-400" },
  daily_limit_reached:{ label: "LIMIT HIT", color: "text-yellow-400" },
  quick_bet_placed: { label: "QUICK BET",   color: "text-cyan-400" },
  button_press:     { label: "BTN",         color: "text-purple-400" },
  start:            { label: "RUN",         color: "text-green-800" },
  complete:         { label: "DONE",        color: "text-green-700" },
};

function toCest(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("sv-SE", {
      timeZone: "Europe/Stockholm",
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso.slice(11, 19);
  }
}

export default function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="border border-green-900 rounded p-2">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        ACTIVITY LOG <span className="text-green-800 font-normal">— all times CET/CEST</span>
      </h2>
      <div className="grid grid-cols-1 gap-0.5 text-xs max-h-48 overflow-auto">
        {events.length === 0 && (
          <p className="text-green-800 py-2 text-center">Waiting for activity…</p>
        )}
        {[...events].reverse().map((e, i) => {
          const meta = EVENT_LABELS[e.event] ?? { label: e.event.toUpperCase(), color: "text-green-700" };
          const time = toCest(e.time ?? "");
          const d = e.details as Record<string, unknown>;
          const script = e.script === "dashboard" ? (e.run_id ?? "") : e.script;

          let detail = "";
          if (e.event === "button_press") {
            const status = d.status as string | undefined;
            if (status === "started") {
              detail = `${script} → started (execute=${d.execute})`;
            } else {
              const ok = d.success ? "✓" : "✗";
              detail = `${script} ${ok} ${(d.summary as string ?? "").slice(0, 70)}`;
            }
          } else {
            detail =
              (d.market as string)?.slice(0, 70) ??
              (d.summary as string)?.slice(0, 70) ??
              (d.reason as string) ??
              (d.error as string) ??
              JSON.stringify(d).slice(0, 70);
          }

          return (
            <div key={i} className="flex items-start gap-2 border-b border-green-950 py-0.5">
              <span className="text-green-800 shrink-0 tabular-nums">{time}</span>
              <span className={`shrink-0 font-bold w-20 ${meta.color}`}>{meta.label}</span>
              <span className="text-green-700 break-all">{detail}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
