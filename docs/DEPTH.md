# 深度登记 灌区配水核算台

- 规模：中型
- 核心规则：按渠道实测净流量与权证做优先级配给，再按最大余数落整。
- 使用者：轮灌调度员核对闸令与斗口，确认供水账后生成调度回执。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 轮灌批次 | 核验当轮闸令 | `GET /api/batches/{sample}` | `app/modules/m1_batches/rules.py` | `tests/test_batches.py` |
| M2 取水权版本 | 裁决斗口有效权证 | `GET /api/rights/{sample}` | `app/modules/m2_rights/rules.py` | `tests/test_rights.py` |
| M3 渠道损耗 | 核对实测分流和渠损 | `GET /api/channels/{sample}` | `app/modules/m3_channels/rules.py` | `tests/test_channels.py` |
| M4 优先级配额 | 核算保底与权重配额 | `GET /api/quotas/{sample}` | `app/modules/m4_quotas/rules.py` | `tests/test_quotas.py` |
| M5 尾量调平 | 分派最小水量单位 | `GET /api/tail/{sample}` | `app/modules/m5_tail/rules.py` | `tests/test_tail.py` |
| M6 斗口勾稽 | 比对供水、损耗、实配与剩余 | `GET /api/balance/{sample}` | `app/modules/m6_balance/rules.py` | `tests/test_balance.py` |
| M7 调度回执 | 编制可下发回执或待审草案 | `GET /api/dispatch/{sample}` | `app/modules/m7_dispatch/rules.py` | `tests/test_dispatch.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-06 | 脏样例：全角千位值 | 解析失败 | 统一归一化后按整升核算 | `app/modules/m1_batches/rules.py` | `tests/test_batches.py::test_unit_normalized` |
| TRAP-07 | 脏样例：保底为哨兵 | 按零配水 | 保留原行隔离 | `app/modules/m2_rights/rules.py` | `tests/test_rights.py::test_missing_minimum` |
| TRAP-08 | 干净样例：带前导零的斗口号 | 数字化后丢零 | 文本编码核算 | `app/modules/m2_rights/rules.py` | `tests/test_rights.py::test_leading_zero` |
| TRAP-15 | 脏样例：支渠混用整升与立方米 | 支渠入流多扣千倍 | 统一整升 | `app/modules/m3_channels/rules.py` | `tests/test_channels.py::test_mixed_channel_unit` |
| TRAP-19 | 脏样例：同轮两道闸令 | 末次覆盖 | 并列留证且闸门阻断 | `app/modules/m1_batches/rules.py` | `tests/test_batches.py::test_overlap_blocks_gate` |
| TRAP-20 | 脏样例：渠道依赖成环 | 遍历不终止 | 从渠首遍历且隔离断联 | `app/modules/m3_channels/rules.py` | `tests/test_channels.py::test_cycle_rejected` |
| TRAP-23 | 干净样例：权证在批次开始失效 | 两版均生效 | 采用半开区间 | `app/modules/m2_rights/rules.py` | `tests/test_rights.py::test_end_exclusive` |
| TRAP-24 | 干净样例：斗口余数相同 | 逐行四舍五入超分 | 用最大余数守恒 | `app/modules/m5_tail/rules.py` | `tests/test_tail.py::test_largest_remainder` |
| TRAP-25 | 脏样例：斗口活动权证重叠 | 取到哪个版本不确定 | 重叠版本同时隔离 | `app/modules/m2_rights/rules.py` | `tests/test_rights.py::test_overlap_right` |

## 对账规则

渠首供水等于已核实渠损、斗口实配和所有本地余量。脏样例部分支渠受闸冲突隔离，未能核实的入流保留于上游余量供复核。各斗口及渠道均带原始行。

## 已知边界

按单一完整轮灌时段计算，时段内切换闸令需分批录入。渠道是单渠首树状网络，按实测入流扣账。回执草案由人工复核。
