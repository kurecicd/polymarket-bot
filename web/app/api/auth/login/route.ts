import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "crypto";

const PASSWORD = process.env.DASHBOARD_PASSWORD || "changeme";
const SECRET = process.env.DASHBOARD_SECRET || "secret-key-change-this";

function sign(value: string): string {
  return createHmac("sha256", SECRET).update(value).digest("hex");
}

export async function POST(req: NextRequest) {
  const { password } = await req.json();

  if (password !== PASSWORD) {
    return NextResponse.json({ error: "Wrong password" }, { status: 401 });
  }

  const token = sign("authenticated");
  const res = NextResponse.json({ ok: true });
  res.cookies.set("auth", token, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    maxAge: 60 * 60 * 24 * 30, // 30 days
    path: "/",
  });
  return res;
}
