#!/usr/bin/env python3
"""Render a dependency-free SVG with request result and chaos deletion events."""
import csv
from pathlib import Path
from html import escape
ROOT = Path(__file__).resolve().parent.parent / 'results'
rows = list(csv.DictReader((ROOT/'availability.csv').open()))
if not rows:
    raise SystemExit('No observations in availability.csv')
events = list(csv.DictReader((ROOT/'chaos.csv').open())) if (ROOT/'chaos.csv').exists() else []
t0=min(int(x['timestamp']) for x in rows)
t1=max(int(x['timestamp']) for x in rows)
span=max(1,t1-t0)
w,h=1100,380
left,right,top,bottom=65,30,45,75
pw=w-left-right
lines=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="1100" height="380">',
       '<rect width="100%" height="100%" fill="white"/>',
       '<text x="65" y="27" font-family="sans-serif" font-size="18" fill="#17202a">Shop availability under pod deletion</text>']
axis=h-bottom
lines.append(f'<line x1="{left}" y1="{axis}" x2="{w-right}" y2="{axis}" stroke="#999"/>')
lines.append(f'<text x="{left}" y="{h-20}" font-size="12" font-family="sans-serif">Elapsed seconds from start (each point = one request)</text>')
for ev in events:
    ts=int(ev['timestamp'])
    if t0<=ts<=t1:
        x=left+pw*(ts-t0)/span
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{axis}" stroke="#f5a24b" stroke-opacity=".65" stroke-width="1.3"/>')
for r in rows:
    x=left+pw*(int(r['timestamp'])-t0)/span
    ok=int(r['success'])
    y=top+90 if ok else top+225
    color='#177e67' if ok else '#c73733'
    lines.append(f'<circle cx="{x:.2f}" cy="{y}" r="2.6" fill="{color}"/>')
for label,y,color in [('Success',top+90,'#177e67'),('Failure',top+225,'#c73733')]:
    lines.append(f'<text x="6" y="{y+4}" font-family="sans-serif" font-size="13" fill="{color}">{label}</text>')
lines += ['<rect x="770" y="25" width="14" height="6" fill="#f5a24b"/>', '<text x="790" y="32" font-family="sans-serif" font-size="12">Pod deleted</text>']
success=sum(int(r['success']) for r in rows)
lines.append(f'<text x="65" y="365" font-family="sans-serif" font-size="12">Requests {len(rows)}, OK {success}, failed {len(rows)-success}; deletions in range {sum(t0<=int(e["timestamp"])<=t1 for e in events)}</text>')
lines.append('</svg>')
out=ROOT/'availability.svg'
out.write_text('\n'.join(lines),encoding='utf-8')
print(out)
