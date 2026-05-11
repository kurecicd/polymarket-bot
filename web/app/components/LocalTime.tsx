"use client";
export default function LocalTime({ utc }: { utc: string }) {
  return <span>{new Date(utc).toLocaleTimeString(undefined, { hour12: false })}</span>;
}
