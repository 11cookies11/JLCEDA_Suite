# 远程桥接架构草案

## 目标

让运行在服务器端的 Codex 可以通过公网桥接服务连接在线的 JLCEDA 插件实例，并向其发送结构化桥接命令。

## 第一版拓扑

第一版采用“插件主动连接公网服务端”的拓扑：

1. `JLCEDA` 插件启动后主动连接 WebSocket 服务端
2. 插件发送 `agent.register`
3. 服务端维护在线会话表
4. 服务端 Codex 向指定在线插件下发 `bridge.request`
5. 插件执行本地桥接逻辑并回传 `bridge.response`

## 第一版消息类型

客户端到服务端：

- `agent.register`
- `agent.heartbeat`
- `bridge.response`
- `bridge.event`

服务端到客户端：

- `server.registered`
- `server.heartbeat_ack`
- `bridge.request`
- `server.error`

## 第一版安全策略

- 插件连接服务端时携带预共享 token
- 服务端校验 token 后才接受注册
- 写操作仍沿用桥接层已有的确认门禁
- 后续再补 TLS、会话授权和更细粒度权限控制

## 第一版实现范围

当前阶段只先交付：

- 服务端 WebSocket 连接管理
- 插件注册与心跳
- 指定会话的请求下发
- 响应回传与超时控制

下一阶段再接入：

- 插件侧 WebSocket 客户端
- 服务端对 Codex 的 API 层
- 实机公网联调
