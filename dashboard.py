"""
dashboard.py — Turn journal/trades.csv into a single, openable dashboard.html.

Run it after any session:

    python dashboard.py
    python dashboard.py --journal journal/trades.csv --out dashboard.html

Then double-click dashboard.html. It opens straight from disk — the trade data is
baked INTO the page, so there's no server to run and no file-permission/CORS mess.
(It pulls only the Chart.js drawing library from a public CDN, so you need to be
online the first time you open it. Nothing else leaves your machine.)

What you'll see:
  - headline cards: trades, win rate, fees paid, realized P&L, net result
  - equity over time (the logged balance after each event)
  - cumulative fees vs cumulative realized P&L (watch fees eat returns)
  - settled wins vs losses

Honest note: "win rate" and "realized P&L" are computed only from SETTLE rows —
i.e. bets whose markets actually resolved. Open positions aren't counted as wins
or losses, because they haven't happened yet.
"""

import argparse
import csv
import json
import os

import config


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_series(rows):
    """Crunch the journal into the arrays the charts need."""
    equity_points = []          # logged equity/balance after each event
    cum_fees_points = []        # cumulative fees over events
    cum_realized_points = []    # cumulative realized P&L over events

    cum_fees = 0.0
    cum_realized = 0.0
    trades = 0
    wins = 0
    losses = 0
    arbs = 0

    for i, r in enumerate(rows):
        action = r.get("action", "")
        cum_fees += _f(r.get("fee"))
        if action in ("BUY", "COPY_BUY"):
            trades += 1
        elif action == "SETTLE":
            cum_realized += _f(r.get("size_usd"))   # size_usd holds the pnl here
            if "WON" in (r.get("reason") or ""):
                wins += 1
            elif "LOST" in (r.get("reason") or ""):
                losses += 1
        elif action == "ARB_DETECTED":
            arbs += 1

        eq = r.get("equity_after")
        if eq not in (None, ""):
            equity_points.append({"x": i + 1, "y": round(_f(eq), 2)})
        cum_fees_points.append({"x": i + 1, "y": round(cum_fees, 2)})
        cum_realized_points.append({"x": i + 1, "y": round(cum_realized, 2)})

    total_settled = wins + losses
    win_rate = round(wins / total_settled * 100, 1) if total_settled else 0.0
    start = config.STARTING_BALANCE_USD
    final_equity = equity_points[-1]["y"] if equity_points else start

    return {
        "equity": equity_points,
        "cum_fees": cum_fees_points,
        "cum_realized": cum_realized_points,
        "metrics": {
            "trades": trades,
            "arbs_detected": arbs,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "fees": round(cum_fees, 2),
            "realized": round(cum_realized, 2),
            "net": round(cum_realized - cum_fees, 2),
            "start": round(start, 2),
            "final_equity": round(final_equity, 2),
            "events": len(rows),
        },
    }


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paper Sandbox — Results</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         background:#0f1216; color:#e6e9ef; margin:0; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:#8b93a7; font-size:13px; margin-bottom:20px; }
  .cards { display:flex; flex-wrap:wrap; gap:12px; margin-bottom:24px; }
  .card { background:#171c24; border:1px solid #232a35; border-radius:10px;
          padding:14px 16px; min-width:120px; flex:1; }
  .card .label { color:#8b93a7; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  .card .value { font-size:22px; font-weight:600; margin-top:4px; }
  .pos { color:#46d39a; } .neg { color:#ff6b6b; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  .panel { background:#171c24; border:1px solid #232a35; border-radius:10px; padding:16px; }
  .panel h2 { font-size:13px; color:#c3c9d6; margin:0 0 12px; font-weight:600; }
  .full { grid-column:1 / -1; }
  .note { color:#8b93a7; font-size:12px; margin-top:18px; line-height:1.5; }
  @media (max-width:760px){ .grid{ grid-template-columns:1fr; } }
</style></head>
<body>
  <h1>Polymarket Paper Sandbox — Results</h1>
  <div class="sub">All amounts are virtual. Generated from journal/trades.csv. Paper results are not a promise of real results.</div>
  <div class="cards" id="cards"></div>
  <div class="grid">
    <div class="panel full"><h2>Equity over time (logged balance after each event)</h2><canvas id="equity"></canvas></div>
    <div class="panel"><h2>Cumulative fees vs realized P&amp;L</h2><canvas id="fees"></canvas></div>
    <div class="panel"><h2>Settled bets: wins vs losses</h2><canvas id="winloss"></canvas></div>
  </div>
  <div class="note" id="note"></div>
<script>
const DATA = __DATA__;
const m = DATA.metrics;
const money = v => (v<0?"-$":"$") + Math.abs(v).toFixed(2);
const cls = v => v>=0 ? "pos" : "neg";

document.getElementById("cards").innerHTML = [
  ["Trades", m.trades],
  ["Settled W / L", m.wins + " / " + m.losses],
  ["Win rate", m.win_rate + "%"],
  ["Fees paid", '<span class="neg">' + money(m.fees) + '</span>'],
  ["Realized P&L", '<span class="'+cls(m.realized)+'">' + money(m.realized) + '</span>'],
  ["Net (P&L - fees)", '<span class="'+cls(m.net)+'">' + money(m.net) + '</span>'],
  ["Final equity", money(m.final_equity)],
].map(([l,v]) => '<div class="card"><div class="label">'+l+'</div><div class="value">'+v+'</div></div>').join("");

const grid = {grid:{color:"#222a35"}, ticks:{color:"#8b93a7"}};
const noPts = {pointRadius:0, borderWidth:2, tension:0.15};

if (DATA.equity.length) new Chart(document.getElementById("equity"), {
  type:"line",
  data:{ datasets:[{ label:"Equity", data:DATA.equity, borderColor:"#5b9bff",
    backgroundColor:"rgba(91,155,255,.12)", fill:true, ...noPts }]},
  options:{ plugins:{legend:{display:false}}, parsing:false,
    scales:{ x:{type:"linear", title:{display:true,text:"event #",color:"#8b93a7"}, ...grid},
             y:{title:{display:true,text:"USD",color:"#8b93a7"}, ...grid} } }
});

new Chart(document.getElementById("fees"), {
  type:"line",
  data:{ datasets:[
    { label:"Cumulative fees", data:DATA.cum_fees, borderColor:"#ff6b6b", ...noPts },
    { label:"Cumulative realized P&L", data:DATA.cum_realized, borderColor:"#46d39a", ...noPts } ]},
  options:{ plugins:{legend:{labels:{color:"#c3c9d6"}}}, parsing:false,
    scales:{ x:{type:"linear", ...grid}, y:{...grid} } }
});

new Chart(document.getElementById("winloss"), {
  type:"bar",
  data:{ labels:["Wins","Losses"], datasets:[{ data:[m.wins, m.losses],
    backgroundColor:["#46d39a","#ff6b6b"] }]},
  options:{ plugins:{legend:{display:false}}, scales:{ x:{...grid}, y:{...grid, beginAtZero:true} } }
});

document.getElementById("note").innerHTML =
  "Win rate and realized P&L count only SETTLE rows (markets that actually resolved): "
  + m.wins + " wins, " + m.losses + " losses out of " + m.events + " logged events. "
  + (m.arbs_detected ? (m.arbs_detected + " sum-to-one arbitrage opportunities were detected (and almost never real after fees). ") : "")
  + "Open positions are not yet counted — they haven't happened. Fees are the house's cut and accrue on every entry.";
</script>
</body></html>
"""


def main():
    p = argparse.ArgumentParser(description="Build a dashboard.html from the trade journal")
    p.add_argument("--journal", default=config.JOURNAL_CSV)
    p.add_argument("--out", default="dashboard.html")
    args = p.parse_args()

    rows = load_rows(args.journal)
    if not rows:
        print(f"No trades found in {args.journal}. Run the bot first (e.g. python bot.py --backtest 50).")
        return

    data = build_series(rows)
    html = HTML.replace("__DATA__", json.dumps(data))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    mtr = data["metrics"]
    print(f"Wrote {args.out} from {mtr['events']} journal events.")
    print(f"  trades={mtr['trades']}  settled={mtr['wins']}W/{mtr['losses']}L  "
          f"win_rate={mtr['win_rate']}%  fees=${mtr['fees']}  realized=${mtr['realized']}  net=${mtr['net']}")
    print(f"Open {args.out} in your browser to view the charts.")


if __name__ == "__main__":
    main()
