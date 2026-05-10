/**
 * Catch-all proxy: forwards all /api/proxy/* requests to Railway backend.
 * This eliminates all CORS issues — browser only ever talks to Vercel (same origin).
 */
import { NextRequest, NextResponse } from "next/server";

const RAILWAY_URL = process.env.RAILWAY_API_URL || "https://polymarket-bot-production-ae2d.up.railway.app";

async function handler(req: NextRequest, { params }: { params: { path: string[] } }) {
  const path = params.path.join("/");
  const search = req.nextUrl.search;
  const url = `${RAILWAY_URL}/api/${path}${search}`;

  const res = await fetch(url, {
    method: req.method,
    headers: { "Content-Type": "application/json" },
    body: req.method !== "GET" ? req.body : undefined,
    // @ts-expect-error Next.js streaming
    duplex: "half",
  });

  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
