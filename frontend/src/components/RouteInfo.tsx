import { RouteResponse } from '../lib/types'

interface RouteInfoProps {
  route: RouteResponse | null
}

export function RouteInfo({ route }: RouteInfoProps) {
  if (!route) return null

  return (
    <div className="route-info-card">
      <h3>Route Comparison</h3>
      <div className="route-row">
        <span className="label">Shortest (Red):</span>
        <span>{route.shortest_path.distance_m.toFixed(0)}m | {route.shortest_path.sun_minutes.toFixed(1)} sun-mins</span>
      </div>
      <div className="route-row">
        <span className="label">Shaded (Green):</span>
        <span>{route.shade_path.distance_m.toFixed(0)}m | {route.shade_path.sun_minutes.toFixed(1)} sun-mins</span>
      </div>
      <div className="route-row">
        <span className="label">Saved:</span>
        <span>{route.sun_minutes_saved.toFixed(1)} sun-mins (+{route.extra_distance_m.toFixed(0)}m)</span>
      </div>
      <p className="tradeoff">{route.trade_off_sentence}</p>
      <p className="solar-info">Solar: {route.solar_elevation}° elev, {route.solar_azimuth}° az</p>
    </div>
  )
}
