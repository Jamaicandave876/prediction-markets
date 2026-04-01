"""Generate System_Overview.pdf — a 3-4 page document describing the trading system."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
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


# ── Content ──────────────────────────────────────────────────────────────────

def build():
    doc = SimpleDocTemplate(
        OUTPUT, pagesize=letter,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    story = []

    # ── PAGE 1: Cover + Architecture ─────────────────────────────────────
    story.append(spacer(60))
    story.append(Paragraph("Prediction Market Trading System", styles["CoverTitle"]))
    story.append(Paragraph("Technical Overview &amp; Architecture", styles["CoverSub"]))
    story.append(spacer(6))
    story.append(Paragraph("Paper Trading on Manifold Markets  |  20 Bots  |  3 Governance Layers", styles["CoverSub"]))
    story.append(spacer(12))
    story.append(hr())
    story.append(spacer(6))

    story.append(heading("1. System Overview"))
    story.append(body(
        "This system is an automated paper-trading platform that monitors prediction markets "
        "on Manifold Markets using 20 specialized trading bots, each implementing a distinct "
        "strategy. A governance layer (3 components) coordinates the bots, manages risk, and "
        "auto-adjusts parameters based on performance. The system runs every 3 hours via "
        "GitHub Actions and sends real-time alerts to Telegram."
    ))

    story.append(subheading("Architecture"))
    story.append(body(
        "The system follows a layered architecture with clear separation of concerns:"
    ))
    bullet_items = [
        "<b>Signal Layer</b> (20 bots) — Each bot scans Manifold Markets for signals matching its strategy, generates trade entries, and manages exits (target, stop loss, trailing stop, max duration).",
        "<b>Engine Layer</b> (bot_engine.py) — Shared infrastructure for market data fetching, trade I/O, exit checking, portfolio integration, and Telegram notifications.",
        "<b>Intelligence Layer</b> (intelligence.py) — Cross-bot conflict detection, risk limit enforcement, auto-parameter adjustment, and daily reporting. Monitors all 20 bots.",
        "<b>Governance Layer</b> (3 components) — Meridian (COO: tactical operations), Atlas (CEO: strategic grading), Sentinel (Risk Manager: portfolio-level circuit breakers).",
        "<b>Position Sizing</b> (portfolio.py) — Fractional Kelly Criterion (0.25x) for mathematically optimal bet sizing, with loss-streak dampening.",
    ]
    for b in bullet_items:
        story.append(bullet(b))

    story.append(subheading("Key Design Principles"))
    design_items = [
        "<b>Fractional Kelly Criterion</b> — Position sizes are calculated using 25% of the full Kelly fraction, providing mathematically optimal growth while protecting against edge overestimation.",
        "<b>Cross-bot conflict blocking</b> — If one bot holds BUY YES on a market, no other bot can take BUY NO on the same market.",
        "<b>Max 2 bots per market</b> — Prevents concentration risk on any single market.",
        "<b>Direction skew monitoring</b> — Warns if more than 75% of positions lean one way.",
        "<b>Unrealized P&amp;L in drawdown checks</b> — Risk limits include open losses, not just closed trades.",
    ]
    for b in design_items:
        story.append(bullet(b))

    story.append(PageBreak())

    # ── PAGE 2: Bot Roster ───────────────────────────────────────────────
    story.append(heading("2. Trading Bots (20)"))
    story.append(body(
        "Each bot implements a distinct edge hypothesis. Strategies range from momentum-following "
        "to mean-reversion, from whale-tracking to academic calibration bias exploitation."
    ))
    story.append(spacer(4))

    bot_data = [
        ["#", "Bot", "Strategy", "Edge Hypothesis"],
        ["1", "Momentum", "Trend following", "Gradual probability drift signals consensus forming"],
        ["2", "Fade", "Spike reversal", "Sudden price spikes are overreactions that revert"],
        ["3", "Mean Reversion", "Extremes revert", "Probabilities >78% or <22% are overcrowded"],
        ["4", "Volume Surge", "Follow volume", "2x+ volume surges signal informed trading"],
        ["5", "Whale Tracker", "Follow big bets", "Large bettors (100+ Mana) are better informed"],
        ["6", "Contrarian", "Against crowd", "Absorbed small-bet flow signals wrong-way crowd"],
        ["7", "Close Gravity", "Near-close trend", "Trends intensify as resolution approaches (0.5-5d)"],
        ["8", "Fresh Sniper", "New market", "Early consensus in new markets (<48h) is usually correct"],
        ["9", "Stability", "Range-bound", "Stable markets (low volatility) tend to stay stable"],
        ["10", "Breakout", "Range break", "When stable markets break their range, the move is real"],
        ["11", "Calibration", "Longshot bias", "Events priced >88% resolve YES only 84-87% of the time"],
        ["12", "Reversal", "Trend exhaustion", "First signs of momentum reversal signal trend end"],
        ["13", "Smart Money", "Repeat conviction", "Users placing 2+ large bets in same direction are informed"],
        ["14", "Time Decay", "Consensus drift", "Markets leaning >65% drift further as close approaches (7-30d)"],
        ["15", "Sentiment Div.", "Price vs count", "When bet count and price disagree, follow the price"],
        ["16", "Accumulation", "Quiet building", "Many small bets in one direction = stealth positioning"],
        ["17", "Underdog", "First crack", "First counter-move in a dormant extreme market signals news"],
        ["18", "Late Mover", "Stale prices", "Markets with no bets in 12h+ have stale, exploitable prices"],
        ["19", "Hedge", "Cross-market", "Related markets with inconsistent probabilities are mispriced"],
        ["20", "Liquidation", "Panic dip", "Single large bets that crash prices create temporary dislocations"],
    ]

    col_widths = [0.3 * inch, 1.0 * inch, 1.1 * inch, 4.2 * inch]
    t = Table(bot_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TABLE_STYLE)
    story.append(t)

    story.append(PageBreak())

    # ── PAGE 3: Risk Management + Position Sizing ────────────────────────
    story.append(heading("3. Risk Management"))
    story.append(body(
        "Risk is managed at three levels: per-trade (stop losses), per-bot (position limits), "
        "and portfolio-wide (drawdown breakers, direction skew)."
    ))

    risk_data = [
        ["Control", "Setting", "Description"],
        ["Max open trades", "50 total", "Across all 20 bots combined (~2-3 per bot)"],
        ["Per-bot limit", "5 per bot", "No single bot dominates the portfolio"],
        ["Per-market limit", "2 positions", "Max 2 bots on the same market"],
        ["Drawdown breaker", "-30pp (7-day)", "Includes both realized and unrealized P&L"],
        ["Loss pause", "5 consecutive", "Bot paused after 5 straight losses; auto-unpauses after 2 days"],
        ["Direction skew", "75% warning", "Alert if positions are too lopsided (YES vs NO)"],
        ["Conflict blocking", "Automatic", "Blocks opposing trades on the same market across all bots"],
        ["Stop loss", "4-8pp per trade", "Varies by bot strategy"],
        ["Trailing stop", "3-5pp from peak", "Activates once any profit is reached"],
        ["Max duration", "5-21 days", "Stale trades are auto-closed"],
    ]
    t2 = Table(risk_data, colWidths=[1.3 * inch, 1.2 * inch, 4.1 * inch], repeatRows=1)
    t2.setStyle(TABLE_STYLE)
    story.append(t2)

    story.append(spacer(8))
    story.append(heading("4. Position Sizing: Fractional Kelly Criterion"))
    story.append(body(
        "The system uses the Kelly Criterion — a mathematically proven formula for optimal bet sizing "
        "in binary outcome scenarios — scaled to 25% (fractional Kelly) for safety."
    ))
    story.append(spacer(4))
    story.append(body(
        "<b>Formula (BUY YES at market price p):</b>"
    ))
    story.append(body(
        "&nbsp;&nbsp;&nbsp;&nbsp;f* = 0.25 x (p_true - p_market) / (1 - p_market)"
    ))
    story.append(spacer(2))
    story.append(body(
        "Where p_true is estimated from signal strength. Each bot provides a signal_strength field "
        "(0.0 to 1.5) which maps to an estimated edge of 0-15 percentage points. The Kelly fraction "
        "determines what percentage of the portfolio to risk."
    ))
    story.append(spacer(4))

    kelly_data = [
        ["Component", "Value", "Purpose"],
        ["Kelly fraction", "0.25x (quarter Kelly)", "Protects against edge overestimation"],
        ["Base fallback", "5% of balance", "Used when Kelly is unavailable"],
        ["Max per trade", "8% of balance", "Hard ceiling on any single position"],
        ["Min per trade", "20 Mana", "Floor to ensure meaningful positions"],
        ["Loss dampening", "0.8x per loss (max 5)", "Reduces size during losing streaks"],
    ]
    t3 = Table(kelly_data, colWidths=[1.4 * inch, 1.8 * inch, 3.4 * inch], repeatRows=1)
    t3.setStyle(TABLE_STYLE)
    story.append(t3)

    story.append(PageBreak())

    # ── PAGE 4: Governance + Operations ──────────────────────────────────
    story.append(heading("5. Governance Layer"))

    gov_data = [
        ["Role", "Component", "Responsibilities"],
        ["President / COO", "Meridian", "Tactical operations: monitors open positions, detects multi-bot overlap, tracks capital deployment and direction balance, adjusts bot capital weights"],
        ["CEO", "Atlas", "Strategic oversight: grades each bot (A-F) based on win rate and P&L, identifies regime changes (trending vs mean-reverting markets), provides 7-day P&L assessment"],
        ["Risk Manager", "Sentinel", "Portfolio-level risk: computes total exposure, monitors drawdown, checks direction skew, applies circuit breakers when risk thresholds are breached"],
    ]
    t4 = Table(gov_data, colWidths=[1.1 * inch, 0.9 * inch, 4.6 * inch], repeatRows=1)
    t4.setStyle(TABLE_STYLE)
    story.append(t4)

    story.append(spacer(8))
    story.append(heading("6. Intelligence Layer"))
    story.append(body(
        "The intelligence layer sits above all bots and governance, providing system-wide coordination:"
    ))
    intel_items = [
        "<b>Cross-bot conflict detection</b> — Scans all 20 bots for opposing positions on the same market. Blocks new conflicting trades before they're placed.",
        "<b>Performance trend analysis</b> — Tracks winning/losing streaks, dominant loss reasons, win rate trends, and directional bias across all bots.",
        "<b>Auto-parameter adjustment</b> — If system-wide win rate drops below 40%, tightens signal thresholds. If above 65%, loosens them. Adjustments are written to config_overrides.json (not the source code).",
        "<b>Daily Telegram report</b> — Sends a comprehensive digest every 24 hours covering all bot performance, conflicts, risk warnings, and parameter adjustments.",
    ]
    for b in intel_items:
        story.append(bullet(b))

    story.append(spacer(8))
    story.append(heading("7. Operations"))

    story.append(subheading("Execution Schedule"))
    story.append(body(
        "The system runs automatically every 3 hours via GitHub Actions (cron: '0 */3 * * *'). "
        "Each run executes all 20 bots sequentially, then the 3 governance layers, then commits "
        "all state changes (trade files, portfolio, intelligence state) back to the repository. "
        "Manual runs can be triggered from the GitHub Actions tab."
    ))

    story.append(subheading("Data Storage"))
    storage_items = [
        "<b>Trade files</b> — Each bot writes to its own JSON file (e.g., whale_trades.json) with atomic backup (whale_trades.backup.json). Corruption recovery falls back to backup.",
        "<b>Portfolio state</b> — portfolio.json tracks starting balance, realized P&amp;L, and total trades counted across all bots.",
        "<b>Intelligence state</b> — intelligence_state.json persists pause status, loss streaks, adjustment history, and last report timestamp.",
        "<b>Config overrides</b> — config_overrides.json stores auto-adjusted parameters without modifying source code.",
    ]
    for b in storage_items:
        story.append(bullet(b))

    story.append(subheading("Monitoring"))
    mon_items = [
        "<b>Dashboard</b> — Mobile-friendly web dashboard at GitHub Pages showing all positions, P&amp;L, and bot status.",
        "<b>Telegram alerts</b> — Real-time notifications for every trade entry, exit, conflict, and the daily intelligence report.",
        "<b>Git history</b> — Every system run commits state changes, creating a full audit trail of all trading activity.",
    ]
    for b in mon_items:
        story.append(bullet(b))

    story.append(spacer(20))
    story.append(hr())
    story.append(Paragraph(
        "Prediction Market Trading System  |  20 Bots + 3 Governance Layers  |  "
        "Paper Trading on Manifold Markets  |  Generated April 2026",
        styles["Footer"],
    ))

    # ── Build ────────────────────────────────────────────────────────────
    doc.build(story)
    print(f"PDF generated: {OUTPUT}")


if __name__ == "__main__":
    build()
