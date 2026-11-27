"""跨业务模块共用的全局常量。"""

GRADE_MIN = 1
GRADE_MAX = 9
GRADE_CHOICES = tuple((value, f"{value} 年级") for value in range(GRADE_MIN, GRADE_MAX + 1))

# 管理员重置密码后，临时密码只在短期缓存中保留，供管理员关闭弹窗后再次查看。
TEMPORARY_PASSWORD_CACHE_PREFIX = "account:temporary-password:"
TEMPORARY_PASSWORD_TTL_SECONDS = 600
