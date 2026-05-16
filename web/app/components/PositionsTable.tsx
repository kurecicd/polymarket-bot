"use client";

import { useState } from "react";
import { Position } from "../lib/api";

async function closePosition(positionId: string) {
  await fetch(`/api/proxy/positions/${positionId}/close`, { method: "POST" });
}

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
              <th className="text-right pb-1">SIDE</th>
              <th className="text-right pb-1">ENTRY</th>
              <th className="text-right pb-1">TARGET</th>
              <th className="text-right pb-1">SHARES</th>
              <th className="text-right pb-1">COST</th>
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
                <td colSpan={8} className="text-green-800 py-4 text-center">No positions yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PositionRow({ position: p, isOpen }: { position: Position; isOpen: boolean }) {
  const [closing, setClosing] = useState(false);
  const [closed, setClosed] = useState(false);

  const pnl = p.realized_pnl ?? 0;
  const pnlColor = pnl > 0 ? "text-green-300" : pnl < 0 ? "text-red-400" : "text-green-700";
  const strategy = p.strategy === "quick_bet" ? "[QB]" : "[W]";
  const outcome = p.outcome ?? (p.token_id ? "NO" : "YES"); // QB bets NO by default
  const outcomeBadge = outcome === "NO"
    ? <span className="text-red-400 font-bold">NO</span>
    : <span className="text-green-400 font-bold">YES</span>;

  const profitPct = p.entry_price && p.profit_target_price
    ? (((p.profit_target_price - p.entry_price) / p.entry_price) * 100).toFixed(0)
    : "?";

  async function handleClose() {
    if (!confirm(`Close position: ${p.market_question}?\n\nThis places a sell order immediately.`)) return;
    setClosing(true);
    await closePosition(p.position_id);
    setClosed(true);
    setClosing(false);
  }

  return (
    <tr className={`border-t border-green-950 ${closed ? "opacity-40" : ""}`}>
      <td className="py-1 max-w-[200px]">
        <div className="text-green-700 text-xs">{strategy} {p.strategy !== "quick_bet" && p.whale_address ? `${p.whale_address.slice(0, 8)}…` : ""}</div>
        <div className="text-green-400 text-xs">{p.market_question?.slice(0, 50)}{(p.market_question?.length ?? 0) > 50 ? "…" : ""}</div>
        {p.end_date_iso && (
          <div className="text-green-800 text-xs">closes {new Date(p.end_date_iso).toLocaleDateString("sv-SE", { timeZone: "Europe/Stockholm" })}</div>
        )}
      </td>
      <td className="text-right align-top py-1">{outcomeBadge}</td>
      <td className="text-right text-green-500 align-top py-1">{p.entry_price?.toFixed(3)}</td>
      <td className="text-right text-green-700 align-top py-1">
        {p.profit_target_price?.toFixed(3)}
        <div className="text-green-800">+{profitPct}%</div>
      </td>
      <td className="text-right text-green-500 align-top py-1">{p.size_shares?.toFixed(1)}</td>
      <td className="text-right text-green-500 align-top py-1">${p.size_usdc?.toFixed(2)}</td>
      <td className={`text-right align-top py-1 ${pnlColor}`}>
        {isOpen ? "—" : `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`}
      </td>
      <td className="text-right align-top py-1">
        {isOpen ? (
          <div className="flex flex-col items-end gap-0.5">
            <span className="text-cyan-400">OPEN</span>
            <button
              onClick={handleClose}
              disabled={closing || closed}
              className="text-red-500 border border-red-900 px-1 rounded hover:bg-red-900/30 disabled:opacity-40 text-xs"
            >
              {closing ? "…" : "CLOSE"}
            </button>
          </div>
        ) : (
          <span className="text-green-800">{p.close_reason?.slice(0, 12) ?? "closed"}</span>
        )}
      </td>
    </tr>
  );
}
