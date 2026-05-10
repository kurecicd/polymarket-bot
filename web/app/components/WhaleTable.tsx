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
              <th className="text-left pb-1">WALLET</th>
              <th className="text-right pb-1">ROI</th>
              <th className="text-right pb-1">PROFIT</th>
            </tr>
          </thead>
          <tbody>
            {whales.slice(0, 20).map((w) => {
              const roi = w.roi_pct ?? 0;
              const roiColor = roi >= 100 ? "text-green-300" : roi >= 20 ? "text-green-400" : "text-yellow-400";
              const roiStr = roi >= 1000 ? `${(roi/1000).toFixed(1)}kx` : `${roi.toFixed(0)}%`;
              return (
                <tr key={w.address} className="border-t border-green-950">
                  <td className="py-0.5 text-green-600">
                    {w.address.slice(0, 6)}…{w.address.slice(-4)}
                  </td>
                  <td className={`text-right ${roiColor}`}>
                    {roiStr}
                  </td>
                  <td className="text-right text-green-300">
                    ${w.total_profit_usdc.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </td>
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
