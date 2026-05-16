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


function ByMarketTable({ markets }: { markets: WhaleLiveMarket[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (markets.length === 0) {
    return <p className="text-green-800 text-xs py-2 text-center">No active whale positions found. Positions refresh every 5 min.</p>;
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
            <th className="text-right pb-1">PRICE</th>
            <th className="text-right pb-1">OPENED</th>
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
            const marketUrl = m.slug
              ? `https://polymarket.com/event/${m.slug}`
              : `https://polymarket.com/search?q=${encodeURIComponent(m.title)}`;
            const isOpen = expanded === m.condition_id + m.outcome;
            return (
              <>
                <tr key={m.condition_id + m.outcome} className="border-t border-green-950 hover:bg-green-950/20">
                  <td className="py-0.5 text-green-800 pr-1">{i + 1}</td>
                  <td className="py-0.5 pr-2">
                    <a href={marketUrl} target="_blank" rel="noopener noreferrer"
                      className="text-green-500 hover:text-green-300" title={m.title}>
                      {m.title.length > 52 ? m.title.slice(0, 52) + "…" : m.title}
                    </a>
                  </td>
                  <td className={`text-right font-bold ${outColor}`}>{m.outcome}</td>
                  <td className="text-right">
                    <span className={`font-bold ${countColor}`}>{m.whale_count}</span>
                    <WhalBar count={m.whale_count} max={maxW} />
                  </td>
                  <td className="text-right text-green-400">{val}</td>
                  <td className="text-right text-green-600">{m.avg_price > 0 ? m.avg_price.toFixed(2) : "—"}</td>
                  <td className="text-right text-green-800">{m.first_whale_opened ? m.first_whale_opened.slice(5) : "—"}</td>
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
  const [expandedWhale, setExpandedWhale] = useState<string | null>(null);
  const [expandedConsensus, setExpandedConsensus] = useState<string | null>(null);

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
            <th className="text-right pb-1">OPEN</th>
            <th className="text-right pb-1">TOTAL $</th>
            <th className="text-left pb-1 pl-3">TOP POSITION (click to expand)</th>
          </tr>
        </thead>
        <tbody>
          {whales.map((w) => {
            const whaleOpen = expandedWhale === w.address;
            const roiColor = w.roi_pct > 200 ? "text-green-300" : w.roi_pct > 50 ? "text-green-400" : "text-green-600";
            const totalVal = w.total_value ?? 0;
            const valStr = totalVal >= 1000 ? `$${(totalVal/1000).toFixed(1)}k` : `$${totalVal.toFixed(0)}`;
            const topPos = w.positions[0];
            return (
              <>
                <tr key={w.address}
                  className="border-t border-green-950 hover:bg-green-950/20 cursor-pointer"
                  onClick={() => { setExpandedWhale(whaleOpen ? null : w.address); setExpandedConsensus(null); }}
                >
                  <td className="py-0.5">
                    <a href={`https://polymarket.com/profile/${w.address}`} target="_blank" rel="noopener noreferrer"
                      className="text-green-600 hover:text-green-400" onClick={e => e.stopPropagation()}
                      title={w.address}>
                      {w.address.slice(0, 6)}…{w.address.slice(-4)}
                    </a>
                  </td>
                  <td className={`text-right ${roiColor}`}>{w.roi_pct > 0 ? `${w.roi_pct.toFixed(0)}%` : "—"}</td>
                  <td className="text-right text-green-400">{w.position_count}</td>
                  <td className="text-right text-green-300">{valStr}</td>
                  <td className="pl-3 text-green-700">
                    {whaleOpen ? "▲ collapse" : topPos
                      ? <span>
                          <span className={topPos.outcome === "YES" ? "text-green-500" : "text-yellow-500"}>{topPos.outcome}</span>
                          {" "}{topPos.title.slice(0, 42)}{topPos.title.length > 42 ? "…" : ""}
                          {" "}<span className="text-green-900">▼ {w.position_count} total</span>
                        </span>
                      : "—"
                    }
                  </td>
                </tr>
                {whaleOpen && (
                  <tr key={w.address + "_detail"}>
                    <td colSpan={5} className="pb-2 px-2">
                      <div className="border border-green-900 rounded p-1.5 bg-green-950/30">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-green-800">
                              <th className="text-left pb-0.5">MARKET</th>
                              <th className="text-right pb-0.5">OUT</th>
                              <th className="text-right pb-0.5">PRICE</th>
                              <th className="text-right pb-0.5">SHARES</th>
                              <th className="text-right pb-0.5">VALUE</th>
                              <th className="text-right pb-0.5">OPENED</th>
                              <th className="text-right pb-0.5">CLOSES</th>
                              <th className="text-right pb-0.5">CONSENSUS</th>
                            </tr>
                          </thead>
                          <tbody>
                            {w.positions.map((p, j) => {
                              const posKey = `${w.address}_${j}`;
                              const consOpen = expandedConsensus === posKey;
                              const posUrl = p.slug
                                ? `https://polymarket.com/event/${p.slug}`
                                : `https://polymarket.com/search?q=${encodeURIComponent(p.title)}`;
                              return (
                                <>
                                  <tr key={j} className="border-t border-green-950">
                                    <td className="py-0.5 pr-2">
                                      <a href={posUrl}
                                        target="_blank" rel="noopener noreferrer"
                                        className="text-green-600 hover:text-green-400" title={p.title}>
                                        {p.title.length > 48 ? p.title.slice(0, 48) + "…" : p.title}
                                      </a>
                                    </td>
                                    <td className={`text-right font-bold ${p.outcome === "YES" ? "text-green-500" : "text-yellow-500"}`}>{p.outcome}</td>
                                    <td className="text-right text-green-600">{p.price > 0 ? p.price.toFixed(2) : "—"}</td>
                                    <td className="text-right text-green-700">{p.size > 0 ? p.size.toFixed(0) : "—"}</td>
                                    <td className="text-right text-green-400">{p.value > 0 ? `$${p.value.toFixed(0)}` : "—"}</td>
                                    <td className="text-right text-green-800">{p.opened_at ? p.opened_at.slice(5) : "—"}</td>
                                    <td className="text-right"><DaysStr d={p.days_left} /></td>
                                    <td className="text-right pl-1">
                                      {p.consensus
                                        ? <ConsensusBadge c={p.consensus} isOpen={consOpen}
                                            onClick={() => setExpandedConsensus(consOpen ? null : posKey)} />
                                        : <span className="text-green-900">—</span>
                                      }
                                    </td>
                                  </tr>
                                  {consOpen && p.consensus && (
                                    <ConsensusDetail c={p.consensus} onClose={() => setExpandedConsensus(null)} />
                                  )}
                                </>
                              );
                            })}
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
        <span className="text-green-900 text-xs">auto-scan every 10 min</span>
      </div>

      {tab === "market"
        ? <ByMarketTable markets={markets} />
        : <ByWhaleTable whales={whales} />
      }

      <p className="text-green-900 text-xs mt-1">
        Refreshes every 5 min · consensus runs automatically every 10 min · click ✓/✗ badge to see agent reasoning · ≥3 whales + approved → auto-trade
      </p>
    </div>
  );
}
