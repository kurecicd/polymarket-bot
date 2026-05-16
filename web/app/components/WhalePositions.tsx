"use client";
import { useState } from "react";

interface WhaleInMarket {
  address: string;
  value: number;
  size: number;
  price: number;
}

interface ConsensusVote {
  agent: string;
  decision: string;
  confidence: number;
  reasoning?: string;
}

interface Consensus {
  time: string;
  approved: boolean;
  buy_count: number;
  votes: ConsensusVote[];
}

interface MarketEntry {
  condition_id: string;
  title: string;
  outcome: string;
  whale_count: number;
  total_whale_value: number;
  avg_price: number;
  days_left: number | null;
  whales: WhaleInMarket[];
  consensus: Consensus | null;
}

function WhalBar({ count, max }: { count: number; max: number }) {
  const pct = Math.min(100, (count / max) * 100);
  return (
    <div className="w-10 bg-green-950 rounded-sm h-1.5 inline-block align-middle ml-1">
      <div className="bg-green-500 h-1.5 rounded-sm" style={{ width: `${pct}%` }} />
    </div>
  );
}

const AGENT_SHORT: Record<string, string> = {
  "Market Analyst": "MKT",
  "Whale Analyst":  "WHL",
  "Risk Analyst":   "RSK",
};

function ConsensusBadge({ c, onClick }: { c: Consensus; onClick: () => void }) {
  const color = c.approved
    ? "text-green-400 border-green-700"
    : "text-red-400 border-red-900";
  return (
    <button
      onClick={onClick}
      className={`border rounded px-1 text-xs font-mono leading-none ${color} hover:opacity-80`}
      title="Click to see agent reasoning"
    >
      {c.approved ? "✓" : "✗"} {c.buy_count}/3
    </button>
  );
}

function ConsensusDetail({ c, onClose }: { c: Consensus; onClose: () => void }) {
  return (
    <tr>
      <td colSpan={8} className="pb-2 px-1">
        <div className="bg-green-950/60 border border-green-900 rounded p-2 text-xs">
          <div className="flex justify-between items-center mb-1">
            <span className={`font-bold ${c.approved ? "text-green-400" : "text-red-400"}`}>
              {c.approved ? "CONSENSUS APPROVED" : "CONSENSUS REJECTED"} — {c.buy_count}/3 agents voted BUY
            </span>
            <button onClick={onClose} className="text-green-800 hover:text-green-500 text-xs">✕ close</button>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-1">
            {c.votes.map((v) => {
              const isBuy = v.decision === "BUY";
              const agentColor = isBuy ? "text-green-400" : "text-red-400";
              const short = AGENT_SHORT[v.agent] || v.agent.slice(0, 3).toUpperCase();
              return (
                <div key={v.agent} className="border border-green-900 rounded p-1.5">
                  <div className="flex justify-between mb-0.5">
                    <span className="text-green-600 font-bold">{short} · {v.agent}</span>
                    <span className={`font-bold ${agentColor}`}>{v.decision}</span>
                  </div>
                  <div className="text-green-700 mb-0.5">
                    confidence: <span className="text-green-500">{(v.confidence * 100).toFixed(0)}%</span>
                  </div>
                  {v.reasoning ? (
                    <p className="text-green-600 leading-snug">{v.reasoning}</p>
                  ) : (
                    <p className="text-green-900 italic">No reasoning logged (old event)</p>
                  )}
                </div>
              );
            })}
          </div>
          <div className="text-green-900 mt-1">logged {new Date(c.time).toLocaleString("sv-SE", { timeZone: "Europe/Stockholm" })} CET</div>
        </div>
      </td>
    </tr>
  );
}

export default function WhalePositions({ data }: { data: MarketEntry[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="border border-green-900 rounded p-2 mt-3">
        <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
          WHALE LIVE POSITIONS
        </h2>
        <p className="text-green-800 text-xs py-2 text-center">
          No markets with ≥2 whales found. Data refreshes every 5 min.
        </p>
      </div>
    );
  }

  const maxWhales = Math.max(...data.map(d => d.whale_count));

  return (
    <div className="border border-green-900 rounded p-2 mt-3">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        WHALE LIVE POSITIONS
        <span className="text-green-700 font-normal ml-2">
          ● {data.length} markets where ≥2 tracked whales currently hold positions
        </span>
      </h2>
      <div className="overflow-auto max-h-96">
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
            {data.map((m, i) => {
              const isHot = m.whale_count >= 5;
              const isMed = m.whale_count >= 3;
              const countColor = isHot ? "text-green-300" : isMed ? "text-green-400" : "text-green-600";
              const outColor = m.outcome === "YES" ? "text-green-400" : "text-yellow-500";
              const val = m.total_whale_value >= 10000
                ? `$${(m.total_whale_value / 1000).toFixed(0)}k`
                : `$${m.total_whale_value.toFixed(0)}`;
              const daysStr = m.days_left === null ? "—"
                : m.days_left <= 1 ? "today"
                : `${m.days_left.toFixed(0)}d`;
              const daysColor = (m.days_left ?? 999) <= 3 ? "text-yellow-600" : "text-green-800";
              const isOpen = expanded === m.condition_id;

              return (
                <>
                  <tr
                    key={m.condition_id}
                    className="border-t border-green-950 hover:bg-green-950/20 cursor-default"
                  >
                    <td className="py-0.5 text-green-800 pr-1">{i + 1}</td>
                    <td className="py-0.5 pr-2">
                      <a
                        href={`https://polymarket.com/market/${m.condition_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-green-500 hover:text-green-300"
                        title={m.title}
                      >
                        {m.title.length > 58 ? m.title.slice(0, 58) + "…" : m.title}
                      </a>
                    </td>
                    <td className={`text-right font-bold ${outColor}`}>{m.outcome}</td>
                    <td className="text-right">
                      <span className={`font-bold ${countColor}`}>{m.whale_count}</span>
                      <WhalBar count={m.whale_count} max={maxWhales} />
                    </td>
                    <td className="text-right text-green-400">{val}</td>
                    <td className="text-right text-green-600">{m.avg_price.toFixed(2)}</td>
                    <td className={`text-right ${daysColor}`}>{daysStr}</td>
                    <td className="text-right pl-2">
                      {m.consensus ? (
                        <ConsensusBadge
                          c={m.consensus}
                          onClick={() => setExpanded(isOpen ? null : m.condition_id)}
                        />
                      ) : (
                        <span className="text-green-900">—</span>
                      )}
                    </td>
                  </tr>
                  {isOpen && m.consensus && (
                    <ConsensusDetail
                      c={m.consensus}
                      onClose={() => setExpanded(null)}
                    />
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-green-900 text-xs mt-1">
        Cached 5 min · click market to open Polymarket · click ✓/✗ badge to see agent reasoning
      </p>
    </div>
  );
}
