import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import fs from 'fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

// CALLMEBOT_KEYS=9108307690:123456,9284955662:654321  →  { phone: apikey }
function parseCallMeBotKeys(raw: string): Record<string, string> {
  const keys: Record<string, string> = {}
  for (const pair of raw.split(',')) {
    const [phone, key] = pair.split(':').map(s => s?.trim())
    if (phone && key && key !== 'your_api_key_here') keys[phone] = key
  }
  return keys
}

function roverLocation(): string {
  try {
    const log = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', 'sensor_log.json'), 'utf-8'))
    const r = Array.isArray(log) ? log[log.length - 1] : log
    if (r?.gps_valid && r.lat != null && r.lon != null) {
      return `Loc: ${r.lat.toFixed(5)},${r.lon.toFixed(5)}\nhttps://maps.google.com/?q=${r.lat},${r.lon}`
    }
  } catch {}
  return 'Loc: GPS unavailable'
}

function notifyPlugin(apiKeys: Record<string, string>) {
  return {
    name: 'notify-api',
    configureServer(server: any) {
      server.middlewares.use('/api/notify', (req: any, res: any) => {
        if (req.method !== 'POST') { res.statusCode = 405; res.end(); return }

        let body = ''
        req.on('data', (chunk: any) => { body += chunk })
        req.on('end', async () => {
          try {
            const { phone, name, agency, severity, description, status } = JSON.parse(body)

            const apiKey = apiKeys[phone]
            if (!apiKey) {
              res.statusCode = 500
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ return: false, message: [`No CallMeBot key for ${phone} in CALLMEBOT_KEYS (.env.local)`] }))
              return
            }

            const message =
              `AEGIS EMERGENCY ALERT\n` +
              `Agency: ${agency}\n` +
              `Severity: ${severity} | Status: ${status}\n` +
              `${description}\n` +
              `${roverLocation()}\n` +
              `Respond immediately.\n` +
              `-- VERDE Emergency Response System`

            const qs = new URLSearchParams({ phone: `+91${phone}`, text: message, apikey: apiKey })
            const r = await fetch(`https://api.callmebot.com/whatsapp.php?${qs}`)
            const text = await r.text()
            const ok = /queued|sent/i.test(text)
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({
              return: ok,
              message: [ok ? 'WhatsApp queued' : text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200)],
              recipient: name,
            }))
          } catch (e) {
            res.statusCode = 500
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ return: false, message: [String(e)] }))
          }
        })
      })
    },
  }
}

function locationProxy() {
  return {
    name: 'location-proxy',
    configureServer(server: any) {
      // /api/location  →  ipinfo.io (city-level IP fallback)
      server.middlewares.use('/api/location', async (_req: any, res: any) => {
        try {
          const r    = await fetch('https://ipinfo.io/json')
          const data = await r.json()
          const [lat, lon] = (data.loc ?? '0,0').split(',').map(Number)
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-store')
          res.end(JSON.stringify({
            lat, lon,
            city:     data.city    ?? '',
            region:   data.region  ?? '',
            country:  data.country ?? '',
            accuracy: 1500,
            source:   'ip',
          }))
        } catch (e) {
          res.statusCode = 502
          res.end(JSON.stringify({ error: String(e) }))
        }
      })

      // /api/address?lat=X&lon=Y  →  Nominatim reverse geocoding (street-level)
      server.middlewares.use('/api/address', async (req: any, res: any) => {
        try {
          const qs  = req.url.includes('?') ? req.url.split('?')[1] : ''
          const p   = new URLSearchParams(qs)
          const lat = p.get('lat')
          const lon = p.get('lon')
          if (!lat || !lon) { res.statusCode = 400; res.end('{}'); return }
          const r = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=18&addressdetails=1`,
            { headers: { 'User-Agent': 'VERDE-Emergency-Dashboard/1.0' } }
          )
          const data = await r.json()
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-store')
          res.end(JSON.stringify(data))
        } catch (e) {
          res.statusCode = 502
          res.end(JSON.stringify({ error: String(e) }))
        }
      })
    },
  }
}

function serveParentData() {
  const dataFiles = ['mission_log.json', 'audio_log.json', 'anomaly_log.json', 'sensor_log.json', 'ehs_log.json', 'fusion_log.json', 'detection_state.json']
  return {
    name: 'serve-parent-data',
    configureServer(server: any) {
      dataFiles.forEach((file) => {
        server.middlewares.use(`/${file}`, (_req: any, res: any) => {
          try {
            const filePath = path.resolve(__dirname, '..', file)
            res.setHeader('Content-Type', 'application/json')
            res.end(fs.readFileSync(filePath))
          } catch {
            res.statusCode = 404
            res.end('Not found')
          }
        })
      })
    },
  }
}

function figmaAssetResolver() {
  return {
    name: 'figma-asset-resolver',
    resolveId(id) {
      if (id.startsWith('figma:asset/')) {
        const filename = id.replace('figma:asset/', '')
        return path.resolve(__dirname, 'src/assets', filename)
      }
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return defineConfig({
  plugins: [
    figmaAssetResolver(),
    locationProxy(),
    serveParentData(),
    notifyPlugin(parseCallMeBotKeys(env.CALLMEBOT_KEYS || '')),
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
  })
})
