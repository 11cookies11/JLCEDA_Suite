import process from 'node:process';
import { BridgeServer } from './bridge-server';
import { BridgeControlServer } from './control-server';

async function main(): Promise<void> {
  const port = Number(process.env.BRIDGE_SERVER_PORT ?? '8787');
  const host = process.env.BRIDGE_SERVER_HOST ?? '0.0.0.0';
  const authToken = process.env.BRIDGE_SERVER_TOKEN ?? '';
  const controlPortRaw = process.env.BRIDGE_SERVER_CONTROL_PORT;
  const controlHost = process.env.BRIDGE_SERVER_CONTROL_HOST ?? '127.0.0.1';
  const controlToken = process.env.BRIDGE_SERVER_CONTROL_TOKEN ?? '';

  const server = new BridgeServer({
    port,
    host,
    authToken,
  });

  await server.start();

  let controlServer: BridgeControlServer | undefined;

  if (controlPortRaw) {
    controlServer = new BridgeControlServer(server, {
      port: Number(controlPortRaw),
      host: controlHost,
      authToken: controlToken,
    });

    await controlServer.start();
  }

  console.log(`Bridge server listening on ws://${host}:${port}`);
  console.log(`Auth token enabled: ${authToken ? 'yes' : 'no'}`);
  if (controlServer) {
    console.log(`Control server listening on http://${controlHost}:${controlPortRaw}`);
    console.log(`Control token enabled: ${controlToken ? 'yes' : 'no'}`);
  }

  const shutdown = async () => {
    if (controlServer) {
      await controlServer.stop();
    }
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
