"""Build the RedShadow concept board (HTML) from concepts/*.svg. Screenshot it to PNG with Chrome."""
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "concepts")

CONCEPTS = [
    ("a-redacted", "A", "Redacted", "RED is knocked out of a hard redaction bar — the finding, blacked out until it's fixed.", True),
    ("b-scanline", "B", "Scanline", "One horizontal cut runs through every letter, like a scanner pass across the target.", False),
    ("c-weight", "C", "Weight Shift", "RED is the heavy, solid attacker; SHADOW is its light trace.", False),
    ("d-cast", "D", "Cast", "Only the S throws a hard, flat 45° shadow — one ownable letter.", False),
    ("e-eclipse", "E", "Eclipse", "The O's counter is half in shadow: a 45° terminator inside the target.", False),
]


def uri(name):
    with open(os.path.join(C, name + ".svg"), "rb") as f:
        return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()


def card(slug, letter, name, idea, rec):
    tag = '<span class="rec">Recommended</span>' if rec else ""
    return f"""
<section class="card{' is-rec' if rec else ''}">
  <header><span class="id">{letter}</span><h2>{name}</h2>{tag}</header>
  <p class="idea">{idea}</p>
  <div class="grid">
    <div class="cell paper big"><img src="{uri(slug)}" style="height:74px"></div>
    <div class="cell ink big"><img src="{uri(slug + '-reversed')}" style="height:74px"></div>
    <div class="cell paper small">
      <div><img src="{uri(slug + '-mono')}" style="height:32px"><label>one colour</label></div>
      <div><img src="{uri(slug)}" style="height:16px"><label>16 px</label></div>
    </div>
    <div class="cell paper icons">
      <img src="{uri(slug + '-icon')}" style="height:64px">
      <img src="{uri(slug + '-icon')}" style="height:32px">
      <img src="{uri(slug + '-icon')}" style="height:16px">
      <span class="sep"></span>
      <img src="{uri(slug + '-icon-reversed')}" style="height:32px">
      <img src="{uri(slug + '-icon-mono')}" style="height:32px">
      <label>icon · 64 / 32 / 16 · reversed · mono</label>
    </div>
  </div>
</section>"""


html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
:root {{ --red:#ff2a1a; --ink:#0a0a0b; --paper:#f1efe8; --line:#d6d3c9; --mute:#6d6a63; }}
* {{ box-sizing:border-box; margin:0; }}
body {{ background:var(--paper); color:var(--ink); width:1800px; padding:56px 64px 64px;
       font:14px/1.45 "Helvetica Neue", Helvetica, Arial, sans-serif; }}
.top {{ display:flex; justify-content:space-between; align-items:flex-end; border-bottom:2px solid var(--ink);
        padding-bottom:18px; margin-bottom:28px; }}
.top h1 {{ font-size:30px; letter-spacing:-0.01em; }}
.top .meta {{ font:12px/1.6 ui-monospace, Menlo, monospace; color:var(--mute); text-align:right; }}
.sw {{ display:inline-block; width:12px; height:12px; vertical-align:-1px; margin:0 4px 0 12px; border:1px solid var(--line); }}
.cards {{ display:grid; grid-template-columns:1fr; gap:18px; }}
.card {{ border:1px solid var(--line); background:#fff; padding:20px 22px 22px; }}
.card.is-rec {{ border:2px solid var(--red); }}
.card header {{ display:flex; align-items:center; gap:12px; }}
.id {{ font:600 12px ui-monospace, Menlo, monospace; border:1.5px solid var(--ink); width:24px; height:24px;
       display:grid; place-items:center; }}
.card h2 {{ font-size:18px; }}
.rec {{ font:600 11px ui-monospace, Menlo, monospace; text-transform:uppercase; letter-spacing:.08em;
        color:#fff; background:var(--red); padding:3px 8px; }}
.idea {{ color:var(--mute); margin:6px 0 14px 36px; }}
.grid {{ display:grid; grid-template-columns:1.25fr 1.25fr .8fr 1fr; gap:10px; }}
.cell {{ min-height:130px; display:flex; align-items:center; justify-content:center; gap:14px; position:relative;
         border:1px solid var(--line); }}
.paper {{ background:var(--paper); }} .ink {{ background:var(--ink); border-color:var(--ink); }}
.small {{ flex-direction:column; gap:18px; }}
.small div {{ display:flex; flex-direction:column; align-items:center; gap:4px; }}
.icons {{ padding-bottom:18px; }}
.icons .sep {{ width:1px; height:40px; background:var(--line); }}
label {{ font:10px ui-monospace, Menlo, monospace; color:var(--mute); text-transform:uppercase; letter-spacing:.06em; }}
.icons label {{ position:absolute; bottom:6px; }}
.foot {{ margin-top:22px; font:12px ui-monospace, Menlo, monospace; color:var(--mute); display:flex; justify-content:space-between; }}
</style></head><body>
<div class="top">
  <div><h1>RedShadow — wordmark concepts</h1>
  <p style="color:var(--mute);margin-top:4px">Pentest management &amp; remediation · round 1 · custom squared-geometric capitals, all outlines</p></div>
  <div class="meta">RED<span class="sw" style="background:#ff2a1a"></span>#FF2A1A &nbsp; INK<span class="sw" style="background:#0a0a0b"></span>#0A0A0B &nbsp; PAPER<span class="sw" style="background:#f1efe8"></span>#F1EFE8<br>
  cap height 100u · stem 20u · bar 17u · diagonals 15°</div>
</div>
<div class="cards">{''.join(card(*c) for c in CONCEPTS)}</div>
<div class="foot"><span>Each row: colour on paper · reversed on ink · one colour + true 16 px · icon at 64/32/16, reversed, mono</span><span>redshadow-logo/concepts/</span></div>
</body></html>"""

os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
with open(os.path.join(ROOT, "work", "board.html"), "w") as f:
    f.write(html)
print("wrote work/board.html")
