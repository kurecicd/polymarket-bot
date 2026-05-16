#!/usr/bin/env python3
"""
3-agent AI consensus system using Claude.
Before any trade is placed, 3 independent Claude agents analyze the signal
from different angles. Trade only executes if at least 2/3 vote BUY.

Agents:
  Agent 1 — Market Analyst: evaluates the market question, current odds, and whether
             the price is fair given the event probability.
  Agent 2 — Whale Analyst: evaluates the whale's track record and whether this specific
             trade fits their historical pattern.
  Agent 3 — Risk Analyst: evaluates timing, liquidity, market age, and downside risk.
"""
import os
import re
from dataclasses import dataclass

import anthropic

import common

MODEL = "claude-sonnet-4-6"
VOTES_NEEDED = 2  # out of 3


@dataclass
class AgentVote:
    agent: str
    decision: str  # "BUY" or "SKIP"
    confidence: float  # 0.0-1.0
    reasoning: str


@dataclass
class ConsensusResult:
    approved: bool
    votes: list[AgentVote]
    buy_count: int
    summary: str


def _call_agent(client: anthropic.Anthropic, system_prompt: str, user_prompt: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def _parse_vote(agent_name: str, raw: str) -> AgentVote:
    """Extract DECISION and CONFIDENCE from agent response."""
    decision = "SKIP"
    confidence = 0.5

    # Look for explicit decision line
    for line in raw.upper().splitlines():
        if "DECISION:" in line:
            if "BUY" in line:
                decision = "BUY"
            elif "SKIP" in line or "NO" in line or "PASS" in line:
                decision = "SKIP"
        if "CONFIDENCE:" in line:
            match = re.search(r"(\d+(?:\.\d+)?)", line)
            if match:
                val = float(match.group(1))
                confidence = val / 100.0 if val > 1 else val

    return AgentVote(
        agent=agent_name,
        decision=decision,
        confidence=round(confidence, 2),
        reasoning=raw[:300],
    )


def _build_signal_context(signal: dict, whale: dict) -> str:
    return f"""
MARKET: {signal.get("market_question", "Unknown")}
CURRENT ODDS (price per share): {float(signal.get("price", 0)):.3f} (i.e. {float(signal.get("price", 0)) * 100:.1f}% implied probability)
MARKET LIQUIDITY: ${float(signal.get("market_liquidity", 0)):,.0f}
HOURS UNTIL RESOLUTION: {signal.get("hours_left", "?")}

WHALE STATS:
- ROI (90-day): {whale.get("roi_pct", 0):.0f}%
- Total profit (90-day): ${whale.get("total_profit_usdc", 0):,.0f}
- Total trades (90-day): {whale.get("total_trades", 0)}
- Avg position size: ${whale.get("avg_position_size_usdc", 0):,.0f}
- This trade size: ${float(signal.get("size", 0)) * float(signal.get("price", 0)):,.0f} USDC
""".strip()


def run_consensus(signal: dict, whale: dict) -> ConsensusResult:
    """
    Run 3 independent agent analyses. Returns ConsensusResult with approval decision.
    """
    common.load_env()
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not common.has_real_value(api_key):
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")

    client = anthropic.Anthropic(api_key=api_key)
    context = _build_signal_context(signal, whale)

    # ── Agent 1: Market Analyst ──────────────────────────────────────────────
    agent1_system = (
        "You are a prediction market analyst. Your job is to evaluate whether a market's "
        "current odds make sense given the real-world event. You focus on: is the implied "
        "probability fair? Is there an edge here? Are the odds mispriced?\n\n"
        "Respond in exactly this format:\n"
        "DECISION: BUY or SKIP\n"
        "CONFIDENCE: 0.0 to 1.0\n"
        "REASONING: one or two sentences max."
    )
    agent1_raw = _call_agent(client, agent1_system, f"Analyze this Polymarket signal:\n\n{context}")
    vote1 = _parse_vote("Market Analyst", agent1_raw)

    # ── Agent 2: Whale Analyst ───────────────────────────────────────────────
    agent2_system = (
        "You are a whale behavior analyst for prediction markets. Your job is to evaluate "
        "whether copying this whale's trade makes sense given their track record and the "
        "size/timing of this specific bet. A whale with a 60%+ win rate making a large "
        "confident bet is a strong signal. A small or unusual bet from a whale is weaker.\n\n"
        "Respond in exactly this format:\n"
        "DECISION: BUY or SKIP\n"
        "CONFIDENCE: 0.0 to 1.0\n"
        "REASONING: one or two sentences max."
    )
    agent2_raw = _call_agent(client, agent2_system, f"Analyze this whale's signal:\n\n{context}")
    vote2 = _parse_vote("Whale Analyst", agent2_raw)

    # ── Agent 3: Risk Analyst ────────────────────────────────────────────────
    agent3_system = (
        "You are a risk manager for a prediction market trading bot. Your job is to flag "
        "bad trades: low liquidity, markets too close to resolution, extreme odds (near 0 or 1), "
        "or whale bets that look like noise. You are the skeptic — only approve if the risk/reward "
        "is clearly favorable.\n\n"
        "Respond in exactly this format:\n"
        "DECISION: BUY or SKIP\n"
        "CONFIDENCE: 0.0 to 1.0\n"
        "REASONING: one or two sentences max."
    )
    agent3_raw = _call_agent(client, agent3_system, f"Risk-check this trade signal:\n\n{context}")
    vote3 = _parse_vote("Risk Analyst", agent3_raw)

    votes = [vote1, vote2, vote3]
    buy_count = sum(1 for v in votes if v.decision == "BUY")
    approved = buy_count >= VOTES_NEEDED

    summary_parts = [f"{v.agent}: {v.decision} ({v.confidence:.0%})" for v in votes]
    summary = " | ".join(summary_parts) + f" → {'APPROVED' if approved else 'REJECTED'}"

    common.log_event(
        "consensus",
        common.new_run_id("consensus"),
        "vote_complete",
        market=signal.get("market_question", "")[:80],
        buy_count=buy_count,
        approved=approved,
        votes=[
            {
                "agent": v.agent,
                "decision": v.decision,
                "confidence": v.confidence,
                "reasoning": v.reasoning,
            }
            for v in votes
        ],
    )

    return ConsensusResult(
        approved=approved,
        votes=votes,
        buy_count=buy_count,
        summary=summary,
    )
