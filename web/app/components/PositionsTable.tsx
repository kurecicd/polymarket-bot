import { Position } from "../lib/api";

export default function PositionsTable({ open, closed }: { open: Position[]; closed: Position[] }) {
  return (
    <div className="border border-green-900 rounded p-2">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        LATEST POSITIONS — {open.length} OPEN
      </h2>
      <div className="overflow-auto max-h-96">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-green-700">
              <th className="text-left pb-1">MARKET</th>
              <th className="text-right pb-1">ENTRY</th>
              <th className="text-right pb-1">TARGET</th>
              <th className="text-right pb-1">SIZE</th>
              <th className="text-right pb-1">P&L</th>
              <th className="text-right pb-1">STATUS</th>
            </tr>
          </thead>
          <tbody>
            {open.map((p) => (
              <PositionRow key={p.position_id} position={p} isOpen />
            ))}
            {closed.slice(0, 10).map((p) => (
              <PositionRow key={p.position_id} position={p} isOpen={false} />
            ))}
            {open.length === 0 && closed.length === 0 && (
              <tr>
                <td colSpan={6} className="text-green-800 py-4 text-center">No positions yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PositionRow({ position: p, isOpen }: { position: Position; isOpen: boolean }) {
  const pnl = p.realized_pnl ?? 0;
  const pnlColor = pnl > 0 ? "text-green-300" : pnl < 0 ? "text-red-400" : "text-green-700";
  const strategy = p.strategy === "quick_bet" ? "[QB]" : "[W]";

  return (
    <tr className="border-t border-green-950">
      <td className="py-0.5 max-w-[200px]">
        <span className="text-green-700 mr-1">{strategy}</span>
        <span className="truncate block text-green-400">{p.market_question?.slice(0, 45)}</span>
      </td>
      <td className="text-right text-green-500">{p.entry_price?.toFixed(3)}</td>
      <td className="text-right text-green-700">{p.profit_target_price?.toFixed(3)}</td>
      <td className="text-right text-green-500">${p.size_usdc?.toFixed(0)}</td>
      <td className={`text-right ${pnlColor}`}>
        {isOpen ? "—" : `$${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`}
      </td>
      <td className="text-right">
        {isOpen ? (
          <span className="text-cyan-400">OPEN</span>
        ) : (
          <span className="text-green-800">{p.close_reason?.slice(0, 8) ?? "closed"}</span>
        )}
      </td>
    </tr>
  );
}
