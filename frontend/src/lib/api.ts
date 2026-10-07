import { POIsResponse, RouteResponse, RouteRequest, ShadowResponse, WindowResponse, ChatRequest, ChatResponse } from './types'

const API_BASE = '/api'

export const api = {
  async getHealth() {
    const res = await fetch(${API_BASE}/health)
    return res.json()
  },

  async getPois(): Promise<POIsResponse> {
    const res = await fetch(${API_BASE}/pois)
    return res.json()
  },

  async getShadows(time: string): Promise<ShadowResponse> {
    const res = await fetch(${API_BASE}/shadows?time=)
    return res.json()
  },

  async planRoute(req: RouteRequest): Promise<RouteResponse> {
    const res = await fetch(${API_BASE}/route, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  async getBestWindow(date?: string): Promise<WindowResponse> {
    const url = date ? ${API_BASE}/window?date= : ${API_BASE}/window
    const res = await fetch(url)
    return res.json()
  },

  async agentChat(req: ChatRequest): Promise<ChatResponse> {
    const res = await fetch(${API_BASE}/agent/chat, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },

  async voiceBriefing(text: string): Promise<any> {
    const res = await fetch(${API_BASE}/voice/briefing, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    })
    return res.json()
  }
}
