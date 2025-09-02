import DateRangePicker from './DateRangePicker'

type Props = {
  start: string
  end: string
  onDateChange: (k:'start'|'end', v:string)=>void
  onExcel: ()=>void
  onPDF: ()=>void
}

export default function Toolbar({ start, end, onDateChange, onExcel, onPDF }: Props){
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 bg-white rounded-2xl shadow p-4">
      <DateRangePicker start={start} end={end} onChange={onDateChange} />
      <div className="flex gap-2">
        <button onClick={onExcel} className="px-3 py-2 rounded-xl bg-green-600 text-white">Descargar Excel</button>
        <button onClick={onPDF} className="px-3 py-2 rounded-xl bg-indigo-600 text-white">Descargar Grafico</button>
      </div>
    </div>
  )
}
