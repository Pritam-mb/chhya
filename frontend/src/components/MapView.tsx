import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import { POI, RouteResponse, ShadowResponse } from '../lib/types'

interface MapViewProps {
  pois: POI[]
  shadows: ShadowResponse | null
  route: RouteResponse | null
}

export function MapView({ pois, shadows, route }: MapViewProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const shadowsLayerId = 'shadows-layer'
  const shortestLayerId = 'shortest-layer'
  const shadeLayerId = 'shade-layer'
  const poisLayerId = 'pois-layer'

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [88.3530, 22.5510],
      zoom: 15
    })

    map.current.on('load', () => {
      addSources()
    })
  }, [])

  const addSources = () => {
    if (!map.current) return

    // Add sources
    if (!map.current.getSource('shadows')) {
      map.current.addSource('shadows', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      })
    }
    if (!map.current.getSource('shortest')) {
      map.current.addSource('shortest', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      })
    }
    if (!map.current.getSource('shade')) {
      map.current.addSource('shade', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      })
    }
    if (!map.current.getSource('pois')) {
      map.current.addSource('pois', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      })
    }

    // Add layers
    if (!map.current.getLayer(shadowsLayerId)) {
      map.current.addLayer({
        id: shadowsLayerId,
        type: 'fill',
        source: 'shadows',
        paint: {
          'fill-color': '#000000',
          'fill-opacity': 0.25
        }
      })
    }
    if (!map.current.getLayer(shortestLayerId)) {
      map.current.addLayer({
        id: shortestLayerId,
        type: 'line',
        source: 'shortest',
        paint: {
          'line-color': '#ef4444',
          'line-width': 5,
          'line-opacity': 0.8
        }
      })
    }
    if (!map.current.getLayer(shadeLayerId)) {
      map.current.addLayer({
        id: shadeLayerId,
        type: 'line',
        source: 'shade',
        paint: {
          'line-color': '#22c55e',
          'line-width': 6,
          'line-opacity': 0.9
        }
      })
    }
    if (!map.current.getLayer(poisLayerId)) {
      map.current.addLayer({
        id: poisLayerId,
        type: 'circle',
        source: 'pois',
        paint: {
          'circle-color': '#3b82f6',
          'circle-radius': 6,
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff'
        }
      })
    }
  }

  useEffect(() => {
    if (!map.current || !map.current.isStyleLoaded()) return
    const source = map.current.getSource('shadows') as maplibregl.GeoJSONSource
    if (source && shadows) {
      source.setData(shadows)
    }
  }, [shadows])

  useEffect(() => {
    if (!map.current || !map.current.isStyleLoaded()) return
    const source = map.current.getSource('pois') as maplibregl.GeoJSONSource
    if (source) {
      const poisGeoJSON = {
        type: 'FeatureCollection' as const,
        features: pois.map(p => ({
          type: 'Feature' as const,
          geometry: { type: 'Point' as const, coordinates: [p.lon, p.lat] },
          properties: { name: p.name, category: p.category }
        }))
      }
      source.setData(poisGeoJSON)
    }
  }, [pois])

  useEffect(() => {
    if (!map.current || !map.current.isStyleLoaded()) return
    const shortestSource = map.current.getSource('shortest') as maplibregl.GeoJSONSource
    const shadeSource = map.current.getSource('shade') as maplibregl.GeoJSONSource
    
    if (shortestSource && shadeSource && route) {
      shortestSource.setData({
        type: 'FeatureCollection',
        features: route.shortest_path.segments.map(s => s.path_geojson || s.geom || s)
      })
      shadeSource.setData({
        type: 'FeatureCollection',
        features: route.shade_path.segments.map(s => s.path_geojson || s.geom || s)
      })
    }
  }, [route])

  return <div ref={mapContainer} className="map-container" />
}
