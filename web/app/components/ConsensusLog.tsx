import { ActivityEvent } from "../lib/api";

export default function ConsensusLog({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="border border-green-900 rounded p-2 h-full">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        3-AGENT CONSENSUS BOTS
      </h2>
      <div className="space-y-1 overflow-auto max-h-96">
        {events.length === 0 && (
          <p className="text-green-800 text-xs py-4 text-center">Waiting for consensus runs…</p>
        )}
        {events.map((e, i) => {
          const d = e.details as { approved?: boolean; buy_count?: number; market?: string };
          const approved = d.approved ?? false;
          const votes = d.buy_count ?? 0;
          const market = (d.market ?? "?").slice(0, 40);
          const time = e.time?.slice(11, 16) ?? "?";
          return (
            <div key={i} className="text-xs border-b border-green-950 pb-1">
              <div className="flex items-center gap-2">
                <span className="text-green-800">{time}</span>
                <span className={approved ? "text-green-400 font-bold" : "text-red-500"}>
                  {approved ? `✓ APPROVED` : `✗ REJECTED`} {votes}/3
                </span>
              </div>
              <div className="text-green-700 truncate">{market}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
