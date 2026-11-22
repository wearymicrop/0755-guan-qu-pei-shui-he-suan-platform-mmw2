from app.modules.m1_batches.handler import router as batches_router
from app.modules.m1_batches.rules import run as batches
from app.modules.m2_rights.handler import router as rights_router
from app.modules.m2_rights.rules import run as rights
from app.modules.m3_channels.handler import router as channels_router
from app.modules.m3_channels.rules import run as channels
from app.modules.m4_quotas.handler import router as quotas_router
from app.modules.m4_quotas.rules import run as quotas
from app.modules.m5_tail.handler import router as tail_router
from app.modules.m5_tail.rules import run as tail
from app.modules.m6_balance.handler import router as balance_router
from app.modules.m6_balance.rules import run as balance
from app.modules.m7_dispatch.handler import router as dispatch_router
from app.modules.m7_dispatch.rules import run as dispatch
from app.modules.m8_merge.handler import router as merge_router
from app.modules.m8_merge.rules import run as merge

TABLES = ("gates", "rights", "channels")
HOME = "tail"
STAGES = (
    ("batches", "轮灌批次", batches, batches_router),
    ("rights", "取水权版本", rights, rights_router),
    ("channels", "渠道损耗", channels, channels_router),
    ("quotas", "优先级配额", quotas, quotas_router),
    ("tail", "尾量调平", tail, tail_router),
    ("balance", "斗口勾稽", balance, balance_router),
    ("dispatch", "调度回执", dispatch, dispatch_router),
    ("merge", "合并承接", merge, merge_router),
)
