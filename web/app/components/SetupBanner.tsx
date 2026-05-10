"use client";

import { useState } from "react";
import { triggerAction } from "../lib/api";

interface Props {
  alreadyRunning?: boolean;
  stage?: string;
  rowsDownloaded?: number;
  walletsScanned?: number;
}

const STAGE_LABELS: Record<string, string> = {
  fetching: "Downloading trade history from Polymarket subgraph…",
  ranking: "Ranking wallets by win rate and profit…",
  selecting: "Selecting top whale wallets…",
  done: "Done! Refresh the page.",
  failed: "Setup failed — check Railway logs.",
  not_started: "Not started yet.",
};

export default function SetupBanner({ alreadyRunning = false, stage = "", rowsDownloaded = 0, walletsScanned = 0 }: Props) {
  const [state, setState] = useState<"idle" | "loading" | "running" | "error">(
    alreadyRunning ? "running" : "idle"
  );

  async function runSetup() {
    setState("loading");
    try {
      const res = await triggerAction("setup");
      if (res.status === "already_running") {
        setState("running");
      } else {
        setState("running");
      }
    } catch {
      setState("error");
    }
  }

  return (
    <div className="border border-yellow-700 bg-yellow-950/30 rounded p-4 mb-4 text-center">
      <p className="text-yellow-400 font-bold text-sm mb-1">⚠ NO DATA YET — BOT NOT READY</p>
      <p className="text-yellow-700 text-xs mb-3">
        The trade history hasn&apos;t been downloaded yet. Click the button below to run the full
        setup pipeline on Railway. It will download all Polymarket trades, rank wallets by win rate,
        and select the top 20 whale wallets to track. This takes several hours.
      </p>

      {state === "idle" && (
        <button
          onClick={runSetup}
          className="bg-yellow-600 hover:bg-yellow-500 text-black font-bold px-6 py-2 rounded text-sm"
        >
          RUN SETUP ON RAILWAY
        </button>
      )}

      {state === "loading" && (
        <p className="text-yellow-400 text-sm">Starting setup...</p>
      )}

      {state === "running" && (
        <div>
          <p className="text-green-400 text-sm font-bold">✓ Setup is running on Railway</p>
          <p className="text-green-400 text-xs mt-1">{STAGE_LABELS[stage] ?? "Running…"}</p>
          {rowsDownloaded > 0 && (
            <p className="text-green-700 text-xs mt-1">
              {rowsDownloaded.toLocaleString()} trades downloaded &nbsp;·&nbsp;
              {walletsScanned.toLocaleString()} wallets scanned
            </p>
          )}
          <p className="text-green-800 text-xs mt-2">Refresh this page in a few hours to see results.</p>
        </div>
      )}

      {state === "error" && (
        <div>
          <p className="text-red-400 text-sm">Failed to start setup — is the Railway backend up?</p>
          <button onClick={() => setState("idle")} className="text-xs text-red-600 underline mt-1">
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
