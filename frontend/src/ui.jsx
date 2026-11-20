// Shared UI building blocks. Libraries picked from Emil Kowalski's curated list
// (pick-ui-library skill): Sonner (toasts), Vaul (drawers), cmdk (command menu),
// NumberFlow (animated numbers), Base UI (accessible primitives), motion (springs),
// plus canvas-confetti (the engine behind Magic UI's confetti).
// Everything is styled with our own neon-bar tokens in styles.css (no Tailwind),
// following shadcn's idea: own the component code, build on headless primitives.
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Drawer } from 'vaul'
import NumberFlow from '@number-flow/react'
import { Switch } from '@base-ui/react/switch'
import { Toggle } from '@base-ui/react/toggle'
import { ToggleGroup } from '@base-ui/react/toggle-group'
import confetti from 'canvas-confetti'
import clsx from 'clsx'

export { toast, clsx }

// ---------------------------------------------------------------- Vaul
// Bottom sheet: swipe down to dismiss, iOS-like easing, focus trapped.
export function Sheet({ open, onOpenChange, title, description, children, tone = 'pink' }) {
  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange} repositionInputs={false}>
      <Drawer.Portal>
        <Drawer.Overlay className="vaul-overlay" />
        <Drawer.Content className={clsx('vaul-sheet', `tone-${tone}`)} aria-describedby={undefined}>
          <Drawer.Handle className="vaul-handle" />
          <div className="vaul-body">
            <Drawer.Title className="vaul-title">{title}</Drawer.Title>
            {description && <Drawer.Description className="hint">{description}</Drawer.Description>}
            {children}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}

// ---------------------------------------------------------------- NumberFlow
export function Num({ value, prefix, className, plus = false }) {
  const v = Number(value) || 0
  return (
    <NumberFlow
      value={v}
      className={className}
      prefix={prefix}
      format={plus ? { signDisplay: 'exceptZero' } : undefined}
      transformTiming={{ duration: 650, easing: 'cubic-bezier(0.23, 1, 0.32, 1)' }}
      spinTiming={{ duration: 650, easing: 'cubic-bezier(0.23, 1, 0.32, 1)' }}
      willChange
    />
  )
}

// Counts up from 0 on mount (e.g. "+974" on the result screen).
export function CountUp({ value, plus = false, className }) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const id = setTimeout(() => setV(value), 120)
    return () => clearTimeout(id)
  }, [value])
  return <Num value={v} plus={plus} className={className} />
}

// ---------------------------------------------------------------- Base UI
// Single-choice segmented control (roast level, wager %, question type, mascot).
export function Segmented({ value, onChange, options, label, className, columns }) {
  return (
    <ToggleGroup
      aria-label={label}
      value={value == null ? [] : [String(value)]}
      onValueChange={(vals) => {
        if (!vals.length) return // keep one option selected
        const opt = options.find((o) => String(o.value) === vals[vals.length - 1])
        if (opt) onChange(opt.value)
      }}
      className={clsx('seg', className)}
      style={columns ? { gridTemplateColumns: `repeat(${columns}, 1fr)` } : undefined}
    >
      {options.map((o) => (
        <Toggle key={String(o.value)} value={String(o.value)} aria-label={o.aria || undefined} className="seg-item">
          {o.label}
        </Toggle>
      ))}
    </ToggleGroup>
  )
}

export function SwitchRow({ checked, onChange, label, hint, danger = false }) {
  return (
    <label className={clsx('switch-row', danger && checked && 'danger')}>
      <span className="grow">
        <b>{label}</b>
        {hint && <span className="switch-hint">{hint}</span>}
      </span>
      <Switch.Root checked={checked} onCheckedChange={(c) => onChange(c)} className="hh-switch">
        <Switch.Thumb className="hh-switch-thumb" />
      </Switch.Root>
    </label>
  )
}

// ---------------------------------------------------------------- confetti
const PALETTE = ['#FF2E88', '#FFE14D', '#A3E635', '#38BDF8', '#ffffff']

export function burst(kind = 'small') {
  try {
    const base = { colors: PALETTE, disableForReducedMotion: true, shapes: ['square'], ticks: 220 }
    if (kind === 'big') {
      const end = Date.now() + 1600
      const frame = () => {
        confetti({ ...base, particleCount: 6, angle: 60, spread: 70, origin: { x: 0, y: 0.75 }, startVelocity: 70, scalar: 1.6 })
        confetti({ ...base, particleCount: 6, angle: 120, spread: 70, origin: { x: 1, y: 0.75 }, startVelocity: 70, scalar: 1.6 })
        if (Date.now() < end) requestAnimationFrame(frame)
      }
      frame()
    } else {
      confetti({ ...base, particleCount: 70, spread: 75, startVelocity: 38, origin: { y: 0.35 }, scalar: 1.1 })
    }
  } catch { /* canvas unavailable: no confetti, no problem */ }
}

// ---------------------------------------------------------------- Magic UI-style marquee (pure CSS)
export function Marquee({ items, speed = 40 }) {
  if (!items.length) return null
  const row = items.map((it, i) => <span className="marquee-item" key={i}>{it}</span>)
  return (
    <div className="marquee" style={{ '--marquee-duration': `${Math.max(12, items.length * speed / 4)}s` }}>
      <div className="marquee-track">{row}</div>
      <div className="marquee-track" aria-hidden>{row}</div>
    </div>
  )
}
