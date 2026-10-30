import { mkdir, writeFile, rename, unlink } from 'node:fs/promises'
import { createHash, randomUUID } from 'node:crypto'
import { homedir } from 'node:os'
import path from 'node:path'

export function projectTools(tools) {
  return tools.slice(0, 10000).filter(tool => typeof tool.id === 'string').map(tool => ({
    id: tool.id.slice(0, 200),
    // Descriptions remain untrusted catalog data, never system instructions.
    description: typeof tool.description === 'string' ? tool.description.slice(0, 800) : '',
    parameters: Object.keys(tool.input?.properties ?? {}).slice(0, 40),
  }))
}

// No tools registered, no credentials read, no calls executed. Only snapshots
// the final runtime registry after transforms, scoped to this loaded location.
export default {
  id: 'pocket.kzl-catalog',
  async setup(ctx) {
    const directory = ctx.location.directory
    const root = path.join(homedir(), '.local/state/opencode-iphone/tool-catalog')
    const name = createHash('sha256').update(directory).digest('hex') + '.json'
    let stopped = false
    let busy = false
    const publish = async () => {
      if (stopped || busy) return
      busy = true
      const temporary = path.join(root, '.' + randomUUID() + '.tmp')
      try {
        const tools = projectTools(await ctx.tool.list())
        if (stopped) return
        await mkdir(root, { recursive: true, mode: 0o700 })
        await writeFile(temporary, JSON.stringify({ version: 1, directory, checkedAt: Date.now(), tools }), { mode: 0o600, flag: 'wx' })
        if (stopped) { await unlink(temporary); return }
        await rename(temporary, path.join(root, name))
      } catch { await unlink(temporary).catch(() => {}) }
      finally { busy = false }
    }
    // Defer first read until setup has returned, avoiding registry load cycles.
    const first = setTimeout(() => { void publish() }, 1000)
    const interval = setInterval(() => { void publish() }, 15000)
    return () => { stopped = true; clearTimeout(first); clearInterval(interval) }
  },
}
