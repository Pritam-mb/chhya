export interface POI {
  id: string
  name: string
  lat: number
  lon: number
  category: string
}

export interface POIsResponse {
  pois: POI[]
}

export interface RouteRequest {
  origin: string
  destination: string
  depart_time?: string
  sun_tolerance?: string
  speed_kmh?: number
}

export interface RouteSegment {
  sunlit_fraction: number
  path_geojson?: any
  geom?: any
}

export interface RoutePath {
  name: string
  distance_m: number
  time_min: number
  sun_minutes: number
  shade_percentage: number
  segments: any[]
}

export interface RouteResponse {
  origin: { name: string; lat: number; lon: number }
  destination: { name: string; lat: number; lon: number }
  depart_time: string
  sun_tolerance: string
  speed_kmh: number
  solar_elevation: number
  solar_azimuth: number
  shadow_factor: number
  shortest_path: RoutePath
  shade_path: RoutePath
  trade_off_sentence: string
  extra_distance_m: number
  sun_minutes_saved: number
}

export interface ShadowFeature {
  type: string
  geometry: any
  properties: any
}

export interface ShadowResponse {
  type: string
  features: ShadowFeature[]
  properties: any
}

export interface WindowResponse {
  best_window: string[]
  heat_index: number
  baseline_mae: number
  tabpfn_mae: number
  info: string
}

export interface ChatRequest {
  message: string
  depart_time?: string
  sun_tolerance?: string
}

export interface ChatResponse {
  reply: string
  parsed_parameters: any
  route_data: RouteResponse | null
  error?: string
}
