import { useState, useEffect } from 'react'
import { MapView } from './components/MapView'
import { TimeSlider } from './components/TimeSlider'
import { ControlPanel } from './components/ControlPanel'
import { RouteInfo } from './components/RouteInfo'
import { api } from './lib/api'
import { POI, RouteResponse, ShadowResponse, WindowResponse } from './lib/types'
import './styles/App.css'

function App() {
  const [pois, setPois] = useState<POI[]>([])
  const [selectedTime, setSelectedTime] = useState('15:00')
  const [shadows, setShadows] = useState<ShadowResponse | null>(null)
  const [currentRoute, setCurrentRoute] = useState<RouteResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [bestWindow, setBestWindow] = useState<WindowResponse | null>(null)

  useEffect(() => {
    loadPois()
    loadShadows('15:00')
    loadBestWindow()
  }, [])

  useEffect(() => {
    loadShadows(selectedTime)
  }, [selectedTime])

  const loadPois = async () => {
    try {
      const data = await api.getPois()
      setPois(data.pois)
    } catch (err) {
      console.error('Failed to load POIs:', err)
    }
  }

  const loadShadows = async (time: string) => {
    try {
      const data = await api.getShadows(time)
      setShadows(data)
    } catch (err) {
      console.error('Failed to load shadows:', err)
    }
  }

  const loadBestWindow = async () => {
    try {
      const data = await api.getBestWindow()
      setBestWindow(data)
    } catch (err) {
      console.error('Failed to load best window:', err)
    }
  }

  const handleRoute = async (origin: string, destination: string, sunTolerance: string, speed: number) => {
    setLoading(true)
    try {
      const data = await api.planRoute({
        origin,
        destination,
        depart_time: selectedTime,
        sun_tolerance: sunTolerance,
        speed_kmh: speed
      })
      setCurrentRoute(data)
    } catch (err) {
      console.error('Failed to plan route:', err)
      alert('Failed to plan route. Check origin/destination names.')
    } finally {
      setLoading(false)
    }
  }

  const handleAgentChat = async (message: string) => {
    setLoading(true)
    try {
      const data = await api.agentChat({ message, depart_time: selectedTime })
      if (data.route_data) {
        setCurrentRoute(data.route_data)
        alert(data.reply)
      } else {
        alert(data.reply || 'No route found')
      }
    } catch (err) {
      console.error('Failed to chat:', err)
      alert('Failed to process message')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <MapView 
        pois={pois} 
        shadows={shadows} 
        route={currentRoute} 
      />
      <div className="overlay">
        <ControlPanel 
          pois={pois}
          onRoute={handleRoute}
          onChat={handleAgentChat}
          loading={loading}
        />
        <RouteInfo route={currentRoute} />
        <TimeSlider 
          selectedTime={selectedTime}
          onTimeChange={setSelectedTime}
        />
        {bestWindow && (
          <div className="best-window-card">
            <h3>Best Shade Window</h3>
            <p>{bestWindow.best_window?.[0] || 'Loading...'}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
