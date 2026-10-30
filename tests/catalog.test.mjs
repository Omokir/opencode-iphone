import test from 'node:test'
import assert from 'node:assert/strict'
import { projectTools } from '../plugins/kzl-catalog.mjs'

test('runtime catalog projects only bounded metadata, never executors or input values', () => {
  let called = false
  const value = projectTools([{ id: 'linux_computer_apps', description: 'List windows',
    input: { properties: { window: { type: 'string', default: 'private-value' } } },
    secret: 'private-secret', execute() { called = true } }])
  assert.deepEqual(value, [{ id: 'linux_computer_apps', description: 'List windows', parameters: ['window'] }])
  assert.equal(called, false)
  assert.ok(!JSON.stringify(value).includes('private'))
})

test('bounds descriptions and ignores records without identifiers', () => {
  const value = projectTools([{ description: 'missing ID' }, { id: 'x'.repeat(500), description: 'y'.repeat(2000) }])
  assert.equal(value.length, 1)
  assert.equal(value[0].id.length, 200)
  assert.equal(value[0].description.length, 800)
})
