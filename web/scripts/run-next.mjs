import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const command = process.argv[2]
const extraArgs = process.argv.slice(3)

const distByCommand = {
  dev: '.next-dev',
  build: '.next-build',
  start: '.next-build',
}

if (process.env.VERCEL) {
  distByCommand.build = '.next'
  distByCommand.start = '.next'
}

if (!command || !['dev', 'build', 'start'].includes(command)) {
  console.error('Usage: node scripts/run-next.mjs <dev|build|start> [next args...]')
  process.exit(1)
}

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const nextCli = path.join(projectRoot, 'node_modules', 'next', 'dist', 'bin', 'next')
const child = spawn(process.execPath, [nextCli, command, ...extraArgs], {
  env: {
    ...process.env,
    NEXT_DIST_DIR: distByCommand[command],
  },
  stdio: 'inherit',
  shell: false,
})

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal)
    return
  }
  process.exit(code ?? 0)
})
