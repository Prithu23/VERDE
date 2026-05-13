import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import fs from 'fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

function notifyPlugin(apiKey: string) {
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

            if (!apiKey) {
              res.statusCode = 500
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ return: false, message: ['FAST2SMS_API_KEY not set in .env.local'] }))
              return
            }

            const message =
              `AEGIS EMERGENCY ALERT\n` +
              `Agency: ${agency}\n` +
              `Severity: ${severity} | Status: ${status}\n` +
              `${description}\n` +
              `Respond immediately.\n` +
              `-- VERDE Emergency Response System`

            const r = await fetch('https://www.fast2sms.com/dev/bulkV2', {
              method: 'POST',
              headers: { authorization: apiKey, 'Content-Type': 'application/json' },
              body: JSON.stringify({ route: 'q', numbers: phone, message, flash: 0, dnd: 0 }),
            })

            const data = await r.json()
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ ...data, recipient: name }))
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

function serveParentData() {
  const dataFiles = ['mission_log.json', 'audio_log.json', 'anomaly_log.json', 'sensor_log.json', 'ehs_log.json', 'fusion_log.json']
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
    serveParentData(),
    notifyPlugin(env.FAST2SMS_API_KEY || ''),
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
