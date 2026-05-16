"use client";

interface WhaleInMarket {
  address: string;
  value: number;
  size: number;
  price: number;
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
}

function bar(count: number, max: number) {
  const pct = Math.min(100, (count / max) * 100);
  return (
    <div className="w-12 bg-green-950 rounded-sm h-1.5 inline-block align-middle ml-1">
      <div className="bg-green-500 h-1.5 rounded-sm" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function WhalePositions({ data }: { data: MarketEntry[] }) {
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
          ● {data.length} markets where ≥2 tracked whales are currently holding
        </span>
      </h2>
      <div className="overflow-auto max-h-72">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-green-700">
              <th className="text-left pb-1 w-6">#</th>
              <th className="text-left pb-1">MARKET</th>
              <th className="text-right pb-1">OUT</th>
              <th className="text-right pb-1">WHALES</th>
              <th className="text-right pb-1">TOTAL $</th>
              <th className="text-right pb-1">AVG PRICE</th>
              <th className="text-right pb-1">CLOSES</th>
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

              return (
                <tr key={m.condition_id} className="border-t border-green-950 hover:bg-green-950/30">
                  <td className="py-0.5 text-green-800 pr-1">{i + 1}</td>
                  <td className="py-0.5 pr-2">
                    <a
                      href={`https://polymarket.com/market/${m.condition_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-green-500 hover:text-green-300"
                      title={m.title}
                    >
                      {m.title.length > 55 ? m.title.slice(0, 55) + "…" : m.title}
                    </a>
                  </td>
                  <td className={`text-right font-bold ${outColor}`}>{m.outcome}</td>
                  <td className="text-right">
                    <span className={`font-bold ${countColor}`}>{m.whale_count}</span>
                    {bar(m.whale_count, maxWhales)}
                  </td>
                  <td className="text-right text-green-400">{val}</td>
                  <td className="text-right text-green-600">{m.avg_price.toFixed(2)}</td>
                  <td className={`text-right ${daysColor}`}>{daysStr}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-green-900 text-xs mt-1">
        Cached 5 min · click market title to open on Polymarket · sorted by # whales
      </p>
    </div>
  );
}
