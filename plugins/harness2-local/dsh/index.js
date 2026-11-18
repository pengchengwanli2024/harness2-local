/**
 * DeepSeek Harness (DSH) skill provider for this plugin's `skills/` directory.
 *
 * Zero dependencies. Registers every `<root>/<dir>/SKILL.md` on `ctx.skills`, applying the optional
 * host-specific overrides in `dsh/skills.json`:
 *
 *   { "provider": "<name>", "root": "../skills",
 *     "skills": { "<dir>": { "name": "...", "description": "...", "preface": "..." } } }
 *
 * `preface` is prepended to the skill body, so the upstream SKILL.md stays byte-identical for other
 * hosts. `{{packageDir}}` and `{{skillDir}}` in a preface expand to absolute paths.
 */
import { readFile, readdir } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const PACKAGE_DIR = resolve(HERE, '..')
/** Same rank DSH gives its own bundled skills: project and user skills of the same name win. */
const BUNDLED_SKILL_RANK = 600
const SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/** Parse the leading YAML frontmatter's single-line scalars; returns `undefined` without frontmatter. */
export function parseSkill(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text)
  if (match === null) return undefined
  const fields = {}
  for (const line of match[1].split(/\r?\n/)) {
    const pair = /^([A-Za-z][\w-]*):\s*(.*)$/.exec(line)
    if (pair === null) continue
    let value = pair[2].trim()
    if (value.startsWith('"')) {
      try {
        value = JSON.parse(value)
      } catch {
        value = value.replace(/^"|"$/g, '')
      }
    } else if (value.startsWith("'")) {
      value = value.replace(/^'|'$/g, '').replaceAll("''", "'")
    }
    fields[pair[1]] = value
  }
  return { fields, body: text.slice(match[0].length) }
}

async function loadManifest() {
  try {
    return JSON.parse(await readFile(join(HERE, 'skills.json'), 'utf8'))
  } catch (error) {
    if (error.code === 'ENOENT') return {}
    throw error
  }
}

function expand(text, skillDir) {
  return text.replaceAll('{{packageDir}}', PACKAGE_DIR).replaceAll('{{skillDir}}', skillDir)
}

/** Build the provider; exported for tests. */
export async function createProvider(logger) {
  const manifest = await loadManifest()
  const providerName = manifest.provider ?? 'plugin-skills'
  const root = resolve(HERE, manifest.root ?? '../skills')
  const overrides = manifest.skills ?? {}

  async function read(dir) {
    const skillDir = join(root, dir)
    const path = join(skillDir, 'SKILL.md')
    const parsed = parseSkill(await readFile(path, 'utf8'))
    if (parsed === undefined) return undefined
    const override = overrides[dir] ?? {}
    const name = override.name ?? parsed.fields.name
    const description = override.description ?? parsed.fields.description
    if (typeof name !== 'string' || !SKILL_NAME.test(name) || typeof description !== 'string' || description === '') {
      logger?.warn(`skill "${dir}" skipped: it needs a kebab-case name and a description`)
      return undefined
    }
    const preface = typeof override.preface === 'string' ? `${expand(override.preface, skillDir)}\n\n` : ''
    return {
      name,
      description,
      invocation: { modelInvocable: true, userInvocable: true },
      provider: providerName,
      source: 'bundled',
      resourceBase: { kind: 'directory', path: skillDir },
      path,
      content: preface + parsed.body,
    }
  }

  return {
    name: providerName,
    async list() {
      let dirs
      try {
        dirs = (await readdir(root, { withFileTypes: true })).filter((entry) => entry.isDirectory()).map((entry) => entry.name)
      } catch (error) {
        logger?.warn(`skill root "${root}" is not readable: ${error.message}`)
        return { candidates: [], complete: false }
      }
      const candidates = []
      for (const dir of dirs.sort()) {
        if (overrides[dir]?.hidden === true) continue
        try {
          const skill = await read(dir)
          if (skill === undefined) continue
          const { content: _content, ...summary } = skill
          candidates.push({ ...summary, rank: BUNDLED_SKILL_RANK, locator: dir })
        } catch (error) {
          if (error.code !== 'ENOENT') logger?.warn(`skill "${dir}" skipped: ${error.message}`)
        }
      }
      return candidates
    },
    async get(candidate) {
      try {
        return await read(candidate.locator)
      } catch (error) {
        if (error.code === 'ENOENT') return undefined
        throw error
      }
    },
  }
}

/** Resolved at import so the registered provider name matches the candidates' owner. */
const PROVIDER_NAME = (await loadManifest()).provider ?? 'plugin-skills'

export const name = 'plugin-skills'
export const inject = ['skills']

export function apply(ctx) {
  let provider
  const ready = () => (provider ??= createProvider(ctx.logger))
  ctx.skills.registerProvider(() => ({
    name: PROVIDER_NAME,
    list: async (options) => (await ready()).list(options),
    get: async (candidate, options) => (await ready()).get(candidate, options),
  }))
}
