/**
 * Frontend/backend contract gate (spec 051 / BL-20260811-16).
 *
 * `lib/api.ts` describes the API with hand-written TypeScript interfaces; the
 * backend describes it with Pydantic models. Nothing connected the two, so a
 * field the server renamed, dropped or newly required drifted silently until a
 * user hit it — no test crossed the boundary.
 *
 * `manage.py export_api_schema` publishes the backend's `model_json_schema()`
 * to `__tests__/fixtures/api-schema.json`; this test compares each contract
 * against the interface the client uses for the same payload, and checks the
 * MSW fixtures the component tests run against still satisfy the schema.
 * Either half failing means the fixture or the client is stale — regenerate
 * with `make manage CMD=export_api_schema`, then fix whichever side moved.
 *
 * The browser half of the boundary (real HTTP + a real WebSocket against a
 * live stack) is `frontend/e2e/`, run by `make test-e2e`. This file is the
 * cheap half that runs on every PR.
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import schemaDoc from '../fixtures/api-schema.json'
import { runAnalysis } from '../../lib/api'

type JsonSchema = {
  properties?: Record<string, unknown>
  required?: string[]
}

const contracts = schemaDoc.contracts as unknown as Record<string, JsonSchema>

/**
 * Backend contract name -> the `export interface` in lib/api.ts that carries
 * the same payload. `export_api_schema` keys its output by these names, so a
 * rename on either side has to be made on both.
 */
const INTERFACE_FOR: Record<string, string> = {
  AnalysisRequest: 'AnalysisRequest',
  AnalysisResponse: 'AnalysisResponse',
  IRACOutput: 'IRACOutput',
  PrecedentList: 'PrecedentList',
  LsatQuestion: 'LsatQuestion',
  LsatGradeRequest: 'LsatGradeRequest',
  LsatGradeResponse: 'LsatGradeResponse',
  LsatTutorRequest: 'LsatTutorRequest',
  LsatTutorResponse: 'LsatTutorResponse',
}

const API_SOURCE = readFileSync(
  path.join(process.cwd(), 'lib', 'api.ts'),
  'utf-8',
)

/** Top-level members of `export interface <name>`, with their optionality. */
function interfaceMembers(name: string): Map<string, boolean> {
  const open = API_SOURCE.indexOf(`export interface ${name} {`)
  if (open === -1) {
    throw new Error(`lib/api.ts declares no \`export interface ${name}\``)
  }
  const body = API_SOURCE.slice(open, API_SOURCE.indexOf('\n}\n', open))
  const members = new Map<string, boolean>()
  // Exactly two spaces of indent = a member of this interface, not of a
  // nested inline object literal (which sits at four) and not a doc comment.
  for (const line of body.split('\n')) {
    const match = /^ {2}(\w+)(\??):/.exec(line)
    if (match) members.set(match[1], match[2] === '?')
  }
  return members
}

describe('lib/api.ts matches the backend contracts', () => {
  it('covers every exported contract', () => {
    expect(Object.keys(contracts).sort()).toEqual(
      Object.keys(INTERFACE_FOR).sort(),
    )
  })

  for (const [contract, interfaceName] of Object.entries(INTERFACE_FOR)) {
    describe(contract, () => {
      it('declares exactly the fields the backend model has', () => {
        const schema = contracts[contract]
        expect(schema, `${contract} missing from api-schema.json`).toBeDefined()
        const backend = Object.keys(schema.properties ?? {}).sort()
        const client = [...interfaceMembers(interfaceName).keys()].sort()
        expect(client, `${interfaceName} vs ${contract}`).toEqual(backend)
      })

      it('marks every required backend field as required', () => {
        const members = interfaceMembers(interfaceName)
        const optionalButRequired = (contracts[contract].required ?? []).filter(
          (field) => members.get(field) === true,
        )
        expect(optionalButRequired).toEqual([])
      })
    })
  }
})

/**
 * Minimal presence/primitive check — enough to catch a fixture that lost a
 * required field or changed a field's JSON type, without pulling a JSON-Schema
 * validator into the dependency tree.
 */
function assertSatisfies(contract: string, payload: unknown): void {
  const schema = contracts[contract]
  expect(payload, `${contract} payload`).toBeTypeOf('object')
  const value = payload as Record<string, unknown>
  for (const field of schema.required ?? []) {
    expect(value, `${contract}.${field} is required`).toHaveProperty(field)
    expect(value[field], `${contract}.${field}`).not.toBeUndefined()
  }
  for (const key of Object.keys(value)) {
    expect(
      Object.keys(schema.properties ?? {}),
      `${contract} has no field ${key}`,
    ).toContain(key)
  }
}

describe('MSW fixtures satisfy the backend contracts', () => {
  it('the default /api/analysis fixture is a valid AnalysisResponse', async () => {
    const result = await runAnalysis({ text: 'Does the statute survive?' })
    assertSatisfies('AnalysisResponse', result)
    assertSatisfies('IRACOutput', result.irac)
    assertSatisfies('PrecedentList', result.precedents)
  })
})
