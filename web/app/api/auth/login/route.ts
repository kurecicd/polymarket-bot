import { NextRequest, NextResponse } from "next/server";

const USERNAME = process.env.DASHBOARD_USERNAME || "admin";
const PASSWORD = process.env.DASHBOARD_PASSWORD || "changeme";
const SECRET = process.env.DASHBOARD_SECRET || "secret-key-change-this";

async function sign(value: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function POST(req: NextRequest) {
  const { username, password } = await req.json();

  if (username !== USERNAME || password !== PASSWORD) {
    return NextResponse.json({ error: "Wrong username or password" }, { status: 401 });
  }

  const token = await sign("authenticated");
  const res = NextResponse.json({ ok: true });
  res.cookies.set("auth", token, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    maxAge: 60 * 60 * 24 * 30,
    path: "/",
  });
  return res;
}
