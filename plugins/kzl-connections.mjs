import { openSync, readFileSync, fstatSync, closeSync, constants } from 'node:fs'
import { homedir } from 'node:os'
import path from 'node:path'

export const PREFIX = 'kzl_center_'

// Parse independently of the gateway: persisted state is not trusted code.
export function projectServers(value, directory) {
  if (value?.version !== 1 || !Number.isSafeInteger(value.revision) || value.revision < 0 ||
      !value.servers || typeof value.servers !== 'object' || Array.isArray(value.servers) ||
      Object.keys(value.servers).length > 100) throw new Error('Invalid registry')
  const result = new Map()
  for (const [name, row] of Object.entries(value.servers)) {
    if (!/^[a-z][a-z0-9_-]{0,47}$/.test(name) || !Array.isArray(row?.projects) || row.projects.length > 100 ||
        row.projects.some(p => typeof p !== 'string' || !p.startsWith('/') || p.includes('\0'))) throw new Error('Invalid grant')
    const config = row.config
    if (!config || typeof config !== 'object' || Array.isArray(config)) throw new Error('Invalid config')
    const allowed = config.type === 'local' ? ['type', 'command', 'environment'] : ['type', 'url']
    if (Object.keys(config).some(k => !allowed.includes(k))) throw new Error('Unsupported config')
    if (config.type === 'local') {
      if (!Array.isArray(config.command) || config.command.length < 1 || config.command.length > 64 ||
          config.command.some(a => typeof a !== 'string' || !a || a.length > 4096 || a.includes('\0'))) throw new Error('Invalid command')
      const env = config.environment ?? {}
      if (!env || typeof env !== 'object' || Array.isArray(env) || Object.keys(env).length > 64 ||
          Object.entries(env).some(([k,v]) => !/^[A-Z_][A-Z0-9_]{0,99}$/.test(k) || typeof v !== 'string' || !/^\{env:[A-Z_][A-Z0-9_]{0,99}\}$/.test(v))) throw new Error('Invalid environment')
    } else if (config.type === 'remote') {
      if (typeof config.url !== 'string' || config.url.length > 2048) throw new Error('Invalid URL')
      const url = new URL(config.url)
      if (url.protocol !== 'https:' || !url.hostname || url.username || url.password || url.search || url.hash) throw new Error('Invalid URL')
    } else throw new Error('Invalid type')
    // Exact directory grant, not a parent-prefix match. No global activation.
    if (row.projects.includes(directory)) result.set(PREFIX + name, { ...structuredClone(config), disabled: false })
  }
  return result
}

export function readRegistry(file) {
  let fd
  try {
    fd = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
    const info = fstatSync(fd)
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o077) || info.nlink !== 1 || info.size > 1024 * 1024) throw new Error('Unsafe registry')
    return JSON.parse(readFileSync(fd, 'utf8'))
  } catch {
    // Missing/corrupt/unsafe state fails closed. Never log config or errors.
    return { version: 1, revision: 0, servers: {} }
  } finally { if (fd !== undefined) closeSync(fd) }
}

export function reconcile(editor, desired, owned) {
  for (const name of owned) if (!desired.has(name)) editor.remove(name)
  for (const [name, config] of desired) {
    if (editor.get(name) && !owned.has(name)) continue
    editor.set(name, structuredClone(config)); owned.add(name)
  }
}

export default {
  id: 'pocket.kzl-connections',
  async setup(ctx) {
    const file = path.join(homedir(), '.local/state/opencode-iphone/connections/connections.json')
    let desired = new Map()
    let fingerprint = ''
    let busy = false
    let stopped = false
    // Only touch names successfully introduced by this adapter. Never remove
    // unrelated servers or replace a conflicting user-configured server.
    const owned = new Set()
    const refresh = () => {
      try { desired = projectServers(readRegistry(file), ctx.location.directory) }
      catch { desired = new Map() }
      return JSON.stringify([...desired])
    }
    fingerprint = refresh()
    const registration = await ctx.mcp.transform(editor => reconcile(editor, desired, owned))
    const timer = setInterval(async () => {
      if (busy || stopped) return
      busy = true
      try {
        const next = refresh()
        if (next !== fingerprint) {
          await ctx.mcp.reload()
          fingerprint = next
        }
      } catch { /* Unconfirmed reconciliation; retry declarative state, not tool calls. */ }
      finally { busy = false }
    }, 2000)
    return async () => { stopped = true; clearInterval(timer); await registration.dispose() }
  },
}
