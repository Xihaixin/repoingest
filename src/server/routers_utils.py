"""此前由摄取端点共享的工具函数。

摄取现在以后台任务方式运行（参见 ``server.routers.ingest`` 和
``server.routers.jobs``）；保留该模块仅为了使用其日志命名空间。
"""

from gitingest.utils.logger import get_logger

logger = get_logger("routers_utils")
