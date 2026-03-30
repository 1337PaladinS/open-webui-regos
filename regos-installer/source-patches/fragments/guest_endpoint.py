class GuestSigninForm(BaseModel):
    email: str


@router.post("/guest", response_model=SessionUserResponse)
async def guest_signin(
    request: Request,
    response: Response,
    form_data: GuestSigninForm,
    db: Session = Depends(get_session),
):
    """
    Email-based guest access. Guests must provide a real email address.

    - If the email already has a guest account: check generation limit,
      then issue a new JWT for the existing account (preserving chat history).
    - If the email is new: create a guest account and auto-assign to the
      configured guest group.
    - If the guest has exceeded the generation limit: reject with 429.

    Guest JWT expires based on REGOS_GUEST_SESSION_TTL (default 3 hours).
    Guest role has restricted permissions enforced at both backend and frontend.
    """
    client_ip = request.client.host if request.client else "unknown"
    if signin_rate_limiter.is_limited(f"guest:{client_ip}"):
        raise HTTPException(429, detail=ERROR_MESSAGES.RATE_LIMIT_EXCEEDED)

    # Validate email format
    email = form_data.email.strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, detail="Please enter a valid email address.")

    from open_webui.config import (
        GUEST_USER_PERMISSIONS,
        GUEST_MESSAGE_LIMIT,
    )
    from open_webui.models.chats import Chats

    # Check if a guest account with this email already exists
    existing_user = Users.get_user_by_email(email, db=db)

    if existing_user:
        if existing_user.role != "guest":
            # Email belongs to a registered (non-guest) user — don't allow guest login
            raise HTTPException(
                400,
                detail="This email is already registered. Please sign in with your account.",
            )

        # Existing guest — check generation limit before issuing new token
        gen_limit = request.app.state.config.REGOS_GUEST_GENERATION_LIMIT
        if gen_limit and gen_limit > 0:
            guest_chats = Chats.get_chat_list_by_user_id(
                existing_user.id, include_archived=True, limit=500
            )
            total_generations = 0
            for c in guest_chats:
                history = c.chat.get("history", {})
                messages = history.get("messages", {})
                if isinstance(messages, dict):
                    total_generations += sum(
                        1 for m in messages.values()
                        if isinstance(m, dict) and m.get("role") == "assistant"
                    )
            if total_generations >= gen_limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Guest usage limit ({gen_limit} responses) reached for this email. Please sign up for unlimited access.",
                )

        user = existing_user
    else:
        # New guest — create account
        guest_password = get_password_hash(str(uuid.uuid4()))

        user = Auths.insert_new_auth(
            email=email,
            password=guest_password,
            name="Guest",
            profile_image_url="/user.png",
            role="guest",
            db=db,
        )
        if not user:
            raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)

        # Auto-assign to guest group (lookup by name "guest", case-insensitive)
        try:
            all_groups = Groups.get_groups(filter={"query": "guest"}, db=db)
            guest_group = next(
                (g for g in all_groups if "guest" in g.name.lower()), None
            )
            if guest_group:
                Groups.add_users_to_group(guest_group.id, [user.id], db=db)
                log.info(f"Guest user {user.id} added to group '{guest_group.name}'")
            else:
                log.warning("No group with 'guest' in its name found — guest user created without group assignment")
        except Exception as e:
            log.error(f"Failed to assign guest group: {e}")

    # Guest JWT expires based on session TTL config
    from datetime import timedelta as _td

    session_ttl = int(request.app.state.config.REGOS_GUEST_SESSION_TTL or 10800)
    guest_expires = _td(seconds=session_ttl)
    expires_at = int(time.time()) + session_ttl

    token = create_token(
        data={"id": user.id},
        expires_delta=guest_expires,
    )

    # Set auth cookie
    datetime_expires_at = datetime.datetime.fromtimestamp(
        expires_at, datetime.timezone.utc
    )
    response.set_cookie(
        key="token",
        value=token,
        expires=datetime_expires_at,
        httponly=True,
        samesite=WEBUI_AUTH_COOKIE_SAME_SITE,
        secure=WEBUI_AUTH_COOKIE_SECURE,
    )

    return {
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "profile_image_url": f"/api/v1/users/{user.id}/profile/image",
        "permissions": GUEST_USER_PERMISSIONS,
    }
