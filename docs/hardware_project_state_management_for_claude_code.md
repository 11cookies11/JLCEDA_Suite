# 硬件 DSL → Pipeline → KiCad 工具链：项目状态管理开发说明

面向：Claude Code / AI Agent 开发任务

## 1. 项目背景

当前项目已经实现：

```text
DSL → pipeline → KiCad project
```

现在需要增加 **Project State Management / 项目状态管理**，让 AI Agent、CLI、API、pipeline 都能清楚知道当前硬件项目的状态。

核心目标：

> 把硬件项目从“文件集合”升级成“可被 AI Agent 理解、操作、验证和持续迭代的工程对象”。

---

## 2. 为什么需要项目状态管理

AI Agent 需要知道：

1. 当前项目是什么。
2. 当前用了哪些硬件模块 pack。
3. 当前 DSL 是否有效。
4. 当前 KiCad 工程是否是最新生成的。
5. 上次 validate 是否通过。
6. 上次 build 是否成功。
7. 当前有哪些 errors / warnings。
8. 哪些 GPIO / 元件 / 网络已经被占用。
9. 哪些内容已经被锁定，不能随便变化。
10. AI Agent 或用户上次做了什么修改。

没有状态管理，Agent 容易重复添加模块、修改已锁定引脚、不知道 KiCad 已经过期，或者不知道当前 DSL 是否已经被手动改过。

---

## 3. 目标架构

当前：

```text
hardware.yaml
    ↓
pipeline
    ↓
KiCad project
```

目标：

```text
hardware.yaml
project.lock.yaml
project.state.json
build/report.json
logs/operations.jsonl
        ↓
ProjectState
        ↓
API / CLI / AI Agent
        ↓
pipeline
        ↓
KiCad project
```

文件职责：

| 文件 | 作用 |
|---|---|
| `hardware.yaml` | 设计意图，用户/AI 可读的 DSL |
| `project.lock.yaml` | 锁定关键工程事实，防止重复生成结果乱变 |
| `project.state.json` | 当前状态快照，给 API/CLI/Agent 读取 |
| `build/ir.json` | DSL 编译后的中间表示 |
| `build/report.json` | validate/build/ERC/DRC 结果 |
| `logs/operations.jsonl` | 操作历史 |

---

## 4. 推荐项目目录结构

```text
esp32_s3_sidekey_console/
├── hardware.yaml
├── project.lock.yaml
├── project.state.json
├── build/
│   ├── ir.json
│   ├── report.json
│   ├── bom.csv
│   └── kicad/
│       ├── xxx.kicad_pro
│       ├── xxx.kicad_sch
│       └── xxx.kicad_pcb
├── logs/
│   └── operations.jsonl
└── docs/
    └── summary.md
```

---

## 5. 三个核心文件

### 5.1 hardware.yaml：设计意图

```yaml
project:
  name: esp32_s3_sidekey_console

mcu:
  part: ESP32-S3-WROOM-1-N16R8

display:
  type: spi_tft
  driver: ST7789
  size: 1.69

buttons:
  type: side_tactile
  count: 4

expansion:
  type: pogo_pin
  pins: 10
```

它表达的是：我要做什么硬件。

### 5.2 project.lock.yaml：工程锁定事实

```yaml
components:
  U1:
    part: ESP32-S3-WROOM-1-N16R8
    footprint: RF_Module:ESP32-S3-WROOM-1
    locked: true

pinmap:
  LCD_SCLK: GPIO12
  LCD_MOSI: GPIO11
  LCD_CS: GPIO10
  LCD_DC: GPIO9
  LCD_RST: GPIO8
  LCD_BL: GPIO7

refs:
  esp32_s3_core.mcu: U1
  usb_c_power.connector: J1
  display.connector: J2
```

它表达的是：已经确定下来的工程事实。

作用：保持 refdes、GPIO、footprint 稳定，防止每次 build 自动变化。

### 5.3 project.state.json：状态快照

```json
{
  "project": {
    "id": "esp32_s3_sidekey_console",
    "name": "ESP32-S3 SideKey Console",
    "version": "0.1.0"
  },
  "status": "DIRTY",
  "dsl": {
    "path": "hardware.yaml",
    "valid": null,
    "hash": "8a91f3c2"
  },
  "lock": {
    "path": "project.lock.yaml",
    "hash": "b129ac11"
  },
  "summary": {
    "mcu": "ESP32-S3-WROOM-1-N16R8",
    "display": "1.69 inch ST7789 SPI",
    "buttons": 4,
    "expansion": "10-pin pogo",
    "components": 38,
    "nets": 42
  },
  "build": {
    "last_build_ok": false,
    "input_dsl_hash": null,
    "input_lock_hash": null,
    "outputs": {}
  },
  "diagnostics": {
    "errors": 0,
    "warnings": 0,
    "items": []
  }
}
```

它表达的是：当前项目处于什么状态。

---

## 6. Single Source of Truth

请按下面规则设计：

```text
hardware.yaml + project.lock.yaml = 事实来源
project.state.json = 状态缓存 / 状态快照
build/ir.json = 构建产物
build/report.json = 构建和验证反馈
```

`project.state.json` 不应该成为主要源码。它应该可以被删除，然后通过 `hardware.yaml + project.lock.yaml + build/report.json` 重新生成。

---

## 7. 项目状态类型

| 状态 | 含义 |
|---|---|
| `INIT` | 项目刚创建 |
| `DIRTY` | 项目被修改了，但还没有重新验证 |
| `VALID` | DSL 和规则检查通过 |
| `INVALID` | DSL 或规则检查失败 |
| `BUILT` | KiCad 已生成，并且是最新的 |
| `STALE` | DSL 或 lock 改了，但 KiCad 还是旧的 |
| `BUILD_FAILED` | 上次构建失败 |

状态流转：

```text
create_project → INIT
add_pack / set_param / patch_dsl → DIRTY
validate 成功 → VALID
validate 失败 → INVALID
build 成功 → BUILT
build 失败 → BUILD_FAILED
build 后 hardware.yaml 或 project.lock.yaml 被修改 → STALE
```

关键判断：

```text
current_dsl_hash != build.input_dsl_hash
或
current_lock_hash != build.input_lock_hash
→ status = STALE
```

---

## 8. 需要管理的信息

至少包含：

1. 项目基础信息：id、name、version、dsl_version、generator_version。
2. DSL 状态：path、valid、hash、last_validated_at。
3. Lock 状态：path、hash。
4. Pack / 模块状态：name、version、enabled、options。
5. 元件摘要：ref、type、part、pack、locked。
6. 网络 / 接口摘要：nets、interfaces。
7. 引脚分配状态：signal → pin、owner、locked。
8. Build 状态：last_build_ok、last_build_at、input hashes、outputs。
9. Diagnostics 状态：errors、warnings、items。
10. 操作历史：operations.jsonl。

---

## 9. 操作历史

写入：

```text
logs/operations.jsonl
```

每一行是一条 JSON：

```json
{"time":"2026-05-27T10:10:00","actor":"agent","op":"add_pack","pack":"esp32_s3_core","ok":true}
{"time":"2026-05-27T10:12:00","actor":"agent","op":"set_param","path":"display.size","old":1.47,"new":1.69,"ok":true}
{"time":"2026-05-27T10:15:00","actor":"agent","op":"validate","errors":1,"warnings":2}
```

用途：追踪 AI Agent 改了什么、debug、生成变更记录、未来支持 rollback。

---

## 10. 需要实现的核心类

```python
class ProjectState:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.state = {}

    def load(self) -> dict:
        """Load project.state.json."""

    def save(self) -> None:
        """Save project.state.json."""

    def recompute(self) -> dict:
        """
        Recompute project state from:
        - hardware.yaml
        - project.lock.yaml
        - build/ir.json
        - build/report.json
        """

    def get_status(self) -> dict:
        """Return short project status."""

    def get_summary(self) -> dict:
        """Return project summary."""

    def mark_dirty(self, reason: str) -> None:
        """Mark project as DIRTY."""

    def mark_valid(self, diagnostics: dict) -> None:
        """Mark project as VALID."""

    def mark_invalid(self, diagnostics: dict) -> None:
        """Mark project as INVALID."""

    def mark_built(self, outputs: dict, input_hashes: dict) -> None:
        """Mark project as BUILT."""

    def mark_build_failed(self, diagnostics: dict) -> None:
        """Mark project as BUILD_FAILED."""

    def is_stale(self) -> bool:
        """Return true if current DSL/lock hash differs from build input hash."""

    def append_operation(self, op: dict) -> None:
        """Append one line to logs/operations.jsonl."""
```

---

## 11. Hash 计算

需要实现：

```python
def hash_file(path: str) -> str:
    """Return stable hash for a file."""

def hash_json_or_yaml(data: dict) -> str:
    """Return stable hash for normalized dict."""
```

建议读取 YAML/JSON 后 normalize 再 hash，避免字段顺序、空格导致 hash 不稳定。

---

## 12. 状态判断逻辑

```python
def compute_status(state):
    if not state_exists:
        return "INIT"

    if current_dsl_hash != build_input_dsl_hash:
        return "STALE"

    if current_lock_hash != build_input_lock_hash:
        return "STALE"

    if diagnostics.errors > 0:
        return "INVALID"

    if build.last_build_ok and hashes_match:
        return "BUILT"

    if dsl.valid:
        return "VALID"

    return "DIRTY"
```

`STALE` 的优先级应该比较高，因为 build 产物过期对 Agent 很重要。

---

## 13. 需要暴露的 CLI / API

第一版建议支持：

```bash
hwtool status
hwtool inspect
hwtool explain
hwtool report
hwtool history
hwtool diff
hwtool validate
hwtool build
```

命令含义：

| 命令 | 作用 |
|---|---|
| `hwtool status` | 返回项目当前状态、是否需要 validate/build |
| `hwtool inspect` | 返回结构化摘要，包括 MCU、屏幕、KiCad resources、pinmap 等 |
| `hwtool explain` | 返回自然语言摘要，方便 AI Agent 快速理解项目 |
| `hwtool report` | 返回 diagnostics，包括 errors/warnings/suggestions |
| `hwtool history` | 读取 operations.jsonl 操作历史 |
| `hwtool diff` | 返回上次 build 后发生的变化 |
| `hwtool validate` | 运行 DSL/IR/规则检查并更新状态 |
| `hwtool build` | 运行 pipeline 生成 KiCad 并更新 build 状态 |

---

## 14. MVP 完成范围

第一阶段先实现：

1. project.state.json 读写。
2. hardware.yaml hash。
3. project.lock.yaml hash。
4. 状态类型：INIT / DIRTY / VALID / INVALID / BUILT / STALE / BUILD_FAILED。
5. mark_dirty / mark_valid / mark_invalid / mark_built / mark_build_failed / is_stale。
6. operations.jsonl 日志。
7. status / inspect / explain / report CLI。

MVP 版 `project.state.json`：

```json
{
  "project": {
    "id": "esp32_s3_sidekey_console",
    "name": "ESP32-S3 SideKey Console"
  },
  "status": "DIRTY",
  "dsl": {
    "hash": "8a91f3c2",
    "valid": null
  },
  "lock": {
    "hash": "b129ac11"
  },
  "build": {
    "last_build_ok": false,
    "input_dsl_hash": null,
    "input_lock_hash": null
  },
  "diagnostics": {
    "errors": 0,
    "warnings": 0,
    "items": []
  }
}
```

---

## 15. 实现步骤

1. 新增 ProjectState 类：load/save/recompute/get_status/get_summary/mark_*。
2. 实现 hash_file、hash_yaml_normalized、hash_json_normalized。
3. 在项目目录自动创建和更新 project.state.json。
4. 接入现有 pipeline：build 成功 mark_built，失败 mark_build_failed。
5. 接入 validate：成功 mark_valid，失败 mark_invalid。
6. 接入 API 修改操作：add_pack/set_param/patch_dsl/remove_pack → mark_dirty。
7. 实现 CLI：status/inspect/explain/report/history/diff。

---

## 16. Agent 工作流目标

最终 AI Agent 应该这样工作：

```text
1. hwtool status
2. hwtool inspect
3. 判断当前项目是否 DIRTY / STALE / INVALID
4. 如果需要，运行 hwtool validate
5. 如果 validate 通过，运行 hwtool build
6. 读取 hwtool report
7. 根据 diagnostics 继续修复
8. 记录所有操作历史
```

---

## 17. 设计原则

1. hardware.yaml 是设计意图。
2. project.lock.yaml 是工程锁定事实。
3. project.state.json 是状态快照，不是主要源码。
4. build/report.json 是验证反馈。
5. 所有 API 操作后都必须更新状态。
6. 所有 build 都要记录输入 hash。
7. hash 不一致时必须标记 STALE。
8. Agent 不应该靠猜文件状态，而应该通过 status / inspect / report 获取上下文。
9. diagnostics 必须结构化，方便 AI 自动修复。
10. operations.jsonl 必须记录 Agent 做过的关键操作。

---

## 18. 完成标准

完成后应满足：

1. 新建项目后存在 project.state.json。
2. 修改 hardware.yaml 后 status 能识别 STALE 或 DIRTY。
3. validate 成功后状态变成 VALID。
4. validate 失败后状态变成 INVALID，并记录 diagnostics。
5. build 成功后状态变成 BUILT，并记录 input_dsl_hash / input_lock_hash。
6. build 后再次修改 DSL，状态变成 STALE。
7. hwtool status 能返回当前状态。
8. hwtool inspect 能返回项目摘要。
9. hwtool explain 能返回自然语言说明。
10. hwtool history 能读取操作日志。

---

## 19. 一句话总结

本功能的目标是：

> 为现有 DSL → pipeline → KiCad 工具链增加项目状态管理层，使 AI Agent 能够稳定地理解、修改、验证和构建硬件项目，而不是盲目操作 DSL 或 KiCad 文件。
