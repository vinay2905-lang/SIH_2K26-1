// Small SVG charts. One axis, thin marks, hairline grid, legends and selective direct labels.

export function LineChart({ series, labels, height = 190 }: {
  series: { name: string; color: string; values: number[] }[];
  labels: string[];
  height?: number;
}) {
  const w = 560, padL = 34, padR = 110, padT = 10, padB = 24;
  const iw = w - padL - padR, ih = height - padT - padB;
  const max = Math.max(4, ...series.flatMap((s) => s.values));
  const top = Math.ceil(max / 4) * 4;
  const ticks = [0, top / 4, top / 2, (3 * top) / 4, top];
  const x = (i: number) => padL + (i * iw) / Math.max(1, labels.length - 1);
  const y = (v: number) => padT + ih - (v / top) * ih;
  const ends = series.map((s) => ({ s, v: s.values[s.values.length - 1] ?? 0 }));
  // keep end labels apart
  const placed = ends.map((e) => ({ ...e, ly: y(e.v) }));
  placed.sort((a, b) => a.ly - b.ly);
  for (let i = 1; i < placed.length; i++) if (placed[i].ly - placed[i - 1].ly < 14) placed[i].ly = placed[i - 1].ly + 14;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" role="img" aria-label={series.map((s) => s.name).join(" and ") + " per day"}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={padL} x2={padL + iw} y1={y(t)} y2={y(t)} stroke={t === 0 ? "#C9D1DB" : "#E9EDF2"} />
          <text x={padL - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#8A94A2" style={{ fontVariantNumeric: "tabular-nums" }}>{t}</text>
        </g>
      ))}
      {labels.map((l, i) => (i % 2 === 0 && i < labels.length - 2) || i === labels.length - 1 ? (
        <text key={i} x={x(i)} y={height - 6} textAnchor="middle" fontSize="11" fill="#8A94A2">{l}</text>
      ) : null)}
      {series.map((s) => (
        <g key={s.name}>
          <polyline points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {s.values.map((v, i) => (
            <circle key={i} cx={x(i)} cy={y(v)} r="9" fill="transparent"><title>{`${labels[i]}: ${v} ${s.name.toLowerCase()}`}</title></circle>
          ))}
          <circle cx={x(s.values.length - 1)} cy={y(s.values[s.values.length - 1] ?? 0)} r="4" fill={s.color} stroke="#fff" strokeWidth="2" />
        </g>
      ))}
      {placed.map(({ s, v, ly }) => (
        <g key={s.name}>
          <line x1={x(labels.length - 1) + 10} x2={x(labels.length - 1) + 22} y1={ly} y2={ly} stroke={s.color} strokeWidth="2" strokeLinecap="round" />
          <text x={x(labels.length - 1) + 27} y={ly + 4} fontSize="11" fill="#3A4555"><tspan fontWeight="600" fill="#17202B">{v}</tspan> {s.name.toLowerCase()}</text>
        </g>
      ))}
    </svg>
  );
}

export function HBars({ rows, color = "#2a78d6" }: { rows: [string, number][]; color?: string }) {
  const w = 420, labelW = 160, valW = 46, bw = w - labelW - valW, bh = 14, gap = 16;
  const max = Math.max(1, ...rows.map((r) => r[1]));
  const h = Math.max(1, rows.length) * (bh + gap);
  if (!rows.length) return <div className="empty">Nothing open</div>;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="Open findings by category">
      <line x1={labelW} x2={labelW} y1={0} y2={h - gap + 4} stroke="#C9D1DB" />
      {rows.map(([l, v], i) => {
        const y = i * (bh + gap) + 2, len = Math.max(6, (v / max) * bw), r = 4;
        return (
          <g key={l}>
            <text x={labelW - 10} y={y + bh - 2.5} textAnchor="end" fontSize="12" fill="#3A4555">{l}</text>
            <path d={`M${labelW} ${y} h${len - r} a${r} ${r} 0 0 1 ${r} ${r} v${bh - 2 * r} a${r} ${r} 0 0 1 -${r} ${r} h-${len - r} z`} fill={color}>
              <title>{`${l}: ${v}`}</title>
            </path>
            <text x={labelW + len + 8} y={y + bh - 2.5} fontSize="12" fontWeight="600" fill="#17202B" style={{ fontVariantNumeric: "tabular-nums" }}>{v}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function Meter({ value, max = 100, tone }: { value: number; max?: number; tone?: "red" }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={`meter${tone === "red" ? " red" : ""}`} role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
      <i style={{ width: `${Math.max(pct, value > 0 ? 2 : 0)}%` }} />
    </div>
  );
}
