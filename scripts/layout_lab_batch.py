#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "scripts" / "layout_lab.py"
SAMPLES = [
    (
        "样本 1：MCU 核心块",
        ROOT / "examples" / "layout-lab" / "samples" / "sample_mcu_core.json",
        ROOT / "tmp" / "layout-lab-sample-mcu-core",
    ),
    (
        "样本 2：电源 + USB",
        ROOT / "examples" / "layout-lab" / "samples" / "sample_power_usb.json",
        ROOT / "tmp" / "layout-lab-sample-power-usb",
    ),
    (
        "样本 3：RF + 调试",
        ROOT / "examples" / "layout-lab" / "samples" / "sample_rf_debug.json",
        ROOT / "tmp" / "layout-lab-sample-rf-debug",
    ),
]


def run_sample(scenario: Path, out_dir: Path) -> None:
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(LAB),
            "--scenario",
            str(scenario),
            "--out",
            str(out_dir),
        ],
        check=True,
    )


def build_gallery() -> None:
    gallery_dir = ROOT / "tmp" / "layout-lab-gallery"
    gallery_dir.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for title, out_dir, description in [
        ("样本 1：MCU 核心块", ROOT / "tmp" / "layout-lab-sample-mcu-core", "中心簇 + 指示灯边缘区"),
        ("样本 2：电源 + USB", ROOT / "tmp" / "layout-lab-sample-power-usb", "电源链 + USB 接口链 + 边缘连接器"),
        ("样本 3：RF + 调试", ROOT / "tmp" / "layout-lab-sample-rf-debug", "模拟岛 + RF 岛 + keepout + 调试口 + 差分对"),
    ]:
        cards.append(
            f"""
            <section class="card">
              <header>
                <h2>{title}</h2>
                <div class="meta">{description}</div>
              </header>
              <iframe src="../{out_dir.name}/final.svg"></iframe>
              <div class="links">
                <a href="../{out_dir.name}/final.svg">打开最终图</a>
                <a href="../{out_dir.name}/steps.html">查看步骤总览</a>
                <a href="../{out_dir.name}/layout-summary.json">查看摘要 JSON</a>
                <a href="../{out_dir.name}/report.md">查看报告</a>
              </div>
            </section>
            """
        )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Layout Lab 图纸看板</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --border: #dbe4ee;
      --text: #0f172a;
      --muted: #475569;
      --accent: #2563eb;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
      color: var(--text);
    }}
    header.page {{
      padding: 24px 28px 12px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    .page p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 18px;
      padding: 18px 24px 28px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
      overflow: hidden;
    }}
    .card header {{
      padding: 16px 18px 12px;
    }}
    .card h2 {{
      margin: 0 0 6px;
      font-size: 18px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    iframe {{
      display: block;
      width: 100%;
      height: 640px;
      border: 0;
      background: white;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 0 18px 18px;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <header class="page">
    <h1>Layout Lab 图纸看板</h1>
    <p>这里汇总了三个测试样本的最终排布图，方便快速对比中心簇、电源/USB 链路，以及 RF / 调试区的布局风格。</p>
  </header>

  <main class="grid">
    {''.join(cards)}
  </main>
</body>
</html>
"""
    (gallery_dir / "index.html").write_text(html, encoding="utf-8")


def build_steps_overview(sample_title: str, out_dir: Path) -> None:
    steps_dir = out_dir / "steps"
    step_files = sorted(steps_dir.glob("*.svg"))
    cards = []
    for step in step_files:
        cards.append(
            f"""
            <figure class="step-card">
              <figcaption>{step.name}</figcaption>
              <iframe src="./steps/{step.name}"></iframe>
            </figure>
            """
        )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{sample_title} - 步骤总览</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --panel: #ffffff;
      --border: #dbe4ee;
      --text: #0f172a;
      --muted: #475569;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
      color: var(--text);
    }}
    header {{
      padding: 24px 28px 12px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 16px;
      padding: 18px 24px 28px;
    }}
    .step-card {{
      margin: 0;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
      overflow: hidden;
    }}
    .step-card figcaption {{
      padding: 10px 12px;
      font-size: 13px;
      color: var(--muted);
      border-bottom: 1px solid var(--border);
    }}
    iframe {{
      display: block;
      width: 100%;
      height: 360px;
      border: 0;
      background: white;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{sample_title} - 步骤总览</h1>
    <p>这里汇总了每一步的摆放过程，方便对比候选位置、失败原因和最终选中结果。</p>
  </header>
  <main class="grid">
    {''.join(cards)}
  </main>
</body>
</html>
"""
    (out_dir / "steps.html").write_text(html, encoding="utf-8")


def main() -> int:
    for _, scenario, out_dir in SAMPLES:
        run_sample(scenario, out_dir)
    for title, _, out_dir in SAMPLES:
        build_steps_overview(title, out_dir)
    build_gallery()
    print("layout-lab batch completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
