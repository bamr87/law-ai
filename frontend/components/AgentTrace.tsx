'use client'

interface AgentTraceProps {
  steps: string[]
  confidence?: number
}

export default function AgentTrace({ steps, confidence }: AgentTraceProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">Agent Execution Trace</h3>
        {confidence && (
          <div className="text-xs px-2 py-1 bg-emerald-500/10 text-emerald-400 rounded">
            {Math.round(confidence * 100)}% confidence
          </div>
        )}
      </div>
      <ol className="space-y-2 text-sm">
        {steps.map((step, i) => (
          <li key={i} className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center flex-shrink-0">
              {i + 1}
            </div>
            <span>{step}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}