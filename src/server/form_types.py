"""Reusable form type aliases for FastAPI form parameters."""

from typing import TYPE_CHECKING, Optional

from fastapi import Form

from gitingest.utils.compat_typing import Annotated

if TYPE_CHECKING:
    from gitingest.utils.compat_typing import TypeAlias

StrForm: TypeAlias = Annotated[str, Form(...)]
IntForm: TypeAlias = Annotated[int, Form(...)]
OptStrForm: TypeAlias = Annotated[Optional[str], Form()]