"""Generate the system documentation PDF."""

from fpdf import FPDF


class DocPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 8, "Prediction Market Paper Trading System", align="C")
            self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(20, 60, 120)
        self.cell(0, 10, title)
        self.ln(8)
        self.set_draw_color(20, 60, 120)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(40, 40, 40)
        self.cell(0, 8, title)
        self.ln(7)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def bullet(self, text, indent=10):
        x = self.get_x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.set_x(x + indent)
        self.cell(4, 5.5, "-")
        self.multi_cell(0, 5.5, f"  {text}")
        self.ln(1)

    def param_row(self, name, value, desc):
        self.set_font("Courier", "B", 9)
        self.set_text_color(20, 60, 120)
        self.cell(52, 5.5, name)
        self.set_font("Courier", "", 9)
        self.set_text_color(30, 30, 30)
        self.cell(18, 5.5, str(value))
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5.5, desc)
        self.ln(1)

    def code_block(self, text):
        self.set_fill_color(240, 240, 245)
        self.set_font("Courier", "", 9)
        self.set_text_color(30, 30, 30)
        x = self.get_x()
        self.set_x(x + 5)
        for line in text.split("\n"):
            self.cell(180, 5, f"  {line}", fill=True)
            self.ln(5)
        self.ln(3)


def build_pdf():
    pdf = DocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── COVER PAGE ───────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.ln(50)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(0, 15, "Prediction Market", align="C")
    pdf.ln(14)
    pdf.cell(0, 15, "Paper Trading System", align="C")
    pdf.ln(20)
    pdf.set_draw_color(20, 60, 120)
    pdf.set_line_width(1)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "System Documentation & Strategy Guide", align="C")
    pdf.ln(30)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "Three-bot architecture on Manifold Markets", align="C")
    pdf.ln(7)
    pdf.cell(0, 8, "Consensus Momentum Trader  |  Overreaction Fade Bot  |  Intelligence Layer", align="C")
    pdf.ln(7)
    pdf.cell(0, 8, "Automated every 4 hours with Telegram alerts", align="C")
    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 8, "March 2026 (v2 - Post Advisory Board Review)", align="C")

    # ── TABLE OF CONTENTS ────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("Table of Contents")
    pdf.ln(4)
    toc = [
        ("1.", "System Overview", 3),
        ("2.", "How Prediction Markets Work", 3),
        ("3.", "Bot 1: Consensus Momentum Trader", 4),
        ("4.", "Bot 2: Overreaction Fade Bot", 6),
        ("5.", "Intelligence Layer", 8),
        ("6.", "Run Schedule & Automation", 10),
        ("7.", "Telegram Notifications", 11),
        ("8.", "Configuration Reference", 12),
        ("9.", "File Reference", 14),
        ("10.", "Key Concepts & Glossary", 15),
    ]
    for num, title, page in toc:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(20, 60, 120)
        pdf.cell(10, 8, num)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(140, 8, title)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 8, str(page), align="R")
        pdf.ln(8)

    # ── 1. SYSTEM OVERVIEW ───────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("1. System Overview")
    pdf.body_text(
        "This is a paper trading system that tracks prediction markets on Manifold Markets. "
        "It does NOT use real money. Instead, it records hypothetical trades and measures "
        "performance in probability points (pp) to test whether the strategies actually work "
        "before risking anything."
    )
    pdf.body_text(
        "The system consists of three components that run together every 4 hours:"
    )
    pdf.ln(2)
    pdf.sub_title("The Three Components")
    pdf.bullet(
        "Consensus Momentum Trader - Detects markets where probability is drifting "
        "steadily in one direction and bets that the trend continues."
    )
    pdf.bullet(
        "Overreaction Fade Bot - Detects sudden, sharp price spikes and bets that "
        "they will revert back (fade) because they were overreactions."
    )
    pdf.bullet(
        "Intelligence Layer - Sits above both bots as a meta-observer. Detects conflicts, "
        "manages risk, auto-adjusts parameters, and sends a daily intelligence report."
    )
    pdf.ln(4)
    pdf.sub_title("Data Source")
    pdf.body_text(
        "All data comes from the Manifold Markets public API (api.manifold.markets/v0). "
        "No authentication is required. The system reads market probabilities and bet "
        "histories to detect patterns, then records paper trades based on what it finds."
    )
    pdf.ln(2)
    pdf.sub_title("How a Cycle Works")
    pdf.body_text("Every 4 hours, the automated agent runs this sequence:")
    pdf.bullet("1. Momentum bot checks exits on open trades, then scans for new signals")
    pdf.bullet("2. Fade bot checks exits on open trades, then scans for new spike signals")
    pdf.bullet("3. Intelligence layer analyzes both bots, checks risk, adjusts parameters")
    pdf.bullet("4. All updated trade data is committed back to GitHub")
    pdf.bullet("5. Telegram notifications are sent at each step")

    pdf.ln(4)
    pdf.sub_title("How to Use This System (Day-to-Day)")
    pdf.body_text(
        "You do NOT need to keep your computer on, VS Code open, or anything running. "
        "The entire system is fully automated in the cloud. Here is what you need to know:"
    )
    pdf.ln(1)
    pdf.bullet(
        "Everything runs automatically. An Anthropic cloud agent wakes up every 4 hours, "
        "clones your GitHub repo, runs all three bots, and pushes updated trade data back. "
        "This happens 6 times per day at 12am, 4am, 8am, 12pm, 4pm, and 8pm UTC."
    )
    pdf.bullet(
        "Check Telegram on your phone. That is your only interface. You will get notifications "
        "for every new trade, every closed trade, every run summary, and a daily intelligence report."
    )
    pdf.bullet(
        "Look for the tags: [MOMENTUM] is the trend-following bot, [FADE] is the spike-fading bot, "
        "and [INTEL] is the daily intelligence report with overall system health."
    )
    pdf.bullet(
        "Your trade history is on GitHub. Go to github.com/Jamaicandave876/prediction-markets "
        "and look at trades.json (momentum) and fade_trades.json (fade) to see all trades."
    )
    pdf.bullet(
        "You do NOT need to touch any code. The intelligence layer automatically adjusts "
        "parameters when performance is poor. If a bot keeps losing, it gets paused automatically."
    )
    pdf.ln(1)
    pdf.body_text(
        "In short: set it and forget it. Just read the Telegram alerts on your phone."
    )

    # ── 2. HOW PREDICTION MARKETS WORK ───────────────────────────────────────
    pdf.add_page()
    pdf.section_title("2. How Prediction Markets Work")
    pdf.body_text(
        "A prediction market is a market where people bet on the outcome of real-world events. "
        "Each market asks a YES/NO question (e.g., 'Will Bitcoin hit $100K by December?'). "
        "The market price represents the crowd's estimated probability of YES."
    )
    pdf.ln(2)
    pdf.sub_title("Key Concepts")
    pdf.bullet(
        "Probability (0-100%): The current market price. If a market shows 70%, the crowd "
        "thinks there's a 70% chance of YES."
    )
    pdf.bullet(
        "BUY YES: You're betting the probability will go UP (the event is more likely "
        "than the market thinks). You profit when the price rises."
    )
    pdf.bullet(
        "BUY NO: You're betting the probability will go DOWN (the event is less likely "
        "than the market thinks). You profit when the price drops."
    )
    pdf.bullet(
        "Resolution: When the event happens (or doesn't), the market resolves to YES (100%) "
        "or NO (0%). Traders are paid out based on their positions."
    )
    pdf.ln(2)
    pdf.sub_title("Probability Points (pp)")
    pdf.body_text(
        "All P&L in this system is measured in probability points (pp). One pp = one percentage "
        "point of probability movement."
    )
    pdf.body_text(
        "Example: You BUY YES at 60%. The price rises to 72%. "
        "Your profit = 72 - 60 = +12pp. If it drops to 54%, your loss = 54 - 60 = -6pp."
    )
    pdf.body_text(
        "Example: You BUY NO at 60%. The price drops to 45%. "
        "Your profit = 60 - 45 = +15pp. If it rises to 68%, your loss = 60 - 68 = -8pp."
    )

    # ── 3. MOMENTUM TRADER ───────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("3. Bot 1: Consensus Momentum Trader")
    pdf.sub_title("Strategy: Follow the Crowd's Drift")
    pdf.body_text(
        "This bot looks for markets where probability has been steadily drifting in one "
        "direction over recent bets. The idea is that when many independent bettors are all "
        "pushing the price the same way, they're likely responding to real information, and "
        "the trend may continue."
    )
    pdf.ln(2)
    pdf.sub_title("How It Detects Momentum")
    pdf.body_text("For each market, the bot fetches the last 30 bets and computes:")
    pdf.bullet(
        "Drift: The total probability change from oldest to newest bet, weighted by "
        "time-decay so recent bets matter more (newest bet weighted ~7x more than oldest)."
    )
    pdf.bullet(
        "Consistency: What percentage of individual bet-to-bet steps moved in the same "
        "direction as the overall drift. High consistency = steady trend, not random noise."
    )
    pdf.bullet(
        "Drift Score: drift x consistency. This combined score must exceed a minimum "
        "threshold (default 2.0) to qualify as a signal."
    )
    pdf.ln(2)
    pdf.sub_title("Entry Conditions (ALL must be true)")
    pdf.bullet("Market probability is between 45% and 72% (not too extreme)")
    pdf.bullet("At least 8 recent bets available for analysis")
    pdf.bullet("|Drift score| > 2.0 (strong enough momentum)")
    pdf.bullet("Consistency > 65% (most bets agree on direction)")
    pdf.bullet("Market has not been traded before (prevents re-entry)")
    pdf.bullet("No conflict with the fade bot on same market")
    pdf.bullet("Intelligence layer risk limits not exceeded")
    pdf.ln(2)
    pdf.sub_title("Trade Direction")
    pdf.bullet("Drift is positive (price trending UP)   ->  BUY YES")
    pdf.bullet("Drift is negative (price trending DOWN)  ->  BUY NO")
    pdf.ln(2)
    pdf.sub_title("Exit Conditions")
    pdf.body_text("The bot checks these every 4 hours. First one triggered closes the trade:")
    pdf.bullet("Target hit: BUY YES exits when prob >= 78%. BUY NO exits when prob <= 22%.")
    pdf.bullet("Reversal: Price moves 6pp or more against our entry (stop-loss).")
    pdf.bullet("Market resolved: The market ends. If resolution matches our bet = WIN.")
    pdf.bullet("Stale: Trade has been open 14+ days with no exit hit. Closed at REAL current market price (records actual P&L, not 0pp).")

    pdf.add_page()
    pdf.sub_title("Momentum Scoring: Time-Decay Weighting")
    pdf.body_text(
        "Not all bets are created equal. A bet placed 5 minutes ago is more informative "
        "than one from 2 days ago. The bot uses exponential time-decay weighting:"
    )
    pdf.ln(1)
    pdf.code_block(
        "weight(i) = exp(DECAY_STRENGTH * i / n)\n"
        "\n"
        "where i = position (0=oldest, n=newest)\n"
        "      DECAY_STRENGTH = 2.0\n"
        "\n"
        "Result: newest bet is weighted ~7.4x more than oldest"
    )
    pdf.body_text(
        "The weighted drift is then multiplied by consistency to get the final drift_score. "
        "This means a market needs BOTH strong movement AND directional agreement to trigger."
    )
    pdf.ln(2)
    pdf.sub_title("P&L Calculation")
    pdf.code_block(
        "BUY YES:  P&L = exit_prob - entry_prob\n"
        "BUY NO:   P&L = entry_prob - exit_prob\n"
        "\n"
        "On resolution:\n"
        "  YES resolves to 100%, NO resolves to 0%\n"
        "  BUY YES on YES resolution: P&L = 100 - entry\n"
        "  BUY NO  on NO  resolution: P&L = entry - 0"
    )

    # ── 4. FADE BOT ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("4. Bot 2: Overreaction Fade Bot")
    pdf.sub_title("Strategy: Bet Against Sharp Spikes")
    pdf.body_text(
        "This bot looks for markets where the price just moved sharply in a short "
        "period - much more than the normal bet-to-bet movement. The idea is that sudden "
        "spikes are often overreactions driven by panic or hype, and the price will "
        "revert back toward where it was before the spike."
    )
    pdf.ln(2)
    pdf.sub_title("How It Detects Spikes")
    pdf.body_text("For each market, the bot fetches the last 20 bets and splits them:")
    pdf.bullet(
        "Baseline (first 15 bets): Calculates the average step size (how much the price "
        "normally moves between individual bets)."
    )
    pdf.bullet(
        "Recent window (last 5 bets): Calculates the total price change in this window."
    )
    pdf.bullet(
        "Spike size: The absolute price change in the recent window (in pp)."
    )
    pdf.bullet(
        "Spike ratio: spike_size / avg_baseline_step. A ratio of 5.0 means the recent "
        "move was 5x larger than normal."
    )
    pdf.ln(2)
    pdf.sub_title("Entry Conditions (ALL must be true)")
    pdf.bullet("Spike size >= 8pp (the move is big enough to matter)")
    pdf.bullet("Spike ratio >= 3.0x (the move is abnormally large vs baseline)")
    pdf.bullet("Consistency <= 50% (bets are NOT all in the same direction - if they were, it's a real trend, not a spike)")
    pdf.bullet("Time validation: The spike window bets must span less than 6 hours. If 5 bets took days, that's gradual movement, not a real spike.")
    pdf.bullet("Risk-reward check: Expected reward must be at least 80% of expected risk. Rejects trades where the stop-loss is much bigger than the profit target.")
    pdf.bullet("At least 12 bets available for analysis")
    pdf.bullet("Market has not been traded before")
    pdf.bullet("No conflict with momentum bot on same market")
    pdf.bullet("Intelligence layer risk limits not exceeded")
    pdf.ln(2)
    pdf.sub_title("Trade Direction (Opposite of Spike)")
    pdf.bullet("Spike went UP   (price spiked higher)  ->  BUY NO  (bet it comes back down)")
    pdf.bullet("Spike went DOWN (price spiked lower)   ->  BUY YES (bet it comes back up)")
    pdf.ln(2)
    pdf.sub_title("Exit Conditions")
    pdf.bullet(
        "Normalized (WIN): Price retraces 50% of the spike back toward pre-spike level."
    )
    pdf.bullet(
        "Stopped out (LOSS): Price continues 8pp further in spike direction (we were wrong, "
        "it wasn't an overreaction)."
    )
    pdf.bullet("Market resolved: Same as momentum bot.")
    pdf.bullet("Stale: 7 days max (shorter than momentum - spikes resolve quickly). Records real P&L at current market price.")

    pdf.add_page()
    pdf.sub_title("Fade Exit Logic: Normalization Target")
    pdf.body_text(
        "The bot doesn't need the full spike to retrace. It targets 50% retracement:"
    )
    pdf.ln(1)
    pdf.code_block(
        "Example: Price was at 40%, spiked to 60% (+20pp spike)\n"
        "  We BUY NO at 60% (fade the upward spike)\n"
        "  Normalize target = 60 - (20 * 50%) = 50%\n"
        "  If price drops to 50%: WIN, P&L = 60 - 50 = +10pp\n"
        "  Stop loss at 60 + 8 = 68%\n"
        "  If price rises to 68%: LOSS, P&L = 60 - 68 = -8pp"
    )
    pdf.ln(2)
    pdf.sub_title("Why Low Consistency Is Required")
    pdf.body_text(
        "The key filter that separates spikes from trends is the consistency check. If 80% of "
        "bets are pushing in the same direction, that's a genuine trend - not an overreaction. "
        "The fade bot rejects these (consistency must be <= 50%). It only trades when the price "
        "movement looks erratic - a few large bets moved the price sharply, which is the "
        "classic signature of an overreaction."
    )
    pdf.ln(2)
    pdf.sub_title("Time-Aware Spike Validation")
    pdf.body_text(
        "A key improvement from the advisory board review: the system now checks WHEN the "
        "bets in the spike window actually happened, not just how many there are. If the "
        "last 5 bets are spread over several days, that is gradual movement, not a spike. "
        "Real spikes happen fast --within hours. The system rejects any 'spike' where the "
        "spike window spans more than 6 hours (SPIKE_MAX_WINDOW_HR)."
    )
    pdf.ln(2)
    pdf.sub_title("Risk-Reward Filter")
    pdf.body_text(
        "Another advisory board improvement: before entering any fade trade, the bot checks "
        "whether the math makes sense. The expected reward (spike_size * normalize%) must be "
        "at least 80% of the expected risk (stop-loss size). Without this filter, small spikes "
        "could produce trades where you risk 8pp to win only 4pp --structurally unprofitable."
    )
    pdf.code_block(
        "Example of a REJECTED trade (bad risk-reward):\n"
        "  Spike size = 8pp, Normalize = 50%, Stop = 8pp\n"
        "  Expected reward = 8 * 50% = 4pp\n"
        "  Expected risk   = 8pp\n"
        "  Ratio = 4/8 = 0.50 < 0.80 threshold -> REJECTED\n"
        "\n"
        "Example of an ACCEPTED trade (good risk-reward):\n"
        "  Spike size = 14pp, Normalize = 50%, Stop = 8pp\n"
        "  Expected reward = 14 * 50% = 7pp\n"
        "  Expected risk   = 8pp\n"
        "  Ratio = 7/8 = 0.875 >= 0.80 threshold -> ACCEPTED"
    )

    # ── 5. INTELLIGENCE LAYER ────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("5. Intelligence Layer")
    pdf.body_text(
        "The intelligence layer is a meta-observer that sits above both trading bots. It runs "
        "after both bots complete their cycle and provides five core capabilities:"
    )
    pdf.ln(2)
    pdf.sub_title("5.1 Cross-Bot Conflict Detection")
    pdf.body_text(
        "If the momentum bot is BUY YES on a market and the fade bot is BUY NO on the same "
        "market, they're directly contradicting each other. The intelligence layer:"
    )
    pdf.bullet("Scans both trade logs for markets where both bots have open opposing positions.")
    pdf.bullet("Sends a [INTEL] Telegram alert identifying the conflict.")
    pdf.bullet(
        "Pre-trade gate: Before either bot logs a new trade, it checks if the other bot "
        "already has an opposing position. If so, the new trade is blocked."
    )
    pdf.ln(2)
    pdf.sub_title("5.2 Risk Management")
    pdf.body_text("The intelligence layer enforces portfolio-level limits:")
    pdf.bullet("Max 8 open trades total across both bots (5 per individual bot).")
    pdf.bullet("Pauses a bot after 4 consecutive losses (until it gets a win).")
    pdf.bullet(
        "Deadlock recovery: If a paused bot stays paused for 3+ days (all open trades "
        "also lost), it auto-unpauses so it gets a fresh chance. This prevents a permanent "
        "dead state where the bot can never recover."
    )
    pdf.bullet(
        "Tracks 7-day NET P&L (wins + losses combined) and alerts when it drops below -50pp. "
        "Previous versions only counted losses, which dramatically overstated risk."
    )
    pdf.bullet(
        "When limits are hit, the bot's scanning phase is skipped entirely - it still "
        "checks exits on existing trades, but won't open new ones."
    )
    pdf.ln(2)
    pdf.sub_title("5.3 Performance Trend Analysis")
    pdf.body_text("The intelligence layer analyzes patterns across closed trades:")
    pdf.bullet("Win/loss streaks for each bot (helps spot hot or cold periods).")
    pdf.bullet("Dominant loss reasons (e.g., if 80% of losses are reversals, the entry criteria may be too loose).")
    pdf.bullet("Direction bias (tracks whether BUY YES or BUY NO is performing better).")
    pdf.bullet("Win rate trends over the most recent 10 closed trades per bot.")

    pdf.add_page()
    pdf.sub_title("5.4 Auto-Parameter Adjustment")
    pdf.body_text(
        "Based on recent performance, the intelligence layer can automatically tighten or "
        "loosen trading parameters. This is bounded by hard guardrails to prevent runaway changes."
    )
    pdf.ln(2)
    pdf.body_text("Tightening (when win rate < 40% over last 10 trades):")
    pdf.bullet("Raises MIN_DRIFT_SCORE so only stronger momentum triggers entries.")
    pdf.bullet("Raises MIN_CONSISTENCY so trend agreement must be higher.")
    pdf.bullet("Raises SPIKE_MIN_RATIO so only more extreme spikes are faded.")
    pdf.ln(1)
    pdf.body_text("Loosening (when win rate > 65% over last 10 trades):")
    pdf.bullet("Lowers thresholds slightly to capture more opportunities.")
    pdf.ln(1)
    pdf.body_text("Guardrails:")
    pdf.bullet("Every parameter has a hard min and max it cannot exceed.")
    pdf.bullet("Max 1 adjustment per parameter per run.")
    pdf.bullet("Requires 10+ closed trades before any adjustment activates.")
    pdf.bullet("Every change is logged and sent as a Telegram alert.")
    pdf.bullet(
        "Adjustments are saved to config_overrides.json (a safe JSON file), NOT by modifying "
        "config.py source code. The original config.py values serve as defaults, and the "
        "overrides file cleanly layers changes on top."
    )
    pdf.ln(2)
    pdf.sub_title("5.5 Daily Intelligence Report")
    pdf.body_text(
        "Once per day, the intelligence layer sends a comprehensive Telegram digest:"
    )
    pdf.bullet("Portfolio overview: total open positions, combined P&L.")
    pdf.bullet("Per-bot stats: win rate, P&L, streak, active/paused status.")
    pdf.bullet("Conflict status: any markets where bots disagree.")
    pdf.bullet("Risk status: position count vs limits, drawdown alerts.")
    pdf.bullet("Trends: dominant loss reasons, direction bias, streak info.")
    pdf.bullet("Adjustments: any parameter changes made this cycle.")

    # ── 6. SCHEDULING ────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("6. Run Schedule & Automation")
    pdf.sub_title("Automated Execution")
    pdf.body_text(
        "The system runs automatically every 4 hours via an Anthropic scheduled remote agent. "
        "This is a cloud-based agent that clones the GitHub repo, runs all three scripts, and "
        "pushes the updated trade data back."
    )
    pdf.ln(2)
    pdf.sub_title("Run Sequence (every 4 hours)")
    pdf.code_block(
        "1. pip install requests\n"
        "2. python paper_trades.py    (momentum bot)\n"
        "3. python fade_trades.py     (fade bot)\n"
        "4. python intelligence.py    (intelligence layer)\n"
        "5. git add *.json config.py\n"
        "6. git commit + push to GitHub"
    )
    pdf.ln(2)
    pdf.sub_title("Run Times (UTC)")
    pdf.body_text(
        "The cron schedule is '0 */4 * * *', which means the agent runs at: "
        "00:00, 04:00, 08:00, 12:00, 16:00, and 20:00 UTC every day. That's 6 runs per day."
    )
    pdf.ln(2)
    pdf.sub_title("Data Persistence")
    pdf.body_text(
        "All trade data lives in JSON files that are committed to the GitHub repo after each "
        "run. This means the full history is version-controlled and recoverable. Each trade "
        "file also has a .backup.json copy for corruption recovery."
    )
    pdf.bullet("trades.json / trades.backup.json - Momentum bot trades")
    pdf.bullet("fade_trades.json / fade_trades.backup.json - Fade bot trades")
    pdf.bullet("intelligence_state.json - Intel layer state (last report time, pause flags, loss streaks)")
    pdf.bullet("config_overrides.json - Parameter adjustments from the intelligence layer")

    # ── 7. TELEGRAM ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("7. Telegram Notifications")
    pdf.body_text(
        "Every action sends a labeled Telegram notification so you can monitor from your phone. "
        "Each bot's alerts are clearly tagged:"
    )
    pdf.ln(2)
    pdf.sub_title("[MOMENTUM] Alerts")
    pdf.bullet("New Signal: When the momentum bot enters a new trade. Shows direction, probability, and drift score.")
    pdf.bullet("Trade Closed: When a trade exits. Shows entry/exit prices, P&L, and reason (target, reversal, resolved, stale).")
    pdf.bullet("Run Complete: Summary after each cycle with new/closed counts and performance stats.")
    pdf.ln(2)
    pdf.sub_title("[FADE] Alerts")
    pdf.bullet("Overreaction Detected: When the fade bot spots a spike. Shows spike direction, size, ratio, and fade direction.")
    pdf.bullet("Trade Closed: Same format as momentum but with fade-specific reasons (normalized, stopped_out).")
    pdf.bullet("Run Complete: Fade-specific summary with same performance stats.")
    pdf.ln(2)
    pdf.sub_title("[INTEL] Alerts")
    pdf.bullet("Cross-Bot Conflict: When both bots have opposing positions on the same market.")
    pdf.bullet("Parameters Adjusted: When auto-adjustment changes a threshold (shows old -> new value and reason).")
    pdf.bullet("Daily Intelligence Report: Once-daily comprehensive digest of the entire system.")

    # ── 8. CONFIGURATION ─────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("8. Configuration Reference")
    pdf.body_text("All parameters are in config.py. Here is every tunable setting:")
    pdf.ln(2)
    pdf.sub_title("Market Scanning")
    pdf.param_row("MARKETS_TO_SCAN", 40, "Markets to scan each run")
    pdf.param_row("MIN_POOL", 500, "Min liquidity (YES+NO in Mana)")
    pdf.param_row("MIN_MARKET_AGE_HR", 1, "Skip markets younger than this")
    pdf.ln(2)
    pdf.sub_title("Momentum Detection")
    pdf.param_row("BETS_WINDOW", 30, "Recent bets to analyze per market")
    pdf.param_row("MIN_BETS", 8, "Minimum bets needed for signal")
    pdf.param_row("DECAY_STRENGTH", 2.0, "Time-decay weight (2.0 = 7x newest vs oldest)")
    pdf.ln(2)
    pdf.sub_title("Momentum Signal Filters")
    pdf.param_row("ENTRY_PROB_LOW", 45, "% - below is too uncertain")
    pdf.param_row("ENTRY_PROB_HIGH", 72, "% - above may be crowded")
    pdf.param_row("MIN_DRIFT_SCORE", 2.0, "|drift_score| threshold")
    pdf.param_row("MIN_CONSISTENCY", 65, "% of bets in trend direction")
    pdf.ln(2)
    pdf.sub_title("Momentum Exit Conditions")
    pdf.param_row("EXIT_TARGET_YES", 78, "% - close BUY YES above this")
    pdf.param_row("EXIT_TARGET_NO", 22, "% - close BUY NO below this")
    pdf.param_row("REVERSAL_THRESHOLD", 6, "pp stop-loss against entry")
    pdf.param_row("MAX_TRADE_DAYS", 14, "Auto-close after this many days")

    pdf.add_page()
    pdf.sub_title("Spike Detection (Fade Bot)")
    pdf.param_row("SPIKE_BETS_TOTAL", 20, "Total bets to fetch per market")
    pdf.param_row("SPIKE_RECENT", 5, "Last N bets = spike window")
    pdf.param_row("SPIKE_MIN_BETS", 12, "Min bets needed (recent + baseline)")
    pdf.param_row("SPIKE_MIN_SIZE", 8, "pp - minimum spike size")
    pdf.param_row("SPIKE_MIN_RATIO", 3.0, "Spike must be Nx baseline moves")
    pdf.param_row("MAX_CONSISTENCY", 50, "% - reject if too consistent (it's a trend)")
    pdf.param_row("SPIKE_MAX_WINDOW_HR", 6, "Max hours for spike window (rejects slow moves)")
    pdf.ln(2)
    pdf.sub_title("Fade Exit Conditions")
    pdf.param_row("FADE_NORMALIZE_PCT", 50, "% of spike to retrace for a win")
    pdf.param_row("FADE_STOP_PP", 8, "pp stop-loss if spike continues")
    pdf.param_row("FADE_MAX_DAYS", 7, "Fade trades expire faster")
    pdf.param_row("FADE_MIN_REWARD_RATIO", 0.8, "Min reward/risk ratio to enter trade")
    pdf.ln(2)
    pdf.sub_title("Intelligence Layer")
    pdf.param_row("INTEL_MAX_OPEN_TOTAL", 8, "Max open trades across both bots")
    pdf.param_row("INTEL_MAX_OPEN_PER_BOT", 5, "Max open trades per bot")
    pdf.param_row("INTEL_DRAWDOWN_LIMIT_PP", -50, "Pause alert threshold (7-day)")
    pdf.param_row("INTEL_PAUSE_AFTER_LOSSES", 4, "Pause bot after N consecutive losses")
    pdf.param_row("INTEL_MAX_PAUSE_DAYS", 3, "Auto-unpause after N days (deadlock fix)")
    pdf.param_row("INTEL_LOOKBACK_TRADES", 10, "Recent trades for adjustment decisions")

    # ── 9. FILE REFERENCE ────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("9. File Reference")
    pdf.ln(2)
    pdf.sub_title("Python Modules")
    pdf.bullet("config.py - All tunable parameters in one place.")
    pdf.bullet("detect_momentum.py - Market fetching + momentum scoring (shared).")
    pdf.bullet("detect_spike.py - Spike detection for the fade bot.")
    pdf.bullet("paper_trades.py - Momentum bot: signal scanning, trade logging, exits.")
    pdf.bullet("fade_trades.py - Fade bot: spike scanning, fade trades, exits.")
    pdf.bullet("intelligence.py - Intelligence layer: conflicts, risk, adjustments, reports.")
    pdf.bullet("notify.py - All Telegram notification functions.")
    pdf.ln(2)
    pdf.sub_title("Data Files (auto-updated each run)")
    pdf.bullet("trades.json - Momentum bot trade log (open + closed trades).")
    pdf.bullet("trades.backup.json - Backup copy of momentum trades.")
    pdf.bullet("fade_trades.json - Fade bot trade log.")
    pdf.bullet("fade_trades.backup.json - Backup copy of fade trades.")
    pdf.bullet("intelligence_state.json - Intel layer state (last report time, pauses, loss streaks).")
    pdf.bullet("config_overrides.json - Parameter overrides from auto-adjustment (loaded by config.py).")
    pdf.ln(2)
    pdf.sub_title("Other Files")
    pdf.bullet("requirements.txt - Python dependencies (just 'requests').")
    pdf.bullet(".gitignore - Excludes __pycache__, .env, *.tmp, .claude/")
    pdf.bullet("generate_docs.py - Generates this PDF documentation.")
    pdf.bullet("Prediction_Market_Trading_System.pdf - This document.")
    pdf.bullet("fetch_markets.py - Original market fetching demo (standalone).")
    pdf.bullet("find_signals.py - Original signal detection demo (standalone).")

    # ── 10. GLOSSARY ─────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("10. Key Concepts & Glossary")
    pdf.ln(2)
    terms = [
        ("pp (probability points)",
         "The unit of measurement. 1pp = 1 percentage point of probability. "
         "A trade that enters at 55% and exits at 67% made +12pp."),
        ("Drift",
         "The total weighted probability change across recent bets. Positive drift = "
         "price trending up. Negative = trending down."),
        ("Consistency",
         "What % of individual bet steps moved in the same direction as the overall "
         "drift. 80% consistency means 4 out of 5 steps agreed."),
        ("Drift Score",
         "drift x consistency. The combined signal strength for the momentum bot. "
         "Higher = stronger and more reliable trend."),
        ("Spike",
         "A sudden, abnormally large price movement in a short window of bets. "
         "Measured by spike_size (pp) and spike_ratio (vs normal)."),
        ("Spike Ratio",
         "How many times larger the recent move is compared to normal bet-to-bet movement. "
         "A ratio of 5.0 means the spike was 5x bigger than usual."),
        ("Fade",
         "To bet against something. 'Fading a spike' = betting the spike will revert."),
        ("Normalization",
         "When a spiked price reverts back toward its pre-spike level. The fade bot's "
         "win condition."),
        ("Stopped Out",
         "When the price keeps moving against your position past the stop-loss threshold. "
         "An automatic loss exit."),
        ("Reversal",
         "When the market moves against a momentum trade by more than REVERSAL_THRESHOLD pp."),
        ("Resolution",
         "When a prediction market closes and pays out. Resolves to YES (100%) or NO (0%)."),
        ("Paper Trading",
         "Recording hypothetical trades without real money. Used to test strategy "
         "performance before going live."),
        ("Net P&L (7-day)",
         "The sum of ALL realized profits and losses over the last 7 days. "
         "Used as the primary risk metric. If it drops below -50pp, a warning is triggered."),
        ("Risk-Reward Ratio",
         "Expected reward divided by expected risk for a trade. A ratio of 1.0 means "
         "you risk the same as you could win. Below 0.8 is rejected by the fade bot."),
        ("Conflict",
         "When both bots have opposing open positions on the same market. "
         "The intelligence layer detects and prevents these."),
        ("Config Overrides",
         "A JSON file (config_overrides.json) where the intelligence layer writes "
         "parameter adjustments. Loaded by config.py at startup, layering changes on "
         "top of the default values without modifying source code."),
    ]
    for term, definition in terms:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(20, 60, 120)
        pdf.cell(0, 6, term)
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.set_x(15)
        pdf.multi_cell(180, 5.5, definition)
        pdf.ln(3)

    # ── SAVE ─────────────────────────────────────────────────────────────────
    path = "Prediction_Market_Trading_System.pdf"
    pdf.output(path)
    print(f"PDF saved to: {path}")


if __name__ == "__main__":
    build_pdf()
