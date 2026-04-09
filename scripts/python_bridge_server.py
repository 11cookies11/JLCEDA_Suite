#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import venv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_now() -> str:
    return utc_now().isoformat()


def write_json(status_code: int, body: Any) -> web.Response:
    return web.json_response(body, status=status_code)


def get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_cache_venv_dir() -> Path:
    return Path.home() / '.cache' / 'jlceda-aiagent-python-server'


def get_venv_python_path(venv_dir: Path) -> Path:
    if os.name == 'nt':
        return venv_dir / 'Scripts' / 'python.exe'
    return venv_dir / 'bin' / 'python'


def ensure_runtime_dependencies() -> None:
    try:
        __import__('aiohttp')
        return
    except ImportError:
        pass

    repo_root = get_repo_root()
    requirements_file = repo_root / 'requirements-server.txt'
    if not requirements_file.exists():
        raise RuntimeError(f'Missing requirements file: {requirements_file}')

    venv_dir = get_cache_venv_dir()
    python_path = get_venv_python_path(venv_dir)
    if not python_path.exists():
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        builder.create(str(venv_dir))

    probe = subprocess.run(
        [str(python_path), '-c', 'import aiohttp'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        subprocess.check_call([
            str(python_path),
            '-m',
            'pip',
            'install',
            '--upgrade',
            'pip',
        ])
        subprocess.check_call([
            str(python_path),
            '-m',
            'pip',
            'install',
            '-r',
            str(requirements_file),
        ])
    os.execv(
        str(python_path),
        [
            str(python_path),
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ],
    )


ensure_runtime_dependencies()

from aiohttp import WSMsgType, web


@dataclass
class BridgeSession:
    registration: dict[str, Any]
    websocket: web.WebSocketResponse
    connected_at: datetime
    last_seen_at: datetime


@dataclass
class PendingBridgeRequest:
    client_id: str
    future: asyncio.Future[dict[str, Any]]
    timeout_handle: asyncio.TimerHandle


class BridgeServer:
    def __init__(
        self,
        bridge_host: str,
        bridge_port: int,
        auth_token: str = '',
        request_timeout_ms: int = 15_000,
        control_host: str = '127.0.0.1',
        control_port: Optional[int] = None,
        control_token: str = '',
    ) -> None:
        self.bridge_host = bridge_host
        self.bridge_port = bridge_port
        self.auth_token = auth_token
        self.request_timeout_ms = request_timeout_ms
        self.control_host = control_host
        self.control_port = control_port
        self.control_token = control_token

        self.sessions: dict[str, BridgeSession] = {}
        self.socket_clients: dict[int, str] = {}
        self.pending_requests: dict[str, PendingBridgeRequest] = {}
        self._bridge_runner: web.AppRunner | None = None
        self._control_runner: web.AppRunner | None = None
        self._bridge_site: web.TCPSite | None = None
        self._control_site: web.TCPSite | None = None

    async def start(self) -> None:
        bridge_app = web.Application()
        bridge_app.router.add_route('*', '/{tail:.*}', self._handle_bridge_http_request)
        self._bridge_runner = web.AppRunner(bridge_app)
        await self._bridge_runner.setup()
        self._bridge_site = web.TCPSite(self._bridge_runner, self.bridge_host, self.bridge_port)
        await self._bridge_site.start()

        if self.control_port is not None:
            control_app = web.Application()
            control_app.router.add_get('/health', self._handle_control_health)
            control_app.router.add_get('/sessions', self._handle_control_sessions)
            control_app.router.add_post('/request', self._handle_control_request)
            self._control_runner = web.AppRunner(control_app)
            await self._control_runner.setup()
            self._control_site = web.TCPSite(self._control_runner, self.control_host, self.control_port)
            await self._control_site.start()

    async def stop(self) -> None:
        for pending in list(self.pending_requests.values()):
            if not pending.future.done():
                pending.future.set_exception(RuntimeError('Bridge server stopped before response was received.'))
            pending.timeout_handle.cancel()
        self.pending_requests.clear()

        for session in list(self.sessions.values()):
            await session.websocket.close()
        self.sessions.clear()
        self.socket_clients.clear()

        if self._control_runner is not None:
            await self._control_runner.cleanup()
            self._control_runner = None
            self._control_site = None

        if self._bridge_runner is not None:
            await self._bridge_runner.cleanup()
            self._bridge_runner = None
            self._bridge_site = None

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for session in self.sessions.values():
            registration = session.registration
            sessions.append({
                **registration,
                'connectedAt': session.connected_at.isoformat(),
                'lastSeenAt': session.last_seen_at.isoformat(),
            })
        return sessions

    async def send_bridge_request(self, client_id: str, request: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(client_id)
        if not session or session.websocket.closed:
            raise RuntimeError(f'Client is not connected: {client_id}')

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        def on_timeout() -> None:
            pending = self.pending_requests.pop(request['id'], None)
            if pending is not None and not pending.future.done():
                pending.future.set_exception(RuntimeError(f"Timed out waiting for bridge response: {request['id']}"))

        timeout_handle = loop.call_later(self.request_timeout_ms / 1000.0, on_timeout)
        self.pending_requests[request['id']] = PendingBridgeRequest(
            client_id=client_id,
            future=future,
            timeout_handle=timeout_handle,
        )

        await session.websocket.send_json({
            'type': 'bridge.request',
            'request': request,
        })

        try:
            return await future
        finally:
            pending = self.pending_requests.pop(request['id'], None)
            if pending is not None:
                pending.timeout_handle.cancel()

    async def _handle_bridge_http_request(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        can_prepare = ws.can_prepare(request)
        if not can_prepare.ok:
            raise web.HTTPNotFound()

        await ws.prepare(request)
        await self._handle_ws_connection(ws)
        return ws

    async def _handle_ws_connection(self, websocket: web.WebSocketResponse) -> None:
        async for message in websocket:
            if message.type == WSMsgType.TEXT:
                await self._handle_socket_message(websocket, message.data)
            elif message.type == WSMsgType.ERROR:
                break
        await self._handle_socket_close(websocket)

    async def _handle_socket_message(self, websocket: web.WebSocketResponse, raw_message: str) -> None:
        try:
            message = json.loads(raw_message)
        except Exception:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'INVALID_MESSAGE',
                'message': 'Failed to parse client message as JSON.',
            })
            return

        message_type = message.get('type')
        if message_type == 'agent.register':
            await self._handle_agent_register(websocket, message)
            return
        if message_type == 'agent.heartbeat':
            await self._handle_agent_heartbeat(websocket, message)
            return
        if message_type == 'bridge.response':
            await self._handle_bridge_response(message)
            return
        if message_type == 'bridge.event':
            return

        await websocket.send_json({
            'type': 'server.error',
            'code': 'INVALID_MESSAGE',
            'message': f'Unsupported client message type: {message_type or "unknown"}',
        })

    async def _handle_agent_register(self, websocket: web.WebSocketResponse, message: dict[str, Any]) -> None:
        token = message.get('token', '')
        if self.auth_token and token != self.auth_token:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'AUTH_FAILED',
                'message': 'Agent registration token is invalid.',
            })
            await websocket.close()
            return

        client = message.get('client') or {}
        client_id = str(client.get('clientId', ''))
        if not client_id:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'INVALID_MESSAGE',
                'message': 'client.clientId is required.',
            })
            await websocket.close()
            return

        existing_session = self.sessions.get(client_id)
        if existing_session is not None:
            await existing_session.websocket.close()
            self.socket_clients.pop(id(existing_session.websocket), None)

        session = BridgeSession(
            registration=client,
            websocket=websocket,
            connected_at=utc_now(),
            last_seen_at=utc_now(),
        )
        self.sessions[client_id] = session
        self.socket_clients[id(websocket)] = client_id

        await websocket.send_json({
            'type': 'server.registered',
            'clientId': client_id,
            'session': {
                **client,
                'connectedAt': session.connected_at.isoformat(),
                'lastSeenAt': session.last_seen_at.isoformat(),
            },
        })

    async def _handle_agent_heartbeat(self, websocket: web.WebSocketResponse, message: dict[str, Any]) -> None:
        client_id = self.socket_clients.get(id(websocket))
        if not client_id or client_id != message.get('clientId'):
            await websocket.send_json({
                'type': 'server.error',
                'code': 'UNKNOWN_CLIENT',
                'message': 'Heartbeat received before agent registration.',
            })
            return

        session = self.sessions.get(client_id)
        if session is None:
            await websocket.send_json({
                'type': 'server.error',
                'code': 'UNKNOWN_CLIENT',
                'message': f'No active session found for {client_id}.',
            })
            return

        timestamp = str(message.get('timestamp') or isoformat_now())
        try:
            session.last_seen_at = datetime.fromisoformat(timestamp)
        except Exception:
            session.last_seen_at = utc_now()

        await websocket.send_json({
            'type': 'server.heartbeat_ack',
            'clientId': client_id,
            'timestamp': isoformat_now(),
        })

    async def _handle_bridge_response(self, message: dict[str, Any]) -> None:
        response = message.get('response') or {}
        request_id = response.get('id')
        client_id = message.get('clientId')
        if not request_id or not client_id:
            return

        pending = self.pending_requests.get(request_id)
        if pending is None or pending.client_id != client_id:
            return

        self.pending_requests.pop(request_id, None)
        pending.timeout_handle.cancel()
        if not pending.future.done():
            pending.future.set_result(response)

    async def _handle_socket_close(self, websocket: web.WebSocketResponse) -> None:
        client_id = self.socket_clients.pop(id(websocket), None)
        if not client_id:
            return

        self.sessions.pop(client_id, None)
        for request_id, pending in list(self.pending_requests.items()):
            if pending.client_id != client_id:
                continue
            pending.timeout_handle.cancel()
            if not pending.future.done():
                pending.future.set_exception(RuntimeError('Bridge session closed before response was received.'))
            self.pending_requests.pop(request_id, None)

    def _is_authorized(self, request: web.Request) -> bool:
        if not self.control_token:
            return True
        header_token = request.headers.get('x-bridge-control-token', '')
        return header_token == self.control_token

    async def _handle_control_health(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})
        return write_json(200, {'ok': True})

    async def _handle_control_sessions(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})
        return write_json(200, {'sessions': self.list_sessions()})

    async def _handle_control_request(self, request: web.Request) -> web.Response:
        if not self._is_authorized(request):
            return write_json(401, {'error': 'unauthorized'})

        try:
            body = await request.json()
        except Exception:
            body = {}

        client_id = body.get('clientId') if isinstance(body, dict) else None
        bridge_request = body.get('request') if isinstance(body, dict) else None
        if not client_id or not bridge_request:
            return write_json(400, {
                'error': 'invalid_request',
                'message': 'clientId and request are required.',
            })

        try:
            response = await self.send_bridge_request(str(client_id), bridge_request)
            return write_json(200, {'response': response})
        except Exception as error:
            return write_json(500, {
                'error': 'request_failed',
                'message': str(error),
            })


async def main() -> None:
    bridge_port = int(os.environ.get('BRIDGE_SERVER_PORT', '8787'))
    bridge_host = os.environ.get('BRIDGE_SERVER_HOST', '0.0.0.0')
    auth_token = os.environ.get('BRIDGE_SERVER_TOKEN', '')
    request_timeout_ms = int(os.environ.get('BRIDGE_SERVER_REQUEST_TIMEOUT_MS', '15000'))
    control_port_raw = os.environ.get('BRIDGE_SERVER_CONTROL_PORT')
    control_port = int(control_port_raw) if control_port_raw else None
    control_host = os.environ.get('BRIDGE_SERVER_CONTROL_HOST', '127.0.0.1')
    control_token = os.environ.get('BRIDGE_SERVER_CONTROL_TOKEN', '')

    server = BridgeServer(
        bridge_host=bridge_host,
        bridge_port=bridge_port,
        auth_token=auth_token,
        request_timeout_ms=request_timeout_ms,
        control_host=control_host,
        control_port=control_port,
        control_token=control_token,
    )
    await server.start()

    print(f'Bridge server listening on ws://{bridge_host}:{bridge_port}')
    print(f'Auth token enabled: {"yes" if auth_token else "no"}')
    if control_port is not None:
        print(f'Control server listening on http://{control_host}:{control_port}')
        print(f'Control token enabled: {"yes" if control_token else "no"}')

    stop_event = asyncio.Event()

    def request_shutdown() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig_name in ('SIGINT', 'SIGTERM'):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, request_shutdown)
            except NotImplementedError:
                signal.signal(sig, lambda *_: request_shutdown())

    await stop_event.wait()
    await server.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
