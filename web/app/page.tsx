import { getStats, getPositions, getWhales, getActivity, getConsensusLog, getBotStatus, getSetupStatus } from "./lib/api";
import LocalTime from "./components/LocalTime";
import LiveStatus from "./components/LiveStatus";
import SetupBanner from "./components/SetupBanner";
import StatsBar from "./components/StatsBar";
import WhaleTable from "./components/WhaleTable";
import PositionsTable from "./components/PositionsTable";
import ActivityFeed from "./components/ActivityFeed";
import ConsensusLog from "./components/ConsensusLog";
import BotControls from "./components/BotControls";
import HeatMap from "./components/HeatMap";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const [stats, positions, whales, activity, consensus, status, setupStatus, heatmap] = await Promise.all([
    getStats().catch(() => null),
    getPositions().catch(() => ({ open: [], closed: [] })),
    getWhales().catch(() => ({ whales: [], count: 0, updated_at: "" })),
    getActivity(30).catch(() => []),
    getConsensusLog(15).catch(() => []),
    getBotStatus().catch(() => null),
    getSetupStatus().catch(() => null),
    fetch(`${process.env.RAILWAY_API_URL || "https://polymarket-bot-production-ae2d.up.railway.app"}/api/stats/heatmap`).then(r => r.json()).catch(() => []),
  ]);

  return (
    <main className="min-h-screen bg-black text-green-400 font-mono p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 border-b border-green-900 pb-3">
        <div>
          <h1 className="text-xl font-bold text-green-300">POLYMARKET WHALE BOT</h1>
          <p className="text-xs text-green-700">
            <LiveStatus />
          </p>
        </div>
        <BotControls />
      </div>

      {/* Setup banner — shown when no data exists yet */}
      {!status?.data_ready && (
        <SetupBanner
          alreadyRunning={setupStatus?.setup_running ?? false}
          stage={setupStatus?.stage ?? "not_started"}
          rowsDownloaded={setupStatus?.rows_downloaded ?? 0}
          walletsScanned={setupStatus?.wallets_scanned ?? 0}
        />
      )}

      {/* Stats bar */}
      {stats && <StatsBar stats={stats} />}

      {/* Heat map */}
      <HeatMap data={heatmap} positions={positions.open} />

      {/* Positions */}
      <div className="mt-4">
        <PositionsTable open={positions.open} closed={positions.closed} />
      </div>

      {/* Whale tracker — full width */}
      <div className="mt-3">
        <WhaleTable whales={whales.whales} />
      </div>

      {/* Consensus + Activity */}
      <div className="grid grid-cols-12 gap-3 mt-3">
        <div className="col-span-4">
          <ConsensusLog events={consensus} />
        </div>
        <div className="col-span-8">
          <ActivityFeed events={activity} />
        </div>
      </div>
    </main>
  );
}
