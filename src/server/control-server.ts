import type { IncomingMessage, ServerResponse } from 'node:http';
import type { BridgeRequest, BridgeResponse } from '../bridge/protocol';
import type { BridgeServer } from './bridge-server';
import { Buffer } from 'node:buffer';
import * as http from 'node:http';

export interface BridgeControlServerOptions {
  host?: string;
  port: number;
  authToken?: string;
}

interface ControlRequestBody {
  clientId: string;
  request: BridgeRequest;
}

function readJsonBody(request: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];

    request.on('data', (chunk) => {
      chunks.push(Buffer.from(chunk));
    });

    request.on('end', () => {
      const rawBody = Buffer.concat(chunks).toString('utf8');

      if (!rawBody.trim()) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(rawBody) as unknown);
      }
      catch (error) {
        reject(error);
      }
    });

    request.on('error', reject);
  });
}

function writeJson(response: ServerResponse, statusCode: number, body: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('content-type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(body));
}

export class BridgeControlServer {
  private readonly options: Required<BridgeControlServerOptions>;
  private readonly bridgeServer: BridgeServer;
  private readonly server: http.Server;

  constructor(bridgeServer: BridgeServer, options: BridgeControlServerOptions) {
    this.bridgeServer = bridgeServer;
    this.options = {
      host: options.host ?? '127.0.0.1',
      port: options.port,
      authToken: options.authToken ?? '',
    };

    this.server = http.createServer((request, response) => {
      void this.handleRequest(request, response);
    });
  }

  async start(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      this.server.once('error', reject);
      this.server.listen(this.options.port, this.options.host, () => {
        resolve();
      });
    });
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      this.server.close((error) => {
        if (error) {
          reject(error);
          return;
        }

        resolve();
      });
    });
  }

  private isAuthorized(request: IncomingMessage): boolean {
    if (!this.options.authToken) {
      return true;
    }

    const headerToken = request.headers['x-bridge-control-token'];

    if (typeof headerToken !== 'string') {
      return false;
    }

    return headerToken === this.options.authToken;
  }

  private async handleRequest(request: IncomingMessage, response: ServerResponse): Promise<void> {
    if (!this.isAuthorized(request)) {
      writeJson(response, 401, {
        error: 'unauthorized',
      });
      return;
    }

    const url = new URL(request.url ?? '/', `http://${request.headers.host ?? `${this.options.host}:${this.options.port}`}`);

    if (request.method === 'GET' && url.pathname === '/health') {
      writeJson(response, 200, {
        ok: true,
      });
      return;
    }

    if (request.method === 'GET' && url.pathname === '/sessions') {
      writeJson(response, 200, {
        sessions: this.bridgeServer.listSessions(),
      });
      return;
    }

    if (request.method === 'POST' && url.pathname === '/request') {
      try {
        const body = (await readJsonBody(request)) as Partial<ControlRequestBody>;

        if (!body.clientId || !body.request) {
          writeJson(response, 400, {
            error: 'invalid_request',
            message: 'clientId and request are required.',
          });
          return;
        }

        const bridgeResponse: BridgeResponse = await this.bridgeServer.sendBridgeRequest(body.clientId, body.request);

        writeJson(response, 200, {
          response: bridgeResponse,
        });
      }
      catch (error) {
        writeJson(response, 500, {
          error: 'request_failed',
          message: error instanceof Error ? error.message : 'Unknown control request failure.',
        });
      }

      return;
    }

    writeJson(response, 404, {
      error: 'not_found',
    });
  }
}
