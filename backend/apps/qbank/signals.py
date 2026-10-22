"""题库领域事件。

审核通知由模块三（后端 A）的通知中心接入，本模块只负责发出事件，
不持有通知数据，避免越界实现通知中心。
"""
from django.dispatch import Signal

# 参数：question、actor、action（approve/reject）、comment
question_reviewed = Signal()
