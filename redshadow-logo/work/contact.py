import base64, sys
names = sys.argv[1:] or ["a-redacted","b-scanline","c-weight","d-cast","e-eclipse"]
def u(n): return "data:image/svg+xml;base64,"+base64.b64encode(open(f"concepts/{n}.svg","rb").read()).decode()
rows=[]
for n in names:
    rows.append(f'''<div class=row><div class=c style="background:#fff"><img src="{u(n)}" style="height:70px"></div>
<div class=c style="background:#0a0a0b"><img src="{u(n+'-reversed')}" style="height:46px"></div>
<div class=c style="background:#fff"><img src="{u(n+'-mono')}" style="height:22px"> <img src="{u(n)}" style="height:14px"></div>
<div class=c style="background:#fff"><img src="{u(n+'-icon')}" style="height:64px"><img src="{u(n+'-icon')}" style="height:32px"><img src="{u(n+'-icon')}" style="height:16px"><img src="{u(n+'-icon-reversed')}" style="height:32px"></div></div>''')
open("work/contact.html","w").write("<html><body style='margin:0;background:#ddd;font-family:sans-serif'><style>.row{display:flex;flex-wrap:wrap;gap:6px;margin:6px}.c{padding:12px;display:flex;align-items:center;gap:12px}</style>"+"".join(rows)+"</body></html>")
