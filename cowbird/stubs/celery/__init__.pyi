from typing import Any, Callable, Optional, Protocol, Tuple, Type

from celery import Task
from celery.local import Proxy

#SharedTaskCallable = Callable[..., Callable[[Proxy], Task[Any, Any]]]
class SharedTaskCallable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Callable[[Proxy], Task[Any, Any]]: ...


class shared_task:
    # add more parameters as necessary, only currently employed ones are defined
    def __init__(
        self,
        bind: bool = False,
        base: Optional[Task[Any, Any]] = None,
        typing: bool = False,
        autoretry_for: Optional[Tuple[Type[Exception], ...]] = None,
        retry_backoff: bool = False,
        max_retries: int = 0,
    ) -> None: ...

    def __call__(self, task: Task[Any, Any], *args: Any, **kwargs: Any) -> SharedTaskCallable: ...
