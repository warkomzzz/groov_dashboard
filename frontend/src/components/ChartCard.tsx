import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'

type Pt = { ts: string; value: number }

export default function ChartCard({ title, data }: { title: string; data: Pt[] }){
  return (
    <div className="glass-card p-4 text-white">
      <h3 className="font-semibold mb-2">{title}</h3>
      <div className="h-56">
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.15)" />
            <XAxis dataKey="ts" hide />
            <YAxis stroke="rgba(255,255,255,.6)" tick={{ fill: 'rgba(255,255,255,.75)' }} />
            <Tooltip formatter={(v)=> (typeof v==='number'? v.toFixed(3): v)} labelFormatter={(l)=> new Date(l).toLocaleString()} />
            <Line type="monotone" dataKey="value" dot={false} strokeWidth={2} stroke="#e7b35b" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
