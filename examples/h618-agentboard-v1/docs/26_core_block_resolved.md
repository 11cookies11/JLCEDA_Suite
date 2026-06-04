# H618 核心块已解决说明

这份文档记录已经从“待确认”切换为“已解决”的四个核心块：

## 已解决

- `U2 H618` 的 pinmap、启动脚位、复位脚位、外设脚位
- `U3 LPDDR4` 的当前 V1 拓扑
- `U1 PMIC` 的电源树、上电顺序和复位/使能节奏
- `RGMII / USB Hub / HDMI / USB-C` 的器件级边界

## 现在可以怎么理解

- 这些块已经不再作为“未完成风险”处理。
- 它们仍然可以在未来 revision 中重做，但当前 V1 已经完成收口。
- 对下单打样来说，它们现在按“已落实输入”看待，而不是按“待确认项”看待。

## 关联文件

- [source/circuit-model.source.json](../source/circuit-model.source.json)
- [25_procurement_ready.md](25_procurement_ready.md)
- [24_final_review_package.md](24_final_review_package.md)
