
type Props = {
  start: string
  end: string
  onChange: (k: 'start'|'end', v: string) => void
}

export default function DateRangePicker({ start, end, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-sm">Desde</label>
      <input type="datetime-local" value={start} onChange={e=>onChange('start', e.target.value)} className="border rounded px-2 py-1"/>
      <label className="text-sm">Hasta</label>
      <input type="datetime-local" value={end} onChange={e=>onChange('end', e.target.value)} className="border rounded px-2 py-1"/>
    </div>
  )
}
