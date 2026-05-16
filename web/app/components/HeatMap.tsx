import { Position } from "../lib/api";

interface HeatMapEntry {
  category: string;
  volume: number;
  liquidity: number;
  market_count: number;
  top_markets: { title: string; volume: number; liquidity: number }[];
}

const CAT_COLORS: Record<string, { border: string; text: string; badge: string; posText: string }> = {
  Politics: { border: "border-blue-900", text: "text-blue-400", badge: "bg-blue-950 text-blue-400", posText: "text-blue-300" },
  Sports:   { border: "border-yellow-900", text: "text-yellow-400", badge: "bg-yellow-950 text-yellow-400", posText: "text-yellow-300" },
  Crypto:   { border: "border-orange-900", text: "text-orange-400", badge: "bg-orange-950 text-orange-400", posText: "text-orange-300" },
  Tech:     { border: "border-purple-900", text: "text-purple-400", badge: "bg-purple-950 text-purple-400", posText: "text-purple-300" },
  Economy:  { border: "border-green-800", text: "text-green-400", badge: "bg-green-950 text-green-400", posText: "text-green-300" },
  Other:    { border: "border-green-950", text: "text-green-700", badge: "bg-green-950 text-green-700", posText: "text-green-600" },
};

function fmt(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n}`;
}

function classifyPosition(p: Position): string {
  const t = (p.market_category || p.market_group || p.market_question || "").toLowerCase();
  if (/bitcoin|btc|eth|crypto|solana|doge|xrp|blockchain|token/.test(t)) return "Crypto";
  if (/trump|biden|harris|president|election|democrat|republican|senate|congress|vote|tariff|nato/.test(t)) return "Politics";
  if (/nba|nfl|mlb|nhl|soccer|football|basketball|baseball|tennis|golf|ufc|mma|world cup|champion|fifa/.test(t)) return "Sports";
  if (/openai|gpt|llm|anthropic|google|apple|microsoft|nvidia|tech|startup/.test(t)) return "Tech";
  if (/oil|gold|inflation|gdp|recession|rate|economy|s&p|nasdaq/.test(t)) return "Economy";
  return "Other";
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (h > 0) return `${h}h ago`;
  return `${m}m ago`;
}

function daysUntil(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now();
  const d = Math.floor(diff / 86400000);
  if (d <= 0) return "today";
  if (d === 1) return "1d";
  return `${d}d`;
}

export default function HeatMap({ data, positions }: { data: HeatMapEntry[]; positions: Position[] }) {
  if (!data || data.length === 0) return null;

  const totalVol = data.reduce((s, d) => s + d.volume, 0);
  const openPositions = positions.filter(p => p.status === "open");

  // Map positions to categories
  const posByCategory: Record<string, Position[]> = {};
  for (const p of openPositions) {
    const cat = classifyPosition(p);
    if (!posByCategory[cat]) posByCategory[cat] = [];
    posByCategory[cat].push(p);
  }

  return (
    <div className="border border-green-900 rounded p-2 mt-3">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        MARKET HEAT MAP
        {openPositions.length > 0 && (
          <span className="text-green-700 font-normal ml-2">● {openPositions.length} open position{openPositions.length > 1 ? "s" : ""}</span>
        )}
      </h2>
      <div className="grid grid-cols-6 gap-2">
        {data.map((cat) => {
          const pct = totalVol > 0 ? ((cat.volume / totalVol) * 100).toFixed(0) : "0";
          const c = CAT_COLORS[cat.category] ?? CAT_COLORS.Other;
          const myPositions = posByCategory[cat.category] || [];

          return (
            <div key={cat.category} className={`border rounded p-2 ${c.border}`}>
              {/* Header */}
              <div className="flex items-center justify-between mb-1">
                <span className={`font-bold text-xs ${c.text}`}>{cat.category}</span>
                <span className="text-green-800 text-xs">{pct}%</span>
              </div>
              <div className="text-green-600 text-xs">{fmt(cat.volume)}</div>
              <div className="text-green-900 text-xs mb-1">{cat.market_count} markets</div>

              {/* Your positions in this category */}
              {myPositions.length > 0 && (
                <div className={`rounded p-1 mb-1 ${c.badge.split(" ")[0]} border ${c.border}`}>
                  <div className="text-green-600 text-xs mb-0.5">YOUR BETS</div>
                  {myPositions.map(p => (
                    <div key={p.position_id} className="text-xs mb-0.5">
                      <div className={`truncate ${c.posText}`} title={p.market_question}>
                        {p.market_question?.slice(0, 28)}…
                      </div>
                      <div className="text-green-800 flex gap-1">
                        <span>{p.strategy === "quick_bet" ? "QB" : "W"}</span>
                        <span>NO @ {p.entry_price?.toFixed(2)}</span>
                        <span>·</span>
                        <span>{timeAgo(p.opened_at)}</span>
                        <span>·</span>
                        <span>closes {daysUntil(p.end_date_iso)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Top markets */}
              <div className="space-y-0.5">
                {cat.top_markets.map((m, i) => (
                  <div key={i} className="text-green-900 text-xs truncate" title={m.title}>
                    {m.title.slice(0, 28)}… <span className="text-green-950">{fmt(m.volume)}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
// Sat May 16 12:43:30 CEST 2026
