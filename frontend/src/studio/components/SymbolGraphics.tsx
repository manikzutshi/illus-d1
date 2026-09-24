import React from 'react';
import { svgTransform, transformPoint, uprightAnchor, VEC } from '../geometry';
import type { Orient, SymbolDef, SymbolPrimitive } from '../types';

export function Primitive({ p, stroke }: { p: SymbolPrimitive; stroke: string }) {
  const fill = p.fill === 'body' ? 'var(--sym-body)' : p.fill === 'outline' ? stroke : 'none';
  const common = { stroke, strokeWidth: p.width, fill, strokeLinejoin: 'round' as const, strokeLinecap: 'round' as const };
  switch (p.kind) {
    case 'line':
      return <line x1={p.points[0][0]} y1={p.points[0][1]} x2={p.points[1][0]} y2={p.points[1][1]} {...common} />;
    case 'polyline':
      return <polyline points={p.points.map(q => q.join(',')).join(' ')} {...common} />;
    case 'polygon':
      return <polygon points={p.points.map(q => q.join(',')).join(' ')} {...common} />;
    case 'rect':
      return <rect x={p.x} y={p.y} width={p.w} height={p.h} {...common} />;
    case 'circle':
      return <circle cx={p.x} cy={p.y} r={p.r} {...common} />;
    case 'path':
      return <path d={p.d} {...common} />;
    default:
      return null;
  }
}

/** Symbol body graphics + upright internal text for a placed instance. */
export function SymbolBody({ symbol, x, y, rotation, mirror, stroke, textColor }: {
  symbol: SymbolDef; x: number; y: number; rotation: number; mirror: boolean; stroke: string; textColor: string;
}) {
  const shapes = symbol.graphics.filter(g => g.kind !== 'text');
  const texts = symbol.graphics.filter(g => g.kind === 'text');
  return (
    <>
      <g transform={svgTransform(x, y, rotation, mirror)}>
        {shapes.map((g, i) => <Primitive key={i} p={g} stroke={stroke} />)}
      </g>
      {texts.map((t, i) => {
        const [tx, ty] = transformPoint(t.x, t.y, x, y, rotation, mirror);
        return (
          <text key={`t${i}`} x={tx} y={ty} fontSize={t.size} textAnchor={uprightAnchor(t.anchor, rotation, mirror)}
                fill={textColor} className="sym-text">{t.text}</text>
        );
      })}
    </>
  );
}

/** Pin stubs of a symbol in its own coordinates (used for thumbnails). */
export function SymbolPins({ symbol, stroke }: { symbol: SymbolDef; stroke: string }) {
  return (
    <>
      {symbol.pins.filter(p => !p.hidden && p.length > 0).map(p => {
        const [vx, vy] = VEC[p.orientation as Orient];
        return <line key={p.name} x1={p.x} y1={p.y} x2={p.x - vx * p.length} y2={p.y - vy * p.length} stroke={stroke} strokeWidth={0.15} />;
      })}
    </>
  );
}

/** Small standalone preview of a library symbol. */
export function SymbolThumbnail({ symbol, size = 56 }: { symbol: SymbolDef; size?: number }) {
  const xs = [symbol.body[0], symbol.body[2], ...symbol.pins.filter(p => !p.hidden).map(p => p.x)];
  const ys = [symbol.body[1], symbol.body[3], ...symbol.pins.filter(p => !p.hidden).map(p => p.y)];
  const x0 = Math.min(...xs) - 1, x1 = Math.max(...xs) + 1, y0 = Math.min(...ys) - 1, y1 = Math.max(...ys) + 1;
  const w = x1 - x0, h = y1 - y0, s = Math.max(w, h);
  return (
    <svg width={size} height={size} viewBox={`${x0 - (s - w) / 2} ${y0 - (s - h) / 2} ${s} ${s}`} className="thumb">
      <SymbolBody symbol={{ ...symbol, graphics: symbol.graphics.filter(g => g.kind !== 'text' || s < 14) }}
                  x={0} y={0} rotation={0} mirror={false} stroke="var(--sym-stroke)" textColor="var(--sym-stroke)" />
      <SymbolPins symbol={symbol} stroke="var(--sym-stroke)" />
    </svg>
  );
}

export function PowerPortShape({ kind, x, y, direction, text, color }: {
  kind: 'power' | 'ground'; x: number; y: number; direction: Orient; text: string; color: string;
}) {
  const [vx, vy] = VEC[direction];
  const ux = Math.abs(vy), uy = Math.abs(vx);
  const ax = x + vx, ay = y + vy;
  const parts: React.ReactNode[] = [<line key="stem" x1={x} y1={y} x2={ax} y2={ay} stroke={color} strokeWidth={0.15} />];
  let tx: number, ty: number;
  if (kind === 'power') {
    parts.push(<line key="bar" x1={ax - ux} y1={ay - uy} x2={ax + ux} y2={ay + uy} stroke={color} strokeWidth={0.22} />);
    tx = x + vx * 2.9; ty = y + vy * 2.9;
  } else {
    ([[0, 1.2], [0.45, 0.75], [0.9, 0.3]] as const).forEach(([k, half], i) => {
      const bx = ax + vx * k, by = ay + vy * k;
      parts.push(<line key={`g${i}`} x1={bx - ux * half} y1={by - uy * half} x2={bx + ux * half} y2={by + uy * half} stroke={color} strokeWidth={0.2} />);
    });
    tx = x + vx * 3.2; ty = y + vy * 3.2;
  }
  if (kind === 'power' || text !== 'GND') {
    const anchor = vx === 0 ? 'middle' : vx > 0 ? 'start' : 'end';
    parts.push(<text key="t" x={tx} y={ty + (vy >= 0 ? 0.35 : 0) + (vx ? 0.4 : 0)} fontSize={0.95} textAnchor={anchor}
                     fill={color} fontWeight={600}>{text}</text>);
  }
  return <>{parts}</>;
}

export function NetLabelShape({ x, y, direction, text, color }: { x: number; y: number; direction: Orient; text: string; color: string }) {
  const [vx, vy] = VEC[direction];
  const length = 0.62 * Math.max(text.length, 1) + 1.2;
  if (vx) {
    const xa = x, xb = x + vx * length;
    const pts = [[xa, y], [xa + vx * 0.6, y - 0.6], [xb, y - 0.6], [xb, y + 0.6], [xa + vx * 0.6, y + 0.6]];
    return (
      <>
        <polygon points={pts.map(p => p.join(',')).join(' ')} fill="var(--label-bg)" stroke={color} strokeWidth={0.1} />
        <text x={(xa + xb) / 2 + vx * 0.3} y={y + 0.35} fontSize={0.9} textAnchor="middle" fill={color}>{text}</text>
      </>
    );
  }
  const yb = y + vy * 1.2;
  return (
    <>
      <line x1={x} y1={y} x2={x} y2={yb} stroke={color} strokeWidth={0.12} />
      <text x={x} y={yb + (vy > 0 ? 0.9 : -0.3)} fontSize={0.9} textAnchor="middle" fill={color}>{text}</text>
    </>
  );
}
