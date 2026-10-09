// In-process development server for environments that block next dev's child process.
// Uses the same Next.js app and supports frontend hot reload. For deployment use next build/start.
import { createServer } from 'node:http';
import next from 'next';

process.env.CATMS_BUILD_THREADS ??= '1';

const port = Number(process.env.PORT || 3000);
const app = next({ dev: true, hostname: 'localhost', port });
const handle = app.getRequestHandler();
await app.prepare();
const server = createServer((request, response) => handle(request, response));
server.listen(port, '127.0.0.1', () => console.log(`CATMS local development: http://localhost:${port}`));
async function shutdown() {
  server.close();
  await app.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
