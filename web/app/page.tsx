import { getStats, getPositions, getWhales, getActivity, getConsensusLog, getBotStatus } from "./lib/api";
import SetupBanner from "./components/SetupBanner";
import StatsBar from "./components/StatsBar";
import WhaleTable from "./components/WhaleTable";
import PositionsTable from "./components/PositionsTable";
import ActivityFeed from "./components/ActivityFeed";
import ConsensusLog from "./components/ConsensusLog";
import BotControls from "./components/BotControls";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const [stats, positions, whales, activity, consensus, status] = await Promise.all([
    getStats().catch(() => null),
    getPositions().catch(() => ({ open: [], closed: [] })),
    getWhales().catch(() => ({ whales: [], count: 0, updated_at: "" })),
    getActivity(30).catch(() => []),
    getConsensusLog(15).catch(() => []),
    getBotStatus().catch(() => null),
  ]);

  return (
    <main className="min-h-screen bg-black text-green-400 font-mono p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 border-b border-green-900 pb-3">
        <div>
          <h1 className="text-xl font-bold text-green-300">POLYMARKET WHALE BOT</h1>
          <p className="text-xs text-green-700">
            {status?.execution_mode === "execute" ? "● LIVE" : "● DRY-RUN"} &nbsp;·&nbsp;
            {status?.whale_count ?? 0} whales tracked &nbsp;·&nbsp;
            last poll: {status?.last_poll ? new Date(status.last_poll).toLocaleTimeString() : "never"}
          </p>
        </div>
        <BotControls />
      </div>

      {/* Setup banner — shown when no data exists yet */}
      {!status?.data_ready && <SetupBanner />}

      {/* Stats bar */}
      {stats && <StatsBar stats={stats} />}

      {/* Main grid */}
      <div className="grid grid-cols-12 gap-3 mt-4">
        <div className="col-span-3">
          <WhaleTable whales={whales.whales} />
        </div>
        <div className="col-span-3">
          <ConsensusLog events={consensus} />
        </div>
        <div className="col-span-6">
          <PositionsTable open={positions.open} closed={positions.closed} />
        </div>
      </div>

      {/* Activity log */}
      <div className="mt-3">
        <ActivityFeed events={activity} />
      </div>
    </main>
  );
}
