import { Whale } from "../lib/api";

export default function WhaleTable({ whales }: { whales: Whale[] }) {
  return (
    <div className="border border-green-900 rounded p-2 h-full">
      <h2 className="text-xs font-bold text-green-500 mb-2 border-b border-green-900 pb-1">
        WHALE TRACKER // {whales.length} WALLETS
      </h2>
      <div className="overflow-auto max-h-96">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-green-700">
              <th className="text-left pb-1">#</th>
              <th className="text-left pb-1">WALLET</th>
              <th className="text-right pb-1">ROI</th>
              <th className="text-right pb-1">TRADES</th>
              <th className="text-right pb-1">AVG</th>
              <th className="text-right pb-1">BALANCE</th>
            </tr>
          </thead>
          <tbody>
            {whales.slice(0, 40).map((w, i) => {
              const trades = w.total_trades ?? 0;
              const avgSize = w.avg_position_size_usdc ?? 0;
              const sizeStr = avgSize >= 10000 ? `$${(avgSize/1000).toFixed(0)}k` : `$${avgSize.toFixed(0)}`;
              const bal = w.balance_usdc ?? 0;
              const balStr = bal >= 1000000 ? `$${(bal/1000000).toFixed(1)}M` : bal >= 1000 ? `$${(bal/1000).toFixed(0)}k` : bal > 0 ? `$${bal.toFixed(0)}` : "—";
              const balColor = bal >= 10000 ? "text-green-300" : bal >= 1000 ? "text-green-500" : "text-green-800";
              const roi = w.roi_pct ?? 0;
              const roiStr = roi === 0 ? "—" : roi >= 1000 ? `${(roi/1000).toFixed(1)}kx` : `${roi.toFixed(0)}%`;
              const roiColor = roi > 100 ? "text-green-300" : roi > 0 ? "text-green-500" : "text-green-800";
              return (
                <tr key={w.address} className="border-t border-green-950">
                  <td className="py-0.5 text-green-800 pr-1">{i + 1}</td>
                  <td className="py-0.5">
                    <a
                      href={`https://polymarket.com/profile/${w.address}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-green-600 hover:text-green-400"
                      title={w.address}
                    >
                      {w.address.slice(0, 6)}…{w.address.slice(-4)}
                    </a>
                  </td>
                  <td className={`text-right ${roiColor}`}>{roiStr}</td>
                  <td className="text-right text-green-400">{trades.toLocaleString()}</td>
                  <td className="text-right text-green-500">{sizeStr}</td>
                  <td className={`text-right ${balColor}`}>{balStr}</td>
                </tr>
              );
            })}
            {whales.length === 0 && (
              <tr>
                <td colSpan={3} className="text-green-800 py-4 text-center">
                  No whales loaded yet.
                  <br />Run select_whales.py
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
