interface HeatMapEntry {
  category: string;
  volume: number;
  liquidity: number;
  market_count: number;
  top_markets: { title: string; volume: number; liquidity: number }[];
}

const CAT_COLORS: Record<string, string> = {
  Politics: "text-blue-400 border-blue-900",
  Sports: "text-yellow-400 border-yellow-900",
  Crypto: "text-orange-400 border-orange-900",
  Tech: "text-purple-400 border-purple-900",
  Economy: "text-green-400 border-green-900",
  Other: "text-green-700 border-green-950",
};

function fmt(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n}`;
}

export default function HeatMap({ data }: { data: HeatMapEntry[] }) {
  if (!data || data.length === 0) return null;

  const totalVol = data.reduce((s, d) => s + d.volume, 0);

  return (
    <div className="border border-green-900 rounded p-2 mt-3">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        MARKET HEAT MAP — what's hot now
      </h2>
      <div className="grid grid-cols-6 gap-2">
        {data.map((cat) => {
          const pct = totalVol > 0 ? ((cat.volume / totalVol) * 100).toFixed(0) : "0";
          const colors = CAT_COLORS[cat.category] ?? CAT_COLORS.Other;
          return (
            <div key={cat.category} className={`border rounded p-2 ${colors.split(" ")[1]}`}>
              <div className={`font-bold text-xs ${colors.split(" ")[0]}`}>
                {cat.category} <span className="text-green-700">{pct}%</span>
              </div>
              <div className="text-green-600 text-xs">{fmt(cat.volume)} vol</div>
              <div className="text-green-800 text-xs">{cat.market_count} markets</div>
              <div className="mt-1 space-y-0.5">
                {cat.top_markets.map((m, i) => (
                  <div key={i} className="text-green-800 text-xs truncate" title={m.title}>
                    {m.title.slice(0, 35)}… <span className="text-green-900">{fmt(m.volume)}</span>
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
