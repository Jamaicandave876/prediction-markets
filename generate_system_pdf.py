"""Generate System_Overview.pdf — comprehensive creator reference for the trading system."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)

OUTPUT = "System_Overview.pdf"

# ── Styles ───────────────────────────────────────────────────────────────────

styles = getSampleStyleSheet()

styles.add(ParagraphStyle(
    "CoverTitle", parent=styles["Title"], fontSize=28, spaceAfter=6,
    textColor=HexColor("#1a1a2e"), alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "CoverSub", parent=styles["Normal"], fontSize=14, spaceAfter=30,
    textColor=HexColor("#555555"), alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "SectionHead", parent=styles["Heading1"], fontSize=16, spaceBefore=18,
    spaceAfter=8, textColor=HexColor("#16213e"),
))
styles.add(ParagraphStyle(
    "SubHead", parent=styles["Heading2"], fontSize=12, spaceBefore=12,
    spaceAfter=4, textColor=HexColor("#0f3460"),
))
styles.add(ParagraphStyle(
    "Body", parent=styles["Normal"], fontSize=10, leading=14,
    spaceAfter=6,
))
styles.add(ParagraphStyle(
    "SmallBody", parent=styles["Normal"], fontSize=9, leading=12,
    spaceAfter=4,
))
styles.add(ParagraphStyle(
    "BulletItem", parent=styles["Normal"], fontSize=10, leading=14,
    leftIndent=20, bulletIndent=10, spaceAfter=3,
))
styles.add(ParagraphStyle(
    "Footer", parent=styles["Normal"], fontSize=8,
    textColor=HexColor("#999999"), alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "SmallBullet", parent=styles["Normal"], fontSize=9, leading=12,
    leftIndent=20, bulletIndent=10, spaceAfter=2,
))
styles.add(ParagraphStyle(
    "CodeBlock", parent=styles["Normal"], fontSize=8, leading=11,
    fontName="Courier", leftIndent=20, spaceAfter=6,
    backColor=HexColor("#f5f5f5"),
))

# ── Helpers ──────────────────────────────────────────────────────────────────

def heading(text):
    return Paragraph(text, styles["SectionHead"])

def subheading(text):
    return Paragraph(text, styles["SubHead"])

def body(text):
    return Paragraph(text, styles["Body"])

def small(text):
    return Paragraph(text, styles["SmallBody"])

def bullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", styles["BulletItem"])

def sbullet(text):
    return Paragraph(f"<bullet>&bull;</bullet> {text}", styles["SmallBullet"])

def code(text):
    return Paragraph(text, styles["CodeBlock"])

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=HexColor("#cccccc"),
                       spaceBefore=6, spaceAfter=6)

def spacer(pts=12):
    return Spacer(1, pts)


TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#16213e")),
    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
    ("FONTSIZE", (0, 0), (-1, 0), 9),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#cccccc")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f8f9fa"), HexColor("#ffffff")]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
])

SMALL_TABLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2d3748")),
    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
    ("FONTSIZE", (0, 0), (-1, 0), 8),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 1), (-1, -1), 7.5),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#cccccc")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f8f9fa"), HexColor("#ffffff")]),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
])


# ── Content ──────────────────────────────────────────────────────────────────

def build():
    doc = SimpleDocTemplate(
        OUTPUT, pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    story = []

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 1: Cover + Architecture
    # ════════════════════════════════════════════════════════════════════════
    story.append(spacer(50))
    story.append(Paragraph("Prediction Market Trading System", styles["CoverTitle"]))
    story.append(Paragraph("Complete Creator Reference", styles["CoverSub"]))
    story.append(spacer(4))
    story.append(Paragraph(
        "Paper Trading on Manifold Markets  |  20 Bots  |  3 Governance Layers  |  Fractional Kelly Sizing",
        styles["CoverSub"],
    ))
    story.append(spacer(8))
    story.append(hr())
    story.append(spacer(4))

    story.append(heading("1. System Architecture"))
    story.append(body(
        "This system is an automated paper-trading platform that monitors prediction markets "
        "on Manifold Markets using 20 specialized trading bots. A three-tier governance layer "
        "coordinates bots, manages risk, and auto-adjusts parameters. The system runs every "
        "3 hours via GitHub Actions, sends real-time Telegram alerts, and publishes a live "
        "dashboard via GitHub Pages."
    ))
    story.append(spacer(2))

    arch_items = [
        "<b>Signal Layer</b> (20 bots) — Each bot scans Manifold for signals matching its strategy, "
        "generates trade entries, and manages exits (target, stop loss, trailing stop, max duration).",
        "<b>Engine Layer</b> (bot_engine.py) — Shared infrastructure for market data fetching, "
        "trade I/O with atomic JSON writes, exit checking, portfolio integration, cross-market caps, "
        "and Telegram notifications.",
        "<b>Intelligence Layer</b> (intelligence.py) — Cross-bot conflict detection, risk limit "
        "enforcement, performance trend analysis, auto-parameter adjustment, and daily reporting. "
        "Monitors all 20 bots.",
        "<b>Governance Layer</b> (3 components) — Meridian (COO), Atlas (CEO), Sentinel (Risk). "
        "Grades bots, detects regime changes, applies circuit breakers.",
        "<b>Position Sizing</b> (portfolio.py) — Fractional Kelly Criterion (0.25x) with loss-streak "
        "dampening and hard ceilings.",
    ]
    for b in arch_items:
        story.append(bullet(b))

    story.append(subheading("How a Trade Flows"))
    story.append(body(
        "1. Bot scans up to 80 markets from Manifold API. "
        "2. Bot identifies a signal matching its strategy. "
        "3. Pre-trade checks: Is bot paused? Open count under limits? Any conflict with other bots? "
        "Cross-market cap (max 2 bots per market)? "
        "4. Portfolio.py calculates stake via Kelly Criterion. "
        "5. Trade is logged to the bot's JSON file + Telegram alert sent. "
        "6. On subsequent runs, bot_engine checks exits: target hit, stop loss, trailing stop, "
        "max duration, market resolved, or custom exit logic. "
        "7. On exit, P&amp;L is computed and portfolio.json updated."
    ))

    story.append(subheading("Execution Order (Every 3 Hours)"))
    story.append(body(
        "run_all.py executes each module sequentially. If one bot fails, it's logged but doesn't "
        "stop the others. Order: Momentum > Fade > Mean Reversion > Volume Surge > Whale > "
        "Contrarian > Gravity > Sniper > Stability > Breakout > Calibration > Reversal > "
        "Smart Money > Time Decay > Sentiment > Accumulation > Underdog > Late Mover > "
        "Hedge > Liquidation > Meridian (COO) > Atlas (CEO) > Sentinel (Risk)."
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 2: Bot Roster
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("2. Trading Bots (20)"))
    story.append(body(
        "Each bot implements a distinct edge hypothesis. Strategies range from momentum-following "
        "to mean-reversion, from whale-tracking to academic calibration bias exploitation. "
        "Each bot writes to its own JSON trade file and backup file."
    ))

    bot_data = [
        ["#", "Bot", "Strategy", "Edge Hypothesis"],
        ["1", "Momentum", "Trend following", "Gradual probability drift signals consensus forming"],
        ["2", "Fade", "Spike reversal", "Sudden price spikes are overreactions that revert"],
        ["3", "Mean Rev", "Extremes revert", "Prob >78% or <22% is overcrowded — reverts to mean"],
        ["4", "Vol Surge", "Follow volume", "2x+ volume surges signal informed trading"],
        ["5", "Whale", "Follow big bets", "Large bettors (100+ Mana) have better information"],
        ["6", "Contrarian", "Against crowd", "Absorbed small-bet flow signals wrong-way retail crowd"],
        ["7", "Gravity", "Near-close trend", "Trends intensify as resolution approaches (0.5-5 days)"],
        ["8", "Sniper", "New markets", "Early consensus in markets <48h old is usually correct"],
        ["9", "Stability", "Range-bound", "Stable markets (low volatility) tend to stay stable"],
        ["10", "Breakout", "Range break", "When stable markets break their range, the move is real"],
        ["11", "Calibration", "Longshot bias", "Events >88% resolve YES only 84-87% of the time (academic)"],
        ["12", "Reversal", "Trend exhaust", "First signs of momentum reversal signal trend end"],
        ["13", "Smart $", "Repeat conviction", "Users placing 2+ large bets same direction are informed"],
        ["14", "Time Decay", "Consensus drift", "Markets >65% lean drift further as close approaches"],
        ["15", "Sentiment", "Price vs count", "When bet count and price disagree, follow the price"],
        ["16", "Accumulate", "Quiet building", "Many small bets in one direction = stealth positioning"],
        ["17", "Underdog", "First crack", "First counter-move in a dormant extreme market = news"],
        ["18", "Late Mover", "Stale prices", "Markets with no bets in 12h+ have exploitable stale prices"],
        ["19", "Hedge", "Cross-market arb", "Related markets with >15pp prob difference are mispriced"],
        ["20", "Liquidation", "Panic dip", "Single large bets that crash price create temp dislocations"],
    ]
    col_widths = [0.3 * inch, 0.7 * inch, 0.9 * inch, 4.7 * inch]
    t = Table(bot_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TABLE_STYLE)
    story.append(t)

    story.append(spacer(6))
    story.append(subheading("Bot-Specific Settings"))
    story.append(body(
        "Each bot can override the default exit settings. Below are the engine defaults — "
        "individual bots may use different values."
    ))

    defaults_data = [
        ["Setting", "Default", "What It Does"],
        ["target_yes", "78%", "Close BUY YES when market prob reaches this"],
        ["target_no", "22%", "Close BUY NO when market prob drops to this"],
        ["stop_pp", "5pp", "Close at a loss if P&L drops this many points (negative)"],
        ["trailing_stop_pp", "4pp", "Once in profit, close if price drops this far from peak"],
        ["max_days", "7 days", "Force-close trade after this many days (prevents stale positions)"],
        ["re-entry cooldown", "12 hours", "Can't re-enter same market within 12h of last exit"],
    ]
    t_def = Table(defaults_data, colWidths=[1.3 * inch, 0.8 * inch, 4.5 * inch], repeatRows=1)
    t_def.setStyle(SMALL_TABLE)
    story.append(t_def)

    story.append(spacer(4))
    story.append(small(
        "<b>Fade bot exceptions:</b> stop_pp=8, max_days=7, targets based on spike normalization (50% revert). "
        "<b>Momentum:</b> max_days=14. <b>Calibration:</b> BUY NO on >88%, BUY YES on <12%, requires 48h age, "
        "14+ days to close, 5+ unique traders, <10pp recent range."
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 3: Risk Management
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("3. Risk Management"))
    story.append(body(
        "Risk is managed at three levels: per-trade (stop losses, trailing stops), per-bot "
        "(position limits, pause after losses), and portfolio-wide (drawdown breakers, direction skew, "
        "cross-bot conflict blocking)."
    ))

    risk_data = [
        ["Control", "Setting", "Description"],
        ["Max open trades", "50 total", "Across all 20 bots combined (avg ~2-3 per bot)"],
        ["Per-bot limit", "5 per bot", "No single bot can dominate the portfolio"],
        ["Per-market limit", "2 bots max", "Max 2 bots can hold positions on the same market"],
        ["Drawdown breaker", "-30pp (7-day)", "Includes BOTH realized and unrealized P&L"],
        ["Loss pause", "5 consecutive", "Bot auto-paused after 5 straight losses"],
        ["Auto-unpause", "2 days max", "Paused bots auto-unpause after 2 days (deadlock recovery)"],
        ["Direction skew", "75% warning", "Alert if >75% of positions lean one direction"],
        ["Conflict block", "Automatic", "Blocks opposing trades on the same market across all bots"],
        ["Stop loss", "4-8pp", "Varies by bot strategy (default 5pp)"],
        ["Trailing stop", "4pp from peak", "Activates once ANY profit is seen (peak > 0)"],
        ["Max duration", "7-21 days", "Auto-closes stale trades (default 7 days)"],
    ]
    t2 = Table(risk_data, colWidths=[1.2 * inch, 1.1 * inch, 4.3 * inch], repeatRows=1)
    t2.setStyle(TABLE_STYLE)
    story.append(t2)

    story.append(spacer(6))
    story.append(subheading("Trailing Stop — How It Actually Works"))
    story.append(body(
        "The trailing stop tracks the highest P&amp;L reached (peak_pnl) since entry. "
        "It activates once any profit is seen (peak > 0). Once active, if the current P&amp;L "
        "drops more than trailing_stop_pp (default 4pp) below the peak, the trade is closed. "
        "Example: If a trade reaches +8pp profit and then drops to +3.5pp, trailing stop fires "
        "(8 - 3.5 = 4.5pp drop > 4pp threshold). This locks in gains on winning trades."
    ))

    story.append(subheading("Cross-Bot Conflict Detection"))
    story.append(body(
        "Before any bot places a new trade, the intelligence layer scans ALL 20 bots' trade files "
        "for open positions on the same market. If another bot holds BUY YES, a BUY NO is blocked "
        "(and vice versa). This prevents the system from betting against itself. Same-direction "
        "trades are allowed (up to the 2-bot-per-market cap)."
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 4: Position Sizing (Kelly)
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("4. Position Sizing: Fractional Kelly Criterion"))
    story.append(body(
        "The Kelly Criterion is a mathematically proven formula for optimal bet sizing in "
        "binary-outcome scenarios. This system uses 25% of full Kelly (\"quarter Kelly\") — "
        "aggressive enough to grow capital, conservative enough to survive edge overestimation."
    ))

    story.append(subheading("The Formula"))
    story.append(body("<b>Step 1 — Estimate edge from signal strength:</b>"))
    story.append(code("edge_pp = min(signal_strength * 10, 20) / 100"))
    story.append(small("Signal strength ranges from 0.0 to 1.5. A strength of 1.0 = 10pp edge. Capped at 20pp."))
    story.append(spacer(2))

    story.append(body("<b>Step 2 — Compute true probability estimate:</b>"))
    story.append(code(
        "BUY YES: p_true = min(p_market + edge_pp, 0.95)<br/>"
        "BUY NO:  p_true = max(p_market - edge_pp, 0.05)"
    ))
    story.append(spacer(2))

    story.append(body("<b>Step 3 — Calculate Kelly fraction:</b>"))
    story.append(code(
        "BUY YES: kelly_f = (p_true - p_market) / (1 - p_market)<br/>"
        "BUY NO:  kelly_f = (p_market - p_true) / p_market"
    ))
    story.append(spacer(2))

    story.append(body("<b>Step 4 — Apply fractional Kelly + dampening:</b>"))
    story.append(code(
        "stake = balance * kelly_f * 0.25 * loss_dampen<br/>"
        "stake = clamp(stake, min=20 Mana, max=8% of balance)"
    ))

    story.append(spacer(4))
    kelly_data = [
        ["Component", "Value", "Purpose"],
        ["Kelly fraction", "0.25x (quarter Kelly)", "Protects against edge overestimation"],
        ["Fallback stake", "5% of balance", "Used when Kelly returns no edge / unavailable"],
        ["Max per trade", "8% of balance", "Hard ceiling — no single trade risks more"],
        ["Min per trade", "20 Mana", "Floor to ensure meaningful positions"],
        ["Loss dampen factor", "0.80x per loss", "Multiplied per consecutive loss (max 5 losses)"],
    ]
    t3 = Table(kelly_data, colWidths=[1.3 * inch, 1.7 * inch, 3.6 * inch], repeatRows=1)
    t3.setStyle(TABLE_STYLE)
    story.append(t3)

    story.append(spacer(4))
    story.append(subheading("Loss Dampening Schedule"))
    story.append(body("When a bot hits a losing streak, its stake is automatically reduced:"))
    dampen_data = [
        ["Consecutive Losses", "Multiplier", "Effect on a 50 Mana Base Stake"],
        ["0 (no streak)", "1.00x", "50 Mana (full size)"],
        ["1 loss", "0.80x", "40 Mana"],
        ["2 losses", "0.64x", "32 Mana"],
        ["3 losses", "0.512x", "25.6 Mana"],
        ["4 losses", "0.41x", "20.5 Mana"],
        ["5+ losses", "0.328x (min)", "20 Mana (hits floor)"],
    ]
    t_damp = Table(dampen_data, colWidths=[1.5 * inch, 1.0 * inch, 4.1 * inch], repeatRows=1)
    t_damp.setStyle(SMALL_TABLE)
    story.append(t_damp)

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 5: Governance Layer (Detailed)
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("5. Governance Layer (3 Components)"))

    story.append(subheading("Meridian — COO (Tactical Operations)"))
    meridian_items = [
        "Monitors all open positions across all 20 bots",
        "Detects multi-bot overlap on the same market",
        "Tracks capital deployment and direction balance (YES% vs NO%)",
        "Adjusts bot capital weights based on recent performance",
        "State stored in: <b>meridian_state.json</b>",
    ]
    for b in meridian_items:
        story.append(bullet(b))

    story.append(subheading("Atlas — CEO (Strategic Oversight)"))
    atlas_items = [
        "Grades each bot A through F based on win rate and cumulative P&amp;L",
        "Identifies market regime changes (trending vs mean-reverting)",
        "Provides 7-day P&amp;L assessment across the entire system",
        "State stored in: <b>atlas_state.json</b> (includes bot_scores with grade + score)",
    ]
    for b in atlas_items:
        story.append(bullet(b))

    story.append(subheading("Sentinel — Risk Manager (Portfolio-Level)"))
    sentinel_items = [
        "Computes total portfolio exposure",
        "Monitors drawdown (realized + unrealized) against -30pp limit",
        "Checks direction skew — warns if &gt;75% of positions lean one way",
        "Applies circuit breakers when risk thresholds are breached",
        "State stored in: <b>sentinel_state.json</b> (includes risk_level: green/yellow/red)",
    ]
    for b in sentinel_items:
        story.append(bullet(b))

    story.append(spacer(6))
    story.append(heading("6. Bot Grading System (A — F)"))
    story.append(body(
        "Atlas grades each bot based on its closed trade performance. Grades appear on the "
        "dashboard next to each bot's name. Here's what they mean:"
    ))

    grade_data = [
        ["Grade", "Color", "Meaning", "What to Do"],
        ["A", "Green", "Top performer — high win rate + positive P&L", "Let it run, consider increasing exposure"],
        ["B", "Light Green", "Good — solid results, minor room for improvement", "Keep running, monitor"],
        ["C", "Yellow", "Average — break-even or small edge", "Watch closely, may improve with more data"],
        ["D", "Orange", "Below average — losing money but may recover", "Consider reducing exposure"],
        ["F", "Red", "Failing — consistent losses, negative P&L", "Strong candidate for removal"],
        ["NEW", "Gray", "No closed trades yet — can't be graded", "Wait for data (needs closed trades)"],
    ]
    t_grade = Table(grade_data, colWidths=[0.5*inch, 0.7*inch, 2.2*inch, 3.2*inch], repeatRows=1)
    t_grade.setStyle(TABLE_STYLE)
    story.append(t_grade)

    story.append(spacer(4))
    story.append(body(
        "After the paper trading period, you should review grades and remove bots that "
        "consistently receive D or F grades. Bots with A or B grades are your best performers. "
        "A bot showing NEW simply hasn't found a qualifying trade yet — give it time."
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 6: Intelligence Layer + Auto-Adjustment
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("7. Intelligence Layer"))
    story.append(body(
        "The intelligence layer sits above all bots and governance. It runs on every cycle "
        "and provides system-wide coordination, monitoring, and self-correction."
    ))

    story.append(subheading("Performance Trend Detection"))
    story.append(body("The system flags the following patterns automatically:"))
    trend_data = [
        ["Pattern", "Trigger", "What It Means"],
        ["Win/loss streak", "3+ consecutive", "Hot or cold streak — may indicate strategy fit to current market conditions"],
        ["Dominant loss reason", "60%+ of losses share same exit_reason (min 3)", "One exit type is killing you (e.g., all stopped_out = stops too tight)"],
        ["Win rate shift", "Recent 10 trades differ from all-time by 15pp+", "Performance is changing — could be improving or degrading"],
        ["Direction bias", "YES vs NO win rates differ by 20pp+ (min 3 each)", "Bot is better in one direction — may be a market regime signal"],
    ]
    t_trend = Table(trend_data, colWidths=[1.2*inch, 2.2*inch, 3.2*inch], repeatRows=1)
    t_trend.setStyle(SMALL_TABLE)
    story.append(t_trend)

    story.append(spacer(6))
    story.append(subheading("Auto-Parameter Adjustment"))
    story.append(body(
        "When performance drifts, the system auto-adjusts parameters. Adjustments are written "
        "to config_overrides.json (never modifies source code). Changes are bounded:"
    ))

    adj_data = [
        ["Trigger", "Action", "Parameter", "Bounds"],
        ["System WR < 40% (last 10)", "Tighten signals", "MIN_DRIFT_SCORE +0.3", "1.0 — 5.0"],
        ["System WR > 65% (last 10)", "Loosen signals", "MIN_DRIFT_SCORE -0.3", "1.0 — 5.0"],
        ["Avg loss worse than -8pp", "Tighten stops", "REVERSAL_THRESHOLD +1", "3 — 8"],
        ["Fade WR < 40% (last 10)", "Tighten fade filter", "SPIKE_MIN_RATIO +0.5", "2.0 — 8.0"],
    ]
    t_adj = Table(adj_data, colWidths=[1.6*inch, 1.1*inch, 1.9*inch, 1.0*inch], repeatRows=1)
    t_adj.setStyle(SMALL_TABLE)
    story.append(t_adj)

    story.append(spacer(4))
    story.append(small(
        "You can manually reset auto-adjustments by deleting config_overrides.json. "
        "The system will recreate it with defaults on the next run."
    ))

    story.append(spacer(6))
    story.append(subheading("Pause / Unpause Logic"))
    story.append(body(
        "A bot is auto-paused after 5 consecutive losses. While paused, it still checks exits "
        "on existing positions but cannot open new trades. It auto-unpauses when: (a) a new win "
        "breaks the streak (consecutive losses drops below 5), or (b) 2 days pass (deadlock "
        "recovery). Pause state is stored in intelligence_state.json."
    ))

    story.append(spacer(6))
    story.append(subheading("Daily Telegram Report"))
    story.append(body("Every ~23 hours, a comprehensive HTML report is sent to Telegram containing:"))
    report_items = [
        "Portfolio summary: total open positions, 7-day P&amp;L (realized + unrealized), direction skew (YES%/NO%)",
        "Per-bot status line: name, ACTIVE/PAUSED, open count, win rate, cumulative P&amp;L in pp",
        "Total P&amp;L across all bots",
        "Conflict count + market names where conflicts were detected",
        "All risk warnings (drawdown, skew, limits)",
        "Top 5 performance trends detected",
        "Any auto-parameter adjustments made this cycle",
    ]
    for b in report_items:
        story.append(sbullet(b))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 7: Market Scanning + Signal Filters
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("8. Market Scanning &amp; Signal Filters"))
    story.append(body(
        "These are the global filters that determine which markets the bots even consider. "
        "Markets that don't pass these filters are skipped entirely."
    ))

    scan_data = [
        ["Filter", "Value", "Purpose"],
        ["MARKETS_TO_SCAN", "80", "Number of markets fetched from Manifold API per cycle"],
        ["MIN_POOL", "300 Mana", "Minimum liquidity (YES + NO pool) — filters out illiquid markets"],
        ["MIN_MARKET_AGE_HR", "1 hour", "Skip brand-new markets (insufficient data)"],
        ["MIN_CLOSE_DAYS", "2 days", "Skip markets closing too soon (not enough time for signals)"],
        ["ENTRY_PROB_LOW", "35%", "Don't enter markets below this probability (too extreme)"],
        ["ENTRY_PROB_HIGH", "78%", "Don't enter markets above this probability (too extreme)"],
        ["MIN_DRIFT_SCORE", "1.5", "Minimum momentum signal strength to trigger entry"],
        ["MIN_CONSISTENCY", "55%", "Minimum % of recent bets in same direction"],
        ["BETS_WINDOW", "30", "Number of recent bets analyzed for signals"],
        ["MIN_BETS", "8", "Minimum bet count to generate a signal"],
    ]
    t_scan = Table(scan_data, colWidths=[1.5*inch, 0.8*inch, 4.3*inch], repeatRows=1)
    t_scan.setStyle(TABLE_STYLE)
    story.append(t_scan)

    story.append(spacer(6))
    story.append(subheading("Fade Bot Specific Filters"))
    fade_data = [
        ["Filter", "Value", "Purpose"],
        ["SPIKE_MIN_SIZE", "6pp", "Minimum price spike to consider (in percentage points)"],
        ["SPIKE_MIN_RATIO", "2.5x", "Spike must be 2.5x larger than gradual drift"],
        ["SPIKE_MAX_WINDOW_HR", "6 hours", "Spike must have occurred within last 6 hours"],
        ["FADE_NORMALIZE_PCT", "50%", "Expect half the spike to retrace (sets target)"],
        ["FADE_STOP_PP", "8pp", "Wider stop loss for fade trades (volatility)"],
        ["FADE_MAX_DAYS", "7 days", "Max duration for fade trades"],
        ["FADE_MIN_REWARD_RATIO", "0.8", "Minimum reward/risk ratio to enter"],
    ]
    t_fade = Table(fade_data, colWidths=[1.6*inch, 0.8*inch, 4.2*inch], repeatRows=1)
    t_fade.setStyle(SMALL_TABLE)
    story.append(t_fade)

    story.append(spacer(6))
    story.append(subheading("Momentum Detection"))
    story.append(body(
        "Momentum signals use time-decay weighting (DECAY_STRENGTH = 2.0) where the newest bet "
        "is weighted ~7x more than the oldest. This emphasizes recent price action. "
        "A drift score of 1.5+ with 55%+ consistency in the same direction triggers a momentum entry."
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 8: Dashboard Guide + Reading Trades
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("9. How to Read the Dashboard"))
    story.append(body(
        "The Trading HQ dashboard is a mobile-friendly web app hosted on GitHub Pages. "
        "It auto-refreshes every 60 seconds and has three views accessed via the bottom nav bar."
    ))

    story.append(subheading("Top Bar"))
    top_items = [
        "<b>Green pulse dot</b> — System is live (always shows; doesn't mean a trade is active right now)",
        "<b>Governance chips</b> — Risk level (GREEN/YELLOW/RED), market regime, direction balance, "
        "open position count, active bot count out of 20",
    ]
    for b in top_items:
        story.append(bullet(b))

    story.append(subheading("Summary Cards (4 cards)"))
    card_items = [
        "<b>Balance</b> — Starting balance + realized P&amp;L (1000 + closed trade profits/losses)",
        "<b>Total Value</b> — Balance + unrealized P&amp;L (what your portfolio is worth right now)",
        "<b>Realized</b> — Profit/loss from closed trades only (locked in)",
        "<b>Unrealized</b> — Profit/loss from open positions (changes with market prices)",
    ]
    for b in card_items:
        story.append(bullet(b))

    story.append(subheading("Positions Tab"))
    pos_items = [
        "Shows all open positions with live P&amp;L (fetches current market prices)",
        "Each card shows: market question (clickable link), bot that placed it, direction (YES/NO), "
        "entry price, current price, stake amount, and P&amp;L in both pp and Mana",
        "<b>Price bar</b> at bottom: gray dot = entry price, blue dot = current price, "
        "green line = target, red line = stop loss",
        "Green text = in profit, Red text = in loss",
    ]
    for b in pos_items:
        story.append(bullet(b))

    story.append(subheading("Bots Tab"))
    bots_items = [
        "Shows all 20 bots in a grid, sorted by performance score",
        "Each card: bot name, grade badge (A/B/C/D/F/NEW), win rate, total P&amp;L in pp, "
        "open/closed trade counts",
        "<b>Dimmed card</b> = bot is paused (still manages exits, can't open new trades)",
        "Use this view to identify which bots to keep vs remove after paper trading",
    ]
    for b in bots_items:
        story.append(bullet(b))

    story.append(subheading("History Tab"))
    hist_items = [
        "Shows last 30 closed trades, newest first",
        "Each entry: market question, P&amp;L in pp, bot name, direction, Mana P&amp;L, "
        "exit reason (target_hit, stopped_out, trailing_stop, stale, resolved_win, resolved_loss), "
        "and exit timestamp",
    ]
    for b in hist_items:
        story.append(bullet(b))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 9: Operations & Troubleshooting
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("10. Operations"))

    story.append(subheading("GitHub Actions Schedule"))
    story.append(body(
        "The system runs via GitHub Actions on a cron schedule: every 3 hours at the top of the hour "
        "(00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 UTC). You can also trigger a "
        "manual run from the Actions tab in your GitHub repo (workflow_dispatch is enabled)."
    ))

    story.append(subheading("What Each Run Does"))
    run_items = [
        "Checks out the repo (actions/checkout@v4)",
        "Sets up Python 3.11 and installs requests",
        "Runs <b>python run_all.py</b> — executes all 20 bots then 3 governance modules",
        "Stages all *.json files (trade files, portfolio, intelligence state, governance state)",
        "Commits with message \"chore: update paper trades + intel state [automated]\"",
        "Pushes to main. Skips commit if nothing changed.",
    ]
    for b in run_items:
        story.append(bullet(b))

    story.append(subheading("Data Files Reference"))
    files_data = [
        ["File", "Purpose", "Updated By"],
        ["trades.json", "Momentum bot trades", "Momentum bot"],
        ["fade_trades.json", "Fade bot trades", "Fade bot"],
        ["[bot]_trades.json", "Each bot's trade log (20 files total)", "Individual bots"],
        ["[bot]_trades.backup.json", "Atomic backup of each trade file", "Bot engine"],
        ["portfolio.json", "Balance, realized P&L, total trades", "Bot engine on each trade"],
        ["intelligence_state.json", "Pause status, streaks, adjustments, report time", "Intelligence layer"],
        ["atlas_state.json", "Bot grades, scores, regime detection", "Atlas (CEO)"],
        ["meridian_state.json", "Direction exposure, capital weights", "Meridian (COO)"],
        ["sentinel_state.json", "Risk level, exposure data", "Sentinel (Risk)"],
        ["config_overrides.json", "Auto-adjusted parameters", "Intelligence layer"],
    ]
    t_files = Table(files_data, colWidths=[1.8*inch, 2.5*inch, 2.3*inch], repeatRows=1)
    t_files.setStyle(SMALL_TABLE)
    story.append(t_files)

    story.append(spacer(8))
    story.append(heading("11. Troubleshooting"))

    story.append(subheading("Common Issues"))
    trouble_data = [
        ["Problem", "Likely Cause", "Fix"],
        ["No trades placed", "Filters too tight or all bots paused", "Check intelligence_state.json for paused bots. Review config.py filters."],
        ["Dashboard shows old data", "Browser cache / GitHub Pages delay", "Hard refresh (Ctrl+Shift+R or pull-down). Pages can take 2-5 min to update."],
        ["Bot shows NEW grade", "No closed trades yet", "Normal — wait for trades to open and close. Can take days."],
        ["GitHub Action fails", "API rate limit or network error", "Check Actions tab for error log. Usually self-resolves on next run."],
        ["Git push rejected", "Automated commit created while you were editing", "Run: git pull --rebase && git push"],
        ["All bots paused", "Drawdown breaker triggered (-30pp)", "Check 7-day P&L. System auto-recovers as losses age out of 7-day window."],
        ["Too many trades on one market", "Cross-market cap not blocking", "Check bot_engine.py _collect_all_trades(). Max 2 bots per market."],
        ["Config changes not taking effect", "config_overrides.json overriding", "Delete config_overrides.json to reset to source values."],
    ]
    t_trouble = Table(trouble_data, colWidths=[1.4*inch, 1.8*inch, 3.4*inch], repeatRows=1)
    t_trouble.setStyle(SMALL_TABLE)
    story.append(t_trouble)

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════════
    # PAGE 10: How to Modify + Glossary
    # ════════════════════════════════════════════════════════════════════════
    story.append(heading("12. How to Modify the System"))

    story.append(subheading("Adding a New Bot"))
    add_items = [
        "Create a new Python file (e.g., my_bot.py) with a main() function",
        "Add the trade file pair to BOT_TRADE_FILES in bot_engine.py",
        "Add the bot name to BOT_NAMES in bot_engine.py",
        "Add the module to the bot list in run_all.py",
        "Add the trade file + display name to docs/index.html (NAMES and FILES dicts)",
        "Add a CSS tag color class in the dashboard stylesheet",
        "Commit and push — the bot will run on the next cycle",
    ]
    for b in add_items:
        story.append(bullet(b))

    story.append(subheading("Removing a Bot"))
    remove_items = [
        "Remove or comment out the module from run_all.py",
        "The bot's existing open trades will go stale and auto-close after max_days",
        "Optionally: remove from dashboard, bot_engine registry, and delete trade files",
        "Do NOT remove while trades are open — let them close first",
    ]
    for b in remove_items:
        story.append(bullet(b))

    story.append(subheading("Adjusting Risk Settings"))
    risk_items = [
        "Edit config.py directly for permanent changes",
        "Or edit config_overrides.json for runtime overrides (survives auto-adjustment)",
        "Key levers: INTEL_MAX_OPEN_TOTAL (position count), INTEL_DRAWDOWN_LIMIT_PP (drawdown), "
        "MAX_STAKE_PCT (max bet size), KELLY_FRACTION (sizing aggressiveness)",
    ]
    for b in risk_items:
        story.append(bullet(b))

    story.append(subheading("Fresh Start / Reset"))
    story.append(body(
        "To reset everything: set portfolio.json to {starting_balance: 1000, realized_pnl: 0, "
        "total_trades: 0}, clear all *_trades.json files to empty arrays [], and delete "
        "intelligence_state.json, atlas_state.json, meridian_state.json, sentinel_state.json. "
        "The system will recreate state files on the next run."
    ))

    story.append(spacer(12))
    story.append(heading("13. Glossary"))
    gloss_data = [
        ["Term", "Definition"],
        ["pp", "Percentage points — a 1pp move means probability changed by 1% (e.g., 50% to 51%)"],
        ["Mana", "Manifold Markets play money currency — starting balance is 1,000 Mana"],
        ["BUY YES", "Betting the market will resolve YES (probability goes up = profit)"],
        ["BUY NO", "Betting the market will resolve NO (probability goes down = profit)"],
        ["P&L", "Profit and Loss — measured in both pp (price movement) and Mana (dollar value)"],
        ["Realized P&L", "Locked-in profit/loss from closed trades"],
        ["Unrealized P&L", "Paper profit/loss on open positions (changes with market)"],
        ["Drawdown", "Peak-to-trough decline — how much you've lost from your highest point"],
        ["Kelly Criterion", "Math formula for optimal bet sizing based on edge and odds"],
        ["Trailing stop", "Exit that follows price up, triggers when price drops X pp from peak"],
        ["Stop loss", "Fixed exit point — closes trade if loss exceeds threshold"],
        ["Direction skew", "Imbalance between YES and NO positions across the portfolio"],
        ["Signal strength", "Bot's confidence in a trade (0.0 to 1.5) — drives Kelly sizing"],
        ["Drift score", "Momentum measurement — higher = stronger directional trend"],
        ["Spike", "Sudden, large price movement in a short time window"],
        ["Resolution", "When a market closes and the outcome (YES/NO) is determined"],
    ]
    t_gloss = Table(gloss_data, colWidths=[1.3*inch, 5.3*inch], repeatRows=1)
    t_gloss.setStyle(TABLE_STYLE)
    story.append(t_gloss)

    story.append(spacer(20))
    story.append(hr())
    story.append(Paragraph(
        "Prediction Market Trading System  |  20 Bots + 3 Governance Layers  |  "
        "Paper Trading on Manifold Markets  |  Complete Creator Reference  |  Generated April 2026",
        styles["Footer"],
    ))

    # ── Build ────────────────────────────────────────────────────────────
    doc.build(story)
    print(f"PDF generated: {OUTPUT}")


if __name__ == "__main__":
    build()
