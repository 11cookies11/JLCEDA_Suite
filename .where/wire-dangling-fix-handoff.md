# wire_dangling 修复任务 — 交接给 Codex

## 背景

KiCadAgentSuite 管道为 NexDAP 项目生成 6 页层次化原理图。ERC 检查显示
**1 个 wire_dangling 错误**在 `02_02_esp32.kicad_sch`，其余全部通过。

## 问题定位

`02_02_esp32.kicad_sch` 中，晶振 Y_ESP32 pin2 到电容 C_ESP_XTAL2 的 L 形走线：

```
Y_ESP32(晶振) @ (60.96, 358.14)
  pin2 body (58.42, ~370) ───水平线─── (45.72, ~370)
                                        │
                                        │ 垂直线
                                        ▼
                              (45.72, 426.72) = C_ESP_XTAL2 pin1
```

KiCad 10.0 判定水平线段悬空——因为线头在 pin 的 **body 端**，
但 KiCad 10.0 要求连接到 **电气端**（body + pin_length 延伸方向的反方向）。

```
  body 端 ── 2.54mm(典型) ── 电气端
     ↑                           ↑
  线在这里                  KiCad 10.0 在这里找连接
  → 判定为悬空
```

## 根因

`endpoint_from_pin` (行 345) 返回 pin 的 **body 端**坐标。
`intra_module_wiring` + `_route_l_shape` 用这个坐标画元件间走线。
结果线画在 body 端，KiCad 10.0 不认。

## 需要修改的文件

**唯一文件：** `src/kicad_suite/kicad_project_writer.py`

### 修改 1 — 行 17：添加常量

在 `SYMBOL_PIN_CACHE` 后面加：

```python
PIN_LEN = 2.54  # standard KiCad pin line length, mm
```

### 修改 2 — 行 238-241：`symbol_block_for_lib_id` 加载真实符号

在 `load_installed_symbol` 返回空之后，`fallback_prefixes` 之前插入：

```python
        # Fall back to KiCad system library (e.g. Device:Crystal)
        system_block = installed_symbol_block(library, symbol_name)
        if system_block:
            return normalize_embedded_symbol_name(system_block, library, symbol_name)
```

这段让 `Device:Crystal`、`Device:LED` 等 KiCad 内置符号从系统库加载真实 pin 数据，而不是用 `local_two_pin_symbol` 编造假 pin 位置。嵌入原理图的符号和 `parse_symbol_pin_map` 读到的 pin 数据由此一致。

### 修改 3 — 行 405 前：添加 `_pin_length` 辅助函数

在 `def pin_endpoint(...` 之前插入：

```python
def _pin_length(symbol: dict[str, Any], pin_number: str) -> float:
    """Return the pin line length (mm) for a symbol's pin, default PIN_LEN."""
    lib_id = str(symbol.get('lib_id', ''))
    if not lib_id:
        return PIN_LEN
    pin_map = parse_symbol_pin_map(lib_id)
    pin_data = pin_map.get(pin_number) or pin_map.get(str(pin_number).strip().upper())
    if pin_data:
        return float(pin_data.get('length', PIN_LEN))
    return PIN_LEN
```

### 修改 4 — 行 690-692：桥接线（核心修复）

**现有代码：**
```python
            if (ref, pin_number) in suppress_labels and net_name not in force_global_nets:
                continue
            x, y, direction = pin_endpoint(symbol, pin_number)
            stub = 3.81
```

**替换为：**
```python
            x, y, direction = pin_endpoint(symbol, pin_number)
            # Bridge from body to electrical end so KiCad 10.0
            # recognises the wire-to-pin connection.
            pin_len = _pin_length(symbol, pin_number)
            ex, ey = x, y
            if direction == 0.0:
                ex -= pin_len
            elif direction == 180.0:
                ex += pin_len
            elif direction == 90.0:
                ey -= pin_len
            elif direction == 270.0:
                ey += pin_len
            if (ex, ey) != (x, y):
                blocks.append(f'''  (wire (pts (xy {fmt(x)} {fmt(y)}) (xy {fmt(ex)} {fmt(ey)}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )''')
            if (ref, pin_number) in suppress_labels and net_name not in force_global_nets:
                continue
            ex, ey, direction = x, y, direction  # keep original for label
            # Actually: use electrical end for label placement
            stub = 3.81
```

**关键**：桥接线必须在 `suppress_labels` 检查**之前**。因为被 suppress 的 pin 已经由 `intra_module_wiring` 走了内部 route，但那条 route 的线头在 body 端——桥接线把 body 连到电气端，KiCad 10.0 就能识别连接。

**注意**：上面的代码片段有逻辑错误。正确的写法是：桥接线用 body→electrical，标签线用 electrical→label。需要把 (x,y) 和 (ex,ey) 分开，标签位置基于 electrical 端。完整版本：

```python
            x, y, direction = pin_endpoint(symbol, pin_number)
            # Bridge wire: body -> electrical end
            pin_len = _pin_length(symbol, pin_number)
            ex, ey = x, y
            if direction == 0.0:
                ex -= pin_len
            elif direction == 180.0:
                ex += pin_len
            elif direction == 90.0:
                ey -= pin_len
            elif direction == 270.0:
                ey += pin_len
            if (ex, ey) != (x, y):
                blocks.append(f'''  (wire (pts (xy {fmt(x)} {fmt(y)}) (xy {fmt(ex)} {fmt(ey)}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )''')
            if (ref, pin_number) in suppress_labels and net_name not in force_global_nets:
                continue
            # Label wire: electrical end -> label
            stub = 3.81
            label_x = ex - stub if direction == 180.0 else ex + stub if direction == 0.0 else ex
            label_y = ey + stub if direction == 90.0 else ey - stub if direction == 270.0 else ey
            label_key = (net_name, round(label_x, 3), round(label_y, 3))
            kind = kind_map.get(net_name, 'signal')
            justify = 'right' if direction == 180.0 else 'left' if direction == 0.0 else 'center'
            justify_effect = f' (justify {justify})' if justify != 'center' else ''
            blocks.append(f'''  (wire (pts (xy {fmt(ex)} {fmt(ey)}) (xy {fmt(label_x)} {fmt(label_y)}))
    (stroke (width 0) (type default))
    (uuid {q(new_uuid())})
  )''')
            # ... label rendering continues below unchanged
```

### 修改 5 — 行 719-727：no_connect 符号覆盖

**现有代码只覆盖 `MCU_Espressif:ESP32-C3`。**

**替换为覆盖所有 `len(pin_map) > 2` 的多 pin 符号，且从库读取真实 pin 数据：**

```python
        lib_id_str = str(symbol.get('lib_id', ''))
        if lib_id_str:
            connected_pins = {str(pin.get('number', '')).strip() for pin in pins if isinstance(pin, dict)}
            try:
                pin_map = parse_symbol_pin_map(lib_id_str)
            except Exception:
                pin_map = {}
            if len(pin_map) > 2:  # only render no_connect for multi-pin symbols
                for pin_number in sorted(pin_map, key=lambda v: int(v) if v.isdigit() else v):
                    if pin_number in connected_pins:
                        continue
                    x, y, _direction = pin_endpoint(symbol, pin_number)
                    blocks.append(f'''  (no_connect (at {fmt(x)} {fmt(y)})
    (uuid {q(new_uuid())})
  )''')
    return '\n'.join(blocks)
```

## 验证方法

```bash
# 清理旧原理图
rm -f ".where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap/kicad-output-v13/nexdap_dual_chip_cmsis_dap/"*.kicad_sch

# 重新生成
KICAD_DISABLE_JLC_MCP=1 python scripts/kas.py pipeline \
  ".where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap/circuit-model.json" \
  ".where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap/kicad-output-v13"

# 检查 ERC（期望 0 errors）
python -c "
import json
from collections import Counter
with open('.where/nexdap-rp2040-esp32c3-isolated-wireless-cmsis-dap/kicad-output-v13/nexdap_dual_chip_cmsis_dap/nexdap_dual_chip_cmsis_dap.erc.json') as f:
    data = json.load(f)
all_v = [v for s in data['sheets'] for v in s['violations']]
errors = [v for v in all_v if v['severity']=='error']
print(f'{len(errors)} errors (target: 0)')
if errors:
    from collections import Counter
    print(dict(Counter(v['type'] for v in errors)))
"
```

## 注意事项

1. **不要在 `endpoint_from_pin` 里延伸 pin 长度**——那会改变走线起止点，破坏 `intra_module_wiring` 的 L 形路由。
2. **桥接线放在 suppress_labels 检查之前**——否则被内部 route 覆盖的 pin 不会得到桥接线。
3. **`_pin_length` 从库文件动态读取**——不同符号 pin 长度不同（晶振 1.27mm，标准 2.54mm），不能硬编码。
4. **`len(pin_map) > 2` 守卫**——2-pin 符号（LED、电阻、电容）不需要 no_connect，且 `parse_symbol_pin_map` 在 fallback 时可能产生错误数据。

## 当前仓库状态

- 分支：`develop`
- 工作区干净（所有有益修改已提交）
- 3 个 commit ahead of origin
- 唯一待修改文件：`src/kicad_suite/kicad_project_writer.py`
