"use client";

import { useState } from "react";
import { triggerAction } from "../lib/api";

export default function BotControls() {
  const [loading, setLoading] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [live, setLive] = useState(false);

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

  function toggleLive() {
    if (!live) {
      const ok = window.confirm(
        "Switch to LIVE mode?\n\nThe bot will place real orders with your USDC.\n\nMake sure you have funds in your Polymarket wallet."
      );
      if (!ok) return;
    }
    setLive(!live);
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2 text-xs">
        {msg && <span className="text-green-500">{msg}</span>}

        {/* Live/Dry-run toggle */}
        <button
          onClick={toggleLive}
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
          className="border border-green-700 px-2 py-1 rounded hover:bg-green-900/40 disabled:opacity-40"
        >
          {loading === "monitor" ? "…" : "POLL"}
        </button>
        <button
          onClick={() => trigger("quick-bets", live)}
          disabled={loading !== null}
          className="border border-cyan-700 px-2 py-1 rounded hover:bg-cyan-900/40 disabled:opacity-40 text-cyan-400"
        >
          {loading === "quick-bets" ? "…" : "QUICK BET"}
        </button>
        <button
          onClick={() => trigger("position-manager", live)}
          disabled={loading !== null}
          className="border border-green-700 px-2 py-1 rounded hover:bg-green-900/40 disabled:opacity-40"
        >
          {loading === "position-manager" ? "…" : "CHECK EXITS"}
        </button>
        <button
          onClick={() => trigger("refresh-whales")}
          disabled={loading !== null}
          className="border border-yellow-700 px-2 py-1 rounded hover:bg-yellow-900/40 disabled:opacity-40 text-yellow-400"
        >
          {loading === "refresh-whales" ? "…" : "REFRESH WHALES"}
        </button>
        <button
          onClick={() => trigger("setup")}
          disabled={loading !== null}
          className="border border-purple-700 px-2 py-1 rounded hover:bg-purple-900/40 disabled:opacity-40 text-purple-400"
        >
          {loading === "setup" ? "…" : "RUN SETUP"}
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
