"use client";
import { useState } from "react";
import { WhaleLiveMarket, WhalePortfolio } from "../lib/api";

const AGENT_SHORT: Record<string, string> = {
  "Market Analyst": "MKT",
  "Whale Analyst":  "WHL",
  "Risk Analyst":   "RSK",
};

function WhalBar({ count, max }: { count: number; max: number }) {
  const pct = Math.min(100, (count / max) * 100);
  return (
    <div className="w-10 bg-green-950 rounded-sm h-1.5 inline-block align-middle ml-1">
      <div className="bg-green-500 h-1.5 rounded-sm" style={{ width: `${pct}%` }} />
    </div>
  );
}

function DaysStr({ d }: { d: number | null }) {
  if (d === null) return <span className="text-green-900">—</span>;
  if (d <= 1) return <span className="text-yellow-600">today</span>;
  if (d <= 7) return <span className="text-yellow-700">{d.toFixed(0)}d</span>;
  return <span className="text-green-800">{d.toFixed(0)}d</span>;
}

function ConsensusBadge({ c, isOpen, onClick }: {
  c: NonNullable<WhaleLiveMarket["consensus"]>;
  isOpen: boolean;
  onClick: () => void;
}) {
  const color = c.approved ? "text-green-400 border-green-700" : "text-red-400 border-red-900";
  return (
    <button
      onClick={onClick}
      className={`border rounded px-1 text-xs font-mono leading-none ${color} hover:opacity-80 ${isOpen ? "opacity-60" : ""}`}
    >
      {c.approved ? "✓" : "✗"} {c.buy_count}/3
    </button>
  );
}

function ConsensusDetail({ c, onClose }: {
  c: NonNullable<WhaleLiveMarket["consensus"]>;
  onClose: () => void;
}) {
  return (
    <tr>
      <td colSpan={8} className="pb-2 px-1">
        <div className="bg-green-950/60 border border-green-900 rounded p-2 text-xs">
          <div className="flex justify-between items-center mb-1.5">
            <span className={`font-bold ${c.approved ? "text-green-400" : "text-red-400"}`}>
              {c.approved ? "APPROVED" : "REJECTED"} — {c.buy_count}/3 agents voted BUY
            </span>
            <button onClick={onClose} className="text-green-800 hover:text-green-500">✕ close</button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {c.votes.map((v) => {
              const isBuy = v.decision === "BUY";
              return (
                <div key={v.agent} className={`border rounded p-1.5 ${isBuy ? "border-green-800" : "border-red-900"}`}>
                  <div className="flex justify-between mb-0.5">
                    <span className="text-green-600 font-bold">{AGENT_SHORT[v.agent] || v.agent.slice(0,3)} · {v.agent}</span>
                    <span className={`font-bold ${isBuy ? "text-green-400" : "text-red-400"}`}>{v.decision}</span>
                  </div>
                  <div className="text-green-700 mb-0.5">confidence: <span className="text-green-500">{(v.confidence * 100).toFixed(0)}%</span></div>
                  {v.reasoning
                    ? <p className="text-green-600 leading-snug">{v.reasoning}</p>
                    : <p className="text-green-900 italic">No reasoning (old event — trigger ANALYZE to get fresh reasoning)</p>
                  }
                </div>
              );
            })}
          </div>
          <div className="text-green-900 mt-1 text-xs">
            logged {new Date(c.time).toLocaleString("sv-SE", { timeZone: "Europe/Stockholm" })} CET
          </div>
        </div>
      </td>
    </tr>
  );
}

function AnalyzeButton({ execute }: { execute: boolean }) {
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");
  const [summary, setSummary] = useState<string>("");

  async function run() {
    setState("loading");
    setSummary("");
    try {
      const res = await fetch(`/api/proxy/whales/live-positions/analyze?execute=${execute}`, { method: "POST" });
      const data = await res.json();
      const results: {status: string; market: string; buy_count?: number}[] = data.results || [];
      const approved = results.filter(r => r.status === "approved").length;
      const rejected = results.filter(r => r.status === "rejected").length;
      const filtered = results.filter(r => r.status === "filtered" || r.status === "already_holding").length;
      const traded = results.filter(r => (r as {traded?: boolean}).traded).length;
      const parts = [`${results.length} markets analyzed`];
      if (approved) parts.push(`${approved} approved`);
      if (rejected) parts.push(`${rejected} rejected`);
      if (filtered) parts.push(`${filtered} filtered`);
      if (traded) parts.push(`${traded} TRADED`);
      setSummary(parts.join(" · "));
      setState("done");
      if (traded) setTimeout(() => window.location.reload(), 1500);
      else setTimeout(() => setState("idle"), 8000);
    } catch {
      setSummary("Error — check Railway logs");
      setState("done");
      setTimeout(() => setState("idle"), 5000);
    }
  }

  return (
    <div className="inline-flex items-center gap-2">
      <button
        onClick={run}
        disabled={state === "loading"}
        className={`border rounded px-2 py-0.5 text-xs font-bold transition-colors ${
          state === "loading"
            ? "border-green-800 text-green-800 cursor-wait"
            : execute
              ? "border-green-500 text-green-400 hover:bg-green-900/40"
              : "border-green-700 text-green-600 hover:bg-green-950/40"
        }`}
      >
        {state === "loading" ? "ANALYZING…" : execute ? "⚡ ANALYZE + TRADE" : "ANALYZE (DRY RUN)"}
      </button>
      {summary && <span className="text-green-600 text-xs">{summary}</span>}
    </div>
  );
}

function ByMarketTable({ markets }: { markets: WhaleLiveMarket[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (markets.length === 0) {
    return <p className="text-green-800 text-xs py-2 text-center">No markets with ≥2 whales found.</p>;
  }
  const maxW = Math.max(...markets.map(m => m.whale_count));
  return (
    <div className="overflow-auto max-h-80">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-green-700">
            <th className="text-left pb-1 w-5">#</th>
            <th className="text-left pb-1">MARKET</th>
            <th className="text-right pb-1">OUT</th>
            <th className="text-right pb-1">WHALES</th>
            <th className="text-right pb-1">TOTAL $</th>
            <th className="text-right pb-1">AVG PRICE</th>
            <th className="text-right pb-1">CLOSES</th>
            <th className="text-right pb-1">CONSENSUS</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((m, i) => {
            const isHot = m.whale_count >= 5;
            const countColor = isHot ? "text-green-300" : m.whale_count >= 3 ? "text-green-400" : "text-green-600";
            const outColor = m.outcome === "YES" ? "text-green-400" : "text-yellow-500";
            const val = m.total_whale_value >= 10000
              ? `$${(m.total_whale_value / 1000).toFixed(0)}k`
              : `$${m.total_whale_value.toFixed(0)}`;
            const isOpen = expanded === m.condition_id + m.outcome;
            return (
              <>
                <tr key={m.condition_id + m.outcome} className="border-t border-green-950 hover:bg-green-950/20">
                  <td className="py-0.5 text-green-800 pr-1">{i + 1}</td>
                  <td className="py-0.5 pr-2">
                    <a href={`https://polymarket.com/market/${m.condition_id}`} target="_blank" rel="noopener noreferrer"
                      className="text-green-500 hover:text-green-300" title={m.title}>
                      {m.title.length > 58 ? m.title.slice(0, 58) + "…" : m.title}
                    </a>
                  </td>
                  <td className={`text-right font-bold ${outColor}`}>{m.outcome}</td>
                  <td className="text-right">
                    <span className={`font-bold ${countColor}`}>{m.whale_count}</span>
                    <WhalBar count={m.whale_count} max={maxW} />
                  </td>
                  <td className="text-right text-green-400">{val}</td>
                  <td className="text-right text-green-600">{m.avg_price.toFixed(2)}</td>
                  <td className="text-right"><DaysStr d={m.days_left} /></td>
                  <td className="text-right pl-2">
                    {m.consensus
                      ? <ConsensusBadge c={m.consensus} isOpen={isOpen}
                          onClick={() => setExpanded(isOpen ? null : m.condition_id + m.outcome)} />
                      : <span className="text-green-900 text-xs">—</span>
                    }
                  </td>
                </tr>
                {isOpen && m.consensus && (
                  <ConsensusDetail c={m.consensus} onClose={() => setExpanded(null)} />
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ByWhaleTable({ whales }: { whales: WhalePortfolio[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (whales.length === 0) {
    return <p className="text-green-900 text-xs py-2 text-center">No active positions found across tracked whales.</p>;
  }
  return (
    <div className="overflow-auto max-h-96">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-green-700">
            <th className="text-left pb-1">WHALE</th>
            <th className="text-right pb-1">ROI</th>
            <th className="text-right pb-1">POSITIONS</th>
            <th className="text-left pb-1 pl-3">CURRENT BETS (click to expand)</th>
          </tr>
        </thead>
        <tbody>
          {whales.map((w) => {
            const isOpen = expanded === w.address;
            const roiColor = w.roi_pct > 200 ? "text-green-300" : w.roi_pct > 50 ? "text-green-400" : "text-green-600";
            const totalVal = w.positions.reduce((s, p) => s + p.value, 0);
            const topPos = w.positions[0];
            return (
              <>
                <tr key={w.address}
                  className="border-t border-green-950 hover:bg-green-950/20 cursor-pointer"
                  onClick={() => setExpanded(isOpen ? null : w.address)}
                >
                  <td className="py-0.5">
                    <a href={`https://polymarket.com/profile/${w.address}`} target="_blank" rel="noopener noreferrer"
                      className="text-green-600 hover:text-green-400" onClick={e => e.stopPropagation()}
                      title={w.address}>
                      {w.address.slice(0, 6)}…{w.address.slice(-4)}
                    </a>
                  </td>
                  <td className={`text-right ${roiColor}`}>{w.roi_pct > 0 ? `${w.roi_pct.toFixed(0)}%` : "—"}</td>
                  <td className="text-right text-green-400">{w.position_count} · ${totalVal >= 1000 ? `${(totalVal/1000).toFixed(1)}k` : totalVal.toFixed(0)}</td>
                  <td className="pl-3 text-green-700">
                    {isOpen ? "▲ collapse" : topPos
                      ? <span><span className={topPos.outcome === "YES" ? "text-green-500" : "text-yellow-500"}>{topPos.outcome}</span> {topPos.title.slice(0, 45)}{topPos.title.length > 45 ? "…" : ""} <span className="text-green-900">▼ {w.position_count} total</span></span>
                      : "—"
                    }
                  </td>
                </tr>
                {isOpen && (
                  <tr key={w.address + "_detail"}>
                    <td colSpan={4} className="pb-2 px-2">
                      <div className="border border-green-900 rounded p-1.5 bg-green-950/30">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-green-800">
                              <th className="text-left pb-0.5">MARKET</th>
                              <th className="text-right pb-0.5">OUT</th>
                              <th className="text-right pb-0.5">PRICE</th>
                              <th className="text-right pb-0.5">VALUE</th>
                              <th className="text-right pb-0.5">CLOSES</th>
                            </tr>
                          </thead>
                          <tbody>
                            {w.positions.map((p, j) => (
                              <tr key={j} className="border-t border-green-950">
                                <td className="py-0.5 pr-2">
                                  <a href={`https://polymarket.com/market/${p.condition_id}`}
                                    target="_blank" rel="noopener noreferrer"
                                    className="text-green-600 hover:text-green-400" title={p.title}>
                                    {p.title.length > 55 ? p.title.slice(0, 55) + "…" : p.title}
                                  </a>
                                </td>
                                <td className={`text-right font-bold ${p.outcome === "YES" ? "text-green-500" : "text-yellow-500"}`}>{p.outcome}</td>
                                <td className="text-right text-green-600">{p.price.toFixed(2)}</td>
                                <td className="text-right text-green-400">${p.value.toFixed(0)}</td>
                                <td className="text-right"><DaysStr d={p.days_left} /></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function WhalePositions({ data }: { data: { by_market: WhaleLiveMarket[]; by_whale: WhalePortfolio[] } }) {
  const [tab, setTab] = useState<"market" | "whale">("market");
  const [executeMode, setExecuteMode] = useState(false);
  const markets = data?.by_market ?? [];
  const whales = data?.by_whale ?? [];

  return (
    <div className="border border-green-900 rounded p-2 mt-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 border-b border-green-900 pb-1">
        <div className="flex items-center gap-3">
          <h2 className="text-xs font-bold text-green-500">WHALE LIVE POSITIONS</h2>
          <button onClick={() => setTab("market")}
            className={`text-xs px-2 rounded ${tab === "market" ? "bg-green-900 text-green-300" : "text-green-700 hover:text-green-500"}`}>
            BY MARKET ({markets.length})
          </button>
          <button onClick={() => setTab("whale")}
            className={`text-xs px-2 rounded ${tab === "whale" ? "bg-green-900 text-green-300" : "text-green-700 hover:text-green-500"}`}>
            BY WHALE ({whales.length} active)
          </button>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-green-700 flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={executeMode} onChange={e => setExecuteMode(e.target.checked)}
              className="accent-green-500" />
            live trades
          </label>
          <AnalyzeButton execute={executeMode} />
        </div>
      </div>

      {tab === "market"
        ? <ByMarketTable markets={markets} />
        : <ByWhaleTable whales={whales} />
      }

      <p className="text-green-900 text-xs mt-1">
        Cached 5 min · — = bot never ran consensus on this market · click ANALYZE to run now
      </p>
    </div>
  );
}
