"""Request correlation and actor context at Mosaic's HTTP edge."""

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from structlog.contextvars import bind_contextvars, reset_contextvars
from structlog.stdlib import BoundLogger

REQUEST_ID_HEADER = "X-Request-ID"
_STATE_ATTRIBUTE = "mosaic_request_context"


@dataclass(frozen=True, slots=True)
class ActorContext:
    """The actor known at the HTTP edge for one request.

    Phase 0 deliberately creates only anonymous actors. A later authentication
    adapter can enrich this value before a domain request is constructed; this
    foundation does not trust caller-supplied identity or authorize behavior.
    """

    kind: Literal["anonymous"] = "anonymous"
    subject: None = None


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Correlation and actor facts carried by one HTTP request."""

    request_id: str
    actor: ActorContext


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Create observable request context before an HTTP adapter runs."""

    def __init__(self, app: ASGIApp, *, logger: BoundLogger) -> None:
        super().__init__(app)
        self._logger = logger

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Correlate the request and record its anonymous Phase 0 actor."""
        context = RequestContext(request_id=str(uuid4()), actor=ActorContext())
        setattr(request.state, _STATE_ATTRIBUTE, context)
        tokens = bind_contextvars(
            actor_kind=context.actor.kind,
            request_id=context.request_id,
        )
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = context.request_id
            self._logger.info(
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
            return response
        finally:
            reset_contextvars(**tokens)


def get_request_context(request: Request) -> RequestContext:
    """Return the typed context installed for a FastAPI HTTP adapter."""
    context = getattr(request.state, _STATE_ATTRIBUTE, None)
    if not isinstance(context, RequestContext):
        raise RuntimeError("request context middleware has not run")
    return context


__all__ = [
    "ActorContext",
    "REQUEST_ID_HEADER",
    "RequestContext",
    "RequestContextMiddleware",
    "get_request_context",
]
