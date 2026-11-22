# 数据字典

| 输入表 | 关键字段 | 单位及约束 |
|---|---|---|
| config | batch、root、start、end、supply、unit、quantum_l | 批号和渠名为文本，最小刻度为正整升，渠首供水为非负整升 |
| gates | channel、start、end、state | 状态 `open` 或 `closed`，闸令须完整覆盖轮灌区间 |
| channels | channel、parent、inflow、loss、unit | 渠首上游为 `null`，损耗不超过入流，子渠入流和不超过上游净流量 |
| rights | outlet、channel、version、start、end、minimum、ceiling、unit、priority、weight | 保留编码前导零，保底和上限按最小刻度填报，优先级 1 最高，权重为正整数 |

时间含偏移，计算统一为 UTC，采用左闭右开区间。水量支持 `L`、`m3`、`m³`，千位分隔符须成组。空串、水量哨兵和小数升拒收。结果 `_l` 为升，理论配额可为精确分数字符串。

同一渠道按实测子渠入流与损耗计算本段可用量。先按优先级保底，同优先级短缺按保底值比例。所有级别保底后才按级别和权重分配余量。达到权证上限后，对尚未触顶的斗口重新计算权重。最后在本渠按最大余数落整，余数相同时依次比较优先级、斗口文本编码。整数刻度之外的水留在原渠。上游不供水时下游读数留在证据中，水量暂留可核实上游。

`MATCHED` 为对平且无异常，`REVIEW` 为对平但存在需复核事项，`DIFFERENCE` 为计算差异。回执仅在 `MATCHED` 时可下发。交付回执草案与证据文件，不连接闸控设备。
