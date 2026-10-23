import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const script = fileURLToPath(new URL('./package_release.py', import.meta.url));
const windows = process.platform === 'win32';
const result = spawnSync(windows ? 'py' : 'python3', [...(windows ? ['-3'] : []), script], { stdio: 'inherit' });
if (result.error) process.stderr.write(`Packaging failed: ${result.error.message}\n`);
process.exit(result.status ?? 1);
