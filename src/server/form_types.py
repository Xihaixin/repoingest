"""用于 FastAPI 表单参数的可复用表单类型别名。"""

from typing import TYPE_CHECKING, Optional

from fastapi import Form

from gitingest.utils.compat_typing import Annotated

if TYPE_CHECKING:
    from gitingest.utils.compat_typing import TypeAlias

StrForm: TypeAlias = Annotated[str, Form(...)]
IntForm: TypeAlias = Annotated[int, Form(...)]
OptStrForm: TypeAlias = Annotated[Optional[str], Form()]