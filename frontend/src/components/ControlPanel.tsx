import { useState } from 'react'
import { POI } from '../lib/types'

interface ControlPanelProps {
  pois: POI[]
  onRoute: (origin: string, destination: string, sunTolerance: string, speed: number) => void
  onChat: (message: string) => void
  loading: boolean
}

export function ControlPanel({ pois, onRoute, onChat, loading }: ControlPanelProps) {
  const [origin, setOrigin] = useState('Dadu\'s Residence (Middleton Row)')
  const [destination, setDestination] = useState('Belle Vue Clinic')
  const [sunTolerance, setSunTolerance] = useState('low')
  const [speed, setSpeed] = useState(3.0)
  const [chatMsg, setChatMsg] = useState('Walk dadu to the clinic around 3 pm, he can\'t take much sun.')

  const poiNames = [...new Set(pois.map(p => p.name))].sort()

  return (
    <div className="control-panel">
      <h2>Chhaya</h2>
      <p className="subtitle">Kolkata Shade-Aware Navigation</p>
      
      <div className="section">
        <h3>Route Planning</h3>
        <label>Origin</label>
        <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
          {poiNames.map(name => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        
        <label>Destination</label>
        <select value={destination} onChange={(e) => setDestination(e.target.value)}>
          {poiNames.map(name => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        
        <label>Sun Tolerance</label>
        <select value={sunTolerance} onChange={(e) => setSunTolerance(e.target.value)}>
          <option value="low">Low (prefers shade)</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
        
        <label>Walking Speed (km/h)</label>
        <input type="number" step="0.1" value={speed} onChange={(e) => setSpeed(parseFloat(e.target.value))} />
        
        <button onClick={() => onRoute(origin, destination, sunTolerance, speed)} disabled={loading}>
          {loading ? 'Planning...' : 'Plan Route'}
        </button>
      </div>

      <div className="section">
        <h3>Natural Language (Agent)</h3>
        <textarea
          value={chatMsg}
          onChange={(e) => setChatMsg(e.target.value)}
          rows={3}
          placeholder="e.g. Walk dadu to the clinic around 3 pm, he can't take much sun."
        />
        <button onClick={() => onChat(chatMsg)} disabled={loading}>
          {loading ? 'Thinking...' : 'Ask Agent'}
        </button>
      </div>
    </div>
  )
}
