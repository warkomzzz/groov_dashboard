import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'

type Pt = { ts: string; value: number }

export default function ChartCard({ title, data }: { title: string; data: Pt[] }){
  return (
    <div className="bg-white rounded-2xl shadow p-4">
      <h3 className="font-semibold mb-2">{title}</h3>
      <div className="h-56">
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis />
            <Tooltip formatter={(v)=> (typeof v==='number'? v.toFixed(3): v)} labelFormatter={(l)=> new Date(l).toLocaleString()} />
            <Line type="monotone" dataKey="value" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
