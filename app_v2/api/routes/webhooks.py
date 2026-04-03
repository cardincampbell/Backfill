from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app_v2.api.deps import AuthDep, SessionDep
from app_v2.models.common import AuditActorType, MembershipRole
from app_v2.schemas.webhooks import (
    WebhookDeliveryRead,
    WebhookEventCatalogResponse,
    WebhookSecretRotateResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreateResponse,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)
from app_v2.services import audit as audit_service
from app_v2.services import auth as auth_service, webhooks

router = APIRouter(prefix="/businesses/{business_id}/webhooks", tags=["v2-webhooks"])

ADMIN_ROLES = {MembershipRole.owner, MembershipRole.admin}


@router.get("/events", response_model=WebhookEventCatalogResponse)
async def list_supported_events(
    business_id: UUID,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    return WebhookEventCatalogResponse(events=webhooks.supported_events())


@router.get("", response_model=list[WebhookSubscriptionRead])
async def list_business_webhooks(
    business_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    return await webhooks.list_subscriptions(session, business_id=business_id)


@router.post("", response_model=WebhookSubscriptionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_business_webhook(
    business_id: UUID,
    payload: WebhookSubscriptionCreate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    try:
        subscription, secret = await webhooks.create_subscription(
            session,
            business_id=business_id,
            created_by_user_id=auth_ctx.user.id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await audit_service.append(
        session,
        event_name="webhook_subscription.created",
        target_type="webhook_subscription",
        target_id=subscription.id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"endpoint_url": subscription.endpoint_url, "subscribed_events": subscription.subscribed_events},
    )
    await session.commit()
    return WebhookSubscriptionCreateResponse(subscription=subscription, signing_secret=secret)


@router.patch("/{subscription_id}", response_model=WebhookSubscriptionRead)
async def update_business_webhook(
    business_id: UUID,
    subscription_id: UUID,
    payload: WebhookSubscriptionUpdate,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    subscription = await webhooks.get_subscription(session, business_id=business_id, subscription_id=subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook_subscription_not_found")
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    try:
        subscription = await webhooks.update_subscription(session, subscription, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await audit_service.append(
        session,
        event_name="webhook_subscription.updated",
        target_type="webhook_subscription",
        target_id=subscription.id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"endpoint_url": subscription.endpoint_url, "status": subscription.status.value},
    )
    await session.commit()
    return subscription


@router.post("/{subscription_id}/rotate-secret", response_model=WebhookSecretRotateResponse)
async def rotate_webhook_secret(
    business_id: UUID,
    subscription_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    request: Request,
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    subscription = await webhooks.get_subscription(session, business_id=business_id, subscription_id=subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook_subscription_not_found")
    membership = auth_service.membership_for_scope(auth_ctx, business_id)
    subscription, secret = await webhooks.rotate_subscription_secret(session, subscription)
    await audit_service.append(
        session,
        event_name="webhook_subscription.secret_rotated",
        target_type="webhook_subscription",
        target_id=subscription.id,
        business_id=business_id,
        actor_type=AuditActorType.user,
        actor_user_id=auth_ctx.user.id,
        actor_membership_id=membership.id if membership is not None else None,
        ip_address=audit_service.request_client_ip(request),
        user_agent=audit_service.request_user_agent(request),
        payload={"endpoint_url": subscription.endpoint_url},
    )
    await session.commit()
    return WebhookSecretRotateResponse(subscription=subscription, signing_secret=secret)


@router.get("/{subscription_id}/deliveries", response_model=list[WebhookDeliveryRead])
async def list_webhook_deliveries(
    business_id: UUID,
    subscription_id: UUID,
    session: SessionDep,
    auth_ctx: AuthDep,
    limit: int = Query(default=50, ge=1, le=200),
):
    if not auth_service.has_business_access(auth_ctx, business_id, allowed_roles=ADMIN_ROLES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="business_admin_required")
    subscription = await webhooks.get_subscription(session, business_id=business_id, subscription_id=subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook_subscription_not_found")
    return await webhooks.list_deliveries(
        session,
        business_id=business_id,
        subscription_id=subscription_id,
        limit=limit,
    )
