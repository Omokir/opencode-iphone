import test from 'node:test'
import assert from 'node:assert/strict'
import { projectServers, reconcile, PREFIX } from './kzl-connections.mjs'

const config = { type: 'local', command: ['/fixture-only'] }
const registry = projects => ({ version: 1, revision: 1, servers: { docs: { config, projects } } })

test('global registration grants no project', () => {
  assert.equal(projectServers(registry([]), '/client/a').size, 0)
})
test('grant applies to exact project only, never descendants or siblings', () => {
  assert.equal(projectServers(registry(['/client/a']), '/client/a').size, 1)
  for (const directory of ['/client', '/client/ab', '/client/a/sub', '/client/b']) {
    assert.equal(projectServers(registry(['/client/a']), directory).size, 0)
  }
})
test('registered command is data; names are isolated and copies independent', () => {
  const value = registry(['/client/a'])
  const projected = projectServers(value, '/client/a')
  assert.deepEqual(projected.get(PREFIX + 'docs'), { ...config, disabled: false })
  projected.get(PREFIX + 'docs').command[0] = 'modified'
  assert.equal(value.servers.docs.config.command[0], '/fixture-only')
})
test('revocation persists as absent runtime configuration', () => {
  const value = registry(['/client/a'])
  assert.equal(projectServers(value, '/client/a').size, 1)
  value.servers.docs.projects = []
  assert.equal(projectServers(JSON.parse(JSON.stringify(value)), '/client/a').size, 0)
})
test('corrupt state or literal secrets rejected before activation', () => {
  const configs = [
    { type: 'remote', url: 'https://user:secret@example.com/mcp' },
    { type: 'remote', url: 'https://example.com/mcp?token=secret' },
    { type: 'local', command: ['tool'], environment: { API_KEY: 'literal-secret' } },
    { type: 'local', command: 'sh -c tool' },
    { type: 'remote', url: 'https://example.com/mcp', headers: { Authorization: 'secret' } },
  ]
  for (const config of configs) {
    const value = registry(['/client/a']); value.servers.docs.config = config
    assert.throws(() => projectServers(value, '/client/a'))
  }
  assert.throws(() => projectServers({ ...registry([]), version: 2 }, '/client/a'))
})

test('adapter activates only a granted project, revokes and preserves unrelated MCPs', () => {
  const configs = new Map([['existing', { type: 'remote', url: 'https://example.com' }]])
  const editor = { get: n => configs.get(n), set: (n,c) => configs.set(n,c), remove: n => configs.delete(n) }
  const owned = new Set()
  reconcile(editor, projectServers(registry([]), '/client/a'), owned)
  assert.equal(configs.size, 1)
  reconcile(editor, projectServers(registry(['/client/a']), '/client/a'), owned)
  assert.equal(configs.get(PREFIX + 'docs').disabled, false)
  reconcile(editor, projectServers(registry([]), '/client/a'), owned)
  assert.equal(configs.has(PREFIX + 'docs'), false)
  assert.equal(configs.has('existing'), true)
})

test('adapter does not overwrite or remove a conflicting pre-existing server', () => {
  const original = { type: 'remote', url: 'https://existing.example.com/mcp' }
  const configs = new Map([[PREFIX + 'docs', original]])
  const editor = { get: n => configs.get(n), set: (n,c) => configs.set(n,c), remove: n => configs.delete(n) }
  const owned = new Set()
  reconcile(editor, projectServers(registry(['/client/a']), '/client/a'), owned)
  assert.equal(configs.get(PREFIX + 'docs'), original)
  assert.equal(owned.size, 0)
  reconcile(editor, new Map(), owned)
  assert.equal(configs.get(PREFIX + 'docs'), original)
})
