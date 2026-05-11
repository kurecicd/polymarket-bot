"use client";

import { useState, useEffect } from "react";
import { triggerAction } from "../lib/api";

export default function BotControls() {
  const [loading, setLoading] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [live, setLive] = useState(false);

  // Load persisted execution mode on mount
  useEffect(() => {
    fetch("https://polymarket-bot-production-ae2d.up.railway.app/api/actions/status")
      .then(r => r.json())
      .then(d => setLive(d.execution_mode === "execute"))
      .catch(() => {});
  }, []);

  async function trigger(action: string, execute = false) {
    setLoading(action);
    setMsg("");
    try {
      await triggerAction(action, execute);
      setMsg(`${action} triggered`);
    } catch {
      setMsg(`Failed: ${action}`);
    } finally {
      setLoading(null);
      setTimeout(() => setMsg(""), 3000);
    }
  }

  async function toggleLive() {
    const next = !live;
    if (next) {
      const ok = window.confirm(
        "Switch to LIVE mode?\n\nThe bot will automatically place real orders every 60 seconds.\n\nMake sure you have USDC in your Polymarket wallet."
      );
      if (!ok) return;
    }
    try {
      const mode = next ? "execute" : "dry_run";
      await fetch(`https://polymarket-bot-production-ae2d.up.railway.app/api/mode/${mode}`, { method: "POST" });
      setLive(next);
    } catch {
      alert("Failed to switch mode — is Railway up?");
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2 text-xs">
        {msg && <span className="text-green-500">{msg}</span>}

        {/* Live/Dry-run toggle */}
        <button
          onClick={toggleLive}
          title={live ? "Bot is placing real orders. Click to switch to dry-run (simulation only)." : "Dry-run mode — bot monitors but places NO real orders. Click to go live."}
          className={`px-3 py-1 rounded font-bold text-xs border ${
            live
              ? "bg-red-600 border-red-500 text-white"
              : "border-green-800 text-green-700 hover:border-green-600"
          }`}
        >
          {live ? "● LIVE" : "○ DRY-RUN"}
        </button>

        <button
          onClick={() => trigger("monitor", live)}
          disabled={loading !== null}
          title="Run one poll cycle now — checks all 20 whale wallets for new trades and copies any signals found."
          className="border border-green-700 px-2 py-1 rounded hover:bg-green-900/40 disabled:opacity-40"
        >
          {loading === "monitor" ? "…" : "POLL"}
        </button>
        <button
          onClick={() => trigger("quick-bets", live)}
          disabled={loading !== null}
          title="Scan active markets for mispricings — places bets where the order book suggests the price is wrong."
          className="border border-cyan-700 px-2 py-1 rounded hover:bg-cyan-900/40 disabled:opacity-40 text-cyan-400"
        >
          {loading === "quick-bets" ? "…" : "QUICK BET"}
        </button>
        <button
          onClick={() => trigger("position-manager", live)}
          disabled={loading !== null}
          title="Check all open positions for exit conditions: +25% profit, whale selling, or market closing soon."
          className="border border-green-700 px-2 py-1 rounded hover:bg-green-900/40 disabled:opacity-40"
        >
          {loading === "position-manager" ? "…" : "CHECK EXITS"}
        </button>
        <button
          onClick={() => trigger("refresh-whales")}
          disabled={loading !== null}
          title="Re-run Dune query to find the most active profitable wallets in the last 30 days and update the watch list."
          className="border border-yellow-700 px-2 py-1 rounded hover:bg-yellow-900/40 disabled:opacity-40 text-yellow-400"
        >
          {loading === "refresh-whales" ? "…" : "REFRESH WHALES"}
        </button>
        <button
          onClick={() => trigger("setup")}
          disabled={loading !== null}
          title="Re-run full setup: refreshes whale rankings from blockchain via Dune. Only needed monthly or if whale list goes stale."
          className="border border-green-900 px-2 py-1 rounded text-green-900 disabled:opacity-40 cursor-default text-xs"
        >
          SETUP ✓
        </button>
      </div>
      {live && (
        <p className="text-red-400 text-xs">
          ● LIVE — real orders will be placed with your USDC
        </p>
      )}
    </div>
  );
}
