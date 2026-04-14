from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response

from app.api.deps import SessionDep
from app.services import communication_suppressions

router = APIRouter(prefix="/communications", tags=["communications"])


def _unsubscribe_page(*, success: bool, message: str) -> HTMLResponse:
    title = "Email Unsubscribed" if success else "Unable To Unsubscribe"
    body = (
        "<!doctype html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{title}</title>"
        "<style>"
        "body{margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#f5f7fb;color:#0a2540;}"
        ".wrap{max-width:560px;margin:64px auto;padding:0 20px;}"
        ".card{background:#fff;border:1px solid #d9e2f1;border-radius:20px;padding:32px;"
        "box-shadow:0 18px 48px rgba(10,37,64,.08);}"
        "h1{margin:0 0 12px;font-size:28px;line-height:1.15;}"
        "p{margin:0;font-size:16px;line-height:1.6;color:#355070;}"
        "</style>"
        "</head>"
        "<body><div class=\"wrap\"><div class=\"card\">"
        f"<h1>{title}</h1><p>{message}</p>"
        "</div></div></body></html>"
    )
    return HTMLResponse(content=body)


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_email_get(
    session: SessionDep,
    token: str = Query(...),
):
    try:
        _suppression, created = await communication_suppressions.suppress_email_from_token(
            session,
            token=token,
            metadata={"transport": "browser_get"},
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    message = (
        "This email address has been unsubscribed from Backfill email notifications."
        if created
        else "This email address is already unsubscribed from Backfill email notifications."
    )
    return _unsubscribe_page(success=True, message=message)


@router.post("/unsubscribe")
async def unsubscribe_email_post(
    request: Request,
    session: SessionDep,
    token: str = Query(...),
):
    try:
        _suppression, created = await communication_suppressions.suppress_email_from_token(
            session,
            token=token,
            metadata={
                "transport": "one_click_post",
                "headers": {key: value for key, value in request.headers.items()},
            },
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    response = Response(status_code=status.HTTP_200_OK if created else status.HTTP_204_NO_CONTENT)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response
