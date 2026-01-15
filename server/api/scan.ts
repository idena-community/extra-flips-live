import { exec } from 'node:child_process'
import { promisify } from 'node:util'
import { readFile, readdir, rm, mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { existsSync } from 'node:fs'

const execAsync = promisify(exec)

export default defineEventHandler(async (event) => {
  try {
    const scriptPath = join(process.cwd(), 'scripts', 'flip_extra_flips_live.py')
    const outDir = join(process.cwd(), 'scripts', 'out')
    
    // --- STABLE CONFIGURATION ---
    // We force 0. In the Python script logic, 0 means "Auto-detect current live epoch".
    // This proved to be the working solution (returning 14 flips instead of 0).
    const targetEpoch = 0 
    // ----------------------------

    // 1. Cleanup output directory
    if (existsSync(outDir)) {
      await rm(outDir, { recursive: true, force: true })
    }
    await mkdir(outDir, { recursive: true })

    // 2. Command configuration (Windows/Linux compatible)
    const pythonCommand = process.platform === 'win32' ? 'python' : 'python3'
    
    const command = `${pythonCommand} "${scriptPath}" --epoch ${targetEpoch} --threshold 3 --out-dir "${outDir}"`
    
    console.log(`🚀 Executing Live Scan: ${command}`)
    
    await execAsync(command)

    // 3. Read results
    const files = await readdir(outDir)
    const jsonFile = files.find((f: string) => f.endsWith('.meta.json'))

    if (!jsonFile) {
      throw new Error("The Python script did not generate any JSON file.")
    }

    const content = await readFile(join(outDir, jsonFile), 'utf-8')
    return {
      success: true,
      data: JSON.parse(content)
    }

  } catch (error: any) {
    console.error('CRITICAL ERROR:', error)
    return {
      success: false,
      error: error.message,
      command_failed: true
    }
  }
})