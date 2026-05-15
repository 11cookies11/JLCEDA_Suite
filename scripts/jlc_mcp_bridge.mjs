#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");
const localServer = resolve(repoRoot, "node_modules", "@jlcpcb", "mcp", "dist", "index.js");

function usage(exitCode = 0) {
  const out = exitCode === 0 ? console.log : console.error;
  out(`Usage:
  node scripts/jlc_mcp_bridge.mjs list-tools
  node scripts/jlc_mcp_bridge.mjs search --query <text> [--source lcsc|community] [--limit 10] [--in-stock] [--basic-only]
  node scripts/jlc_mcp_bridge.mjs install --id <Cxxxxx> [--project-path <path>] [--include-3d]
  node scripts/jlc_mcp_bridge.mjs fix --id <Cxxxxx> --corrections-json <json> [--project-path <path>] [--force]
`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const result = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      result._.push(token);
      continue;
    }
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      result[key] = true;
      continue;
    }
    result[key] = next;
    i += 1;
  }
  return result;
}

function parseJsonishText(text) {
  const trimmed = text.trim();
  if (!trimmed) {
    return text;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    const first = trimmed.search(/[\[{]/);
    const lastObj = trimmed.lastIndexOf("}");
    const lastArr = trimmed.lastIndexOf("]");
    const last = Math.max(lastObj, lastArr);
    if (first >= 0 && last > first) {
      try {
        return JSON.parse(trimmed.slice(first, last + 1));
      } catch {
        return text;
      }
    }
    return text;
  }
}

function normalizeToolResult(result) {
  if (result.structuredContent) {
    return result.structuredContent;
  }
  if (Array.isArray(result.content) && result.content.length === 1 && result.content[0]?.type === "text") {
    return parseJsonishText(result.content[0].text ?? "");
  }
  return result;
}

function serverParams() {
  if (process.env.JLC_MCP_COMMAND) {
    return {
      command: process.env.JLC_MCP_COMMAND,
      args: process.env.JLC_MCP_ARGS ? JSON.parse(process.env.JLC_MCP_ARGS) : [],
      cwd: repoRoot,
      stderr: "pipe",
    };
  }
  if (existsSync(localServer)) {
    return {
      command: process.execPath,
      args: [localServer],
      cwd: repoRoot,
      stderr: "pipe",
    };
  }
  return {
    command: "npx",
    args: ["-y", "@jlcpcb/mcp@0.3.2"],
    cwd: repoRoot,
    stderr: "pipe",
  };
}

async function withClient(fn) {
  const transport = new StdioClientTransport(serverParams());
  const stderr = [];
  transport.stderr?.on("data", (chunk) => {
    stderr.push(String(chunk));
  });

  const client = new Client({ name: "kicad-agent-suite-jlc-bridge", version: "0.1.0" });
  try {
    await client.connect(transport);
    return await fn(client);
  } finally {
    await transport.close().catch(() => undefined);
    if (process.env.JLC_MCP_DEBUG === "1" && stderr.length) {
      console.error(stderr.join(""));
    }
  }
}

const args = parseArgs(process.argv.slice(2));
const command = args._[0];

if (!command || args.help) {
  usage(command ? 0 : 1);
}

try {
  const output = await withClient(async (client) => {
    if (command === "list-tools") {
      return await client.listTools();
    }

    if (command === "search") {
      if (!args.query) {
        usage(1);
      }
      const result = await client.callTool({
        name: "component_search",
        arguments: {
          query: String(args.query),
          source: args.source ? String(args.source) : "lcsc",
          in_stock: Boolean(args["in-stock"]),
          basic_only: Boolean(args["basic-only"]),
          limit: Number(args.limit ?? 10),
        },
      });
      return normalizeToolResult(result);
    }

    if (command === "install") {
      if (!args.id) {
        usage(1);
      }
      const toolArgs = {
        id: String(args.id),
        include_3d: Boolean(args["include-3d"]),
        force: Boolean(args.force),
      };
      if (args["project-path"]) {
        toolArgs.project_path = resolve(String(args["project-path"]));
      }
      const result = await client.callTool({
        name: "library_install",
        arguments: toolArgs,
      });
      return normalizeToolResult(result);
    }

    if (command === "fix") {
      if (!args.id || !args["corrections-json"]) {
        usage(1);
      }
      const toolArgs = {
        lcsc_id: String(args.id),
        corrections: JSON.parse(String(args["corrections-json"])),
        force: Boolean(args.force),
      };
      if (args["project-path"]) {
        toolArgs.project_path = resolve(String(args["project-path"]));
      }
      const result = await client.callTool({
        name: "library_fix",
        arguments: toolArgs,
      });
      return normalizeToolResult(result);
    }

    usage(1);
  });

  console.log(JSON.stringify({ ok: true, result: output }, null, 2));
} catch (error) {
  console.log(JSON.stringify({
    ok: false,
    error: error instanceof Error ? error.message : String(error),
  }, null, 2));
  process.exit(1);
}
