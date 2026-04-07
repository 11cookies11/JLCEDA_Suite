import process from 'node:process';
import { BridgeServer } from './bridge-server';

async function main(): Promise<void> {
  const port = Number(process.env.BRIDGE_SERVER_PORT ?? '8787');
  const host = process.env.BRIDGE_SERVER_HOST ?? '0.0.0.0';
  const authToken = process.env.BRIDGE_SERVER_TOKEN ?? '';

  const server = new BridgeServer({
    port,
    host,
    authToken,
  });

  await server.start();

  console.log(`Bridge server listening on ws://${host}:${port}`);
  console.log(`Auth token enabled: ${authToken ? 'yes' : 'no'}`);

  const shutdown = async () => {
    await server.stop();
    process.exit(0);
  };

  process.once('SIGINT', () => {
    void shutdown();
  });

  process.once('SIGTERM', () => {
    void shutdown();
  });
}

main().catch((error) => {
  console.error('Bridge server failed to start.');
  console.error(error);
  process.exit(1);
});
