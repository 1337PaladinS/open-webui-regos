#!/usr/bin/env python3
"""
apply-patches.py — Surgical source patcher for RegOS on stock Open WebUI.

Injects RegOS features (admin panel, guest access, disclaimer modal, confidence
display) into a stock Open WebUI source tree without replacing entire files.
Each patch finds an anchor point in the existing code and injects new code
before or after it.

Usage:
    python3 apply-patches.py /path/to/open-webui

Exit codes:
    0  All patches applied successfully
    1  One or more patches failed (anchor not found)
"""

import os
import sys
import shutil
from pathlib import Path


class PatchError(Exception):
    pass


def inject_after(content: str, anchor: str, injection: str, label: str) -> str:
    """Insert code AFTER the anchor line."""
    if anchor not in content:
        raise PatchError(f"[{label}] Anchor not found: {anchor[:80]}...")
    if injection.strip() in content:
        print(f"  [SKIP] {label} — already applied")
        return content
    return content.replace(anchor, anchor + injection)


def inject_before(content: str, anchor: str, injection: str, label: str) -> str:
    """Insert code BEFORE the anchor line."""
    if anchor not in content:
        raise PatchError(f"[{label}] Anchor not found: {anchor[:80]}...")
    if injection.strip() in content:
        print(f"  [SKIP] {label} — already applied")
        return content
    return content.replace(anchor, injection + anchor)


def replace_text(content: str, old: str, new: str, label: str) -> str:
    """Replace exact text."""
    if old not in content:
        raise PatchError(f"[{label}] Text not found: {old[:80]}...")
    if new in content:
        print(f"  [SKIP] {label} — already applied")
        return content
    return content.replace(old, new)


def append_to_file(content: str, injection: str, label: str) -> str:
    """Append code to end of file."""
    marker = injection.strip()[:60]
    if marker in content:
        print(f"  [SKIP] {label} — already applied")
        return content
    return content.rstrip() + "\n\n" + injection + "\n"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
# PATCH DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

def patch_backend_config(root: Path):
    """backend/open_webui/config.py — Add guest access vars + RegOS PersistentConfig entries."""
    f = root / "backend" / "open_webui" / "config.py"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # 1. Add GUEST_MESSAGE_LIMIT and GUEST_MESSAGE_WINDOW if not present
    guest_vars = '''
####################################
# Guest Access Configuration
####################################

GUEST_MESSAGE_LIMIT = int(os.environ.get("GUEST_MESSAGE_LIMIT", "10"))
GUEST_MESSAGE_WINDOW = int(os.environ.get("GUEST_MESSAGE_WINDOW", "10800"))  # 3 hours
'''
    if "GUEST_MESSAGE_LIMIT" not in c:
        c = c.rstrip() + "\n" + guest_vars
        print("  [OK] Added GUEST_MESSAGE_LIMIT / GUEST_MESSAGE_WINDOW")
    else:
        print("  [SKIP] GUEST_MESSAGE_LIMIT already present")

    # 2. Append RegOS PersistentConfig entries at end of file
    regos_config = '''
####################################
# RegOS Admin Settings
####################################

REGOS_DISCLAIMER_ENABLED = PersistentConfig(
    "REGOS_DISCLAIMER_ENABLED",
    "regos.disclaimer.enabled",
    os.environ.get("REGOS_DISCLAIMER_ENABLED", "True").lower() == "true",
)

REGOS_DISCLAIMER_TITLE = PersistentConfig(
    "REGOS_DISCLAIMER_TITLE",
    "regos.disclaimer.title",
    os.environ.get("REGOS_DISCLAIMER_TITLE", "Welcome to RegOS Compliance Copilot"),
)

REGOS_DISCLAIMER_BODY = PersistentConfig(
    "REGOS_DISCLAIMER_BODY",
    "regos.disclaimer.body",
    os.environ.get("REGOS_DISCLAIMER_BODY", ""),
)

REGOS_DISCLAIMER_ACCEPT_LABEL = PersistentConfig(
    "REGOS_DISCLAIMER_ACCEPT_LABEL",
    "regos.disclaimer.accept_label",
    os.environ.get("REGOS_DISCLAIMER_ACCEPT_LABEL", "I Understand & Accept"),
)

REGOS_GUEST_ENABLED = PersistentConfig(
    "REGOS_GUEST_ENABLED",
    "regos.guest.enabled",
    os.environ.get("REGOS_GUEST_ENABLED", "True").lower() == "true",
)

REGOS_GUEST_MESSAGE_LIMIT = PersistentConfig(
    "REGOS_GUEST_MESSAGE_LIMIT",
    "regos.guest.message_limit",
    int(os.environ.get("REGOS_GUEST_MESSAGE_LIMIT", str(GUEST_MESSAGE_LIMIT))),
)

REGOS_GUEST_GENERATION_LIMIT = PersistentConfig(
    "REGOS_GUEST_GENERATION_LIMIT",
    "regos.guest.generation_limit",
    int(os.environ.get("REGOS_GUEST_GENERATION_LIMIT", "50")),
)

REGOS_GUEST_SESSION_TTL = PersistentConfig(
    "REGOS_GUEST_SESSION_TTL",
    "regos.guest.session_ttl",
    int(os.environ.get("REGOS_GUEST_SESSION_TTL", str(GUEST_MESSAGE_WINDOW))),
)

REGOS_GUEST_SHOW_BUTTON = PersistentConfig(
    "REGOS_GUEST_SHOW_BUTTON",
    "regos.guest.show_button",
    os.environ.get("REGOS_GUEST_SHOW_BUTTON", "True").lower() == "true",
)

REGOS_CONFIDENCE_ENABLED = PersistentConfig(
    "REGOS_CONFIDENCE_ENABLED",
    "regos.confidence.enabled",
    os.environ.get("REGOS_CONFIDENCE_ENABLED", "True").lower() == "true",
)

REGOS_CONFIDENCE_STYLE = PersistentConfig(
    "REGOS_CONFIDENCE_STYLE",
    "regos.confidence.style",
    os.environ.get("REGOS_CONFIDENCE_STYLE", "emoji_blockquote"),
)

REGOS_CONFIDENCE_HIGH_THRESHOLD = PersistentConfig(
    "REGOS_CONFIDENCE_HIGH_THRESHOLD",
    "regos.confidence.high_threshold",
    int(os.environ.get("REGOS_CONFIDENCE_HIGH_THRESHOLD", "70")),
)

REGOS_CONFIDENCE_MEDIUM_THRESHOLD = PersistentConfig(
    "REGOS_CONFIDENCE_MEDIUM_THRESHOLD",
    "regos.confidence.medium_threshold",
    int(os.environ.get("REGOS_CONFIDENCE_MEDIUM_THRESHOLD", "45")),
)
'''
    c = append_to_file(c, regos_config, "RegOS PersistentConfig entries")
    write_file(f, c)
    print("  [OK] config.py patched")


def patch_backend_main(root: Path):
    """backend/open_webui/main.py — Add imports, state assignments, guest rate limiting."""
    f = root / "backend" / "open_webui" / "main.py"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # 1. Add REGOS imports — find the end of the import block from config.py
    #    Look for WEBHOOK_URL which is typically the last import
    import_injection = """\
    # RegOS Settings
    REGOS_DISCLAIMER_ENABLED,
    REGOS_DISCLAIMER_TITLE,
    REGOS_DISCLAIMER_BODY,
    REGOS_DISCLAIMER_ACCEPT_LABEL,
    REGOS_GUEST_ENABLED,
    REGOS_GUEST_MESSAGE_LIMIT,
    REGOS_GUEST_GENERATION_LIMIT,
    REGOS_GUEST_SESSION_TTL,
    REGOS_GUEST_SHOW_BUTTON,
    REGOS_CONFIDENCE_ENABLED,
    REGOS_CONFIDENCE_STYLE,
    REGOS_CONFIDENCE_HIGH_THRESHOLD,
    REGOS_CONFIDENCE_MEDIUM_THRESHOLD,
"""
    # Try to inject before WEBHOOK_URL import
    if "REGOS_DISCLAIMER_ENABLED" not in c:
        anchor = "    WEBHOOK_URL,"
        if anchor in c:
            c = inject_before(c, anchor, import_injection, "RegOS imports")
        else:
            # Fallback: inject before ADMIN_EMAIL
            anchor2 = "    ADMIN_EMAIL,"
            c = inject_before(c, anchor2, import_injection, "RegOS imports (fallback)")
    else:
        print("  [SKIP] RegOS imports already present")

    # 2. Add state assignments — after the last app.state.config line
    state_block = """
########################################
#
# REGOS
#
########################################

app.state.config.REGOS_DISCLAIMER_ENABLED = REGOS_DISCLAIMER_ENABLED
app.state.config.REGOS_DISCLAIMER_TITLE = REGOS_DISCLAIMER_TITLE
app.state.config.REGOS_DISCLAIMER_BODY = REGOS_DISCLAIMER_BODY
app.state.config.REGOS_DISCLAIMER_ACCEPT_LABEL = REGOS_DISCLAIMER_ACCEPT_LABEL
app.state.config.REGOS_GUEST_ENABLED = REGOS_GUEST_ENABLED
app.state.config.REGOS_GUEST_MESSAGE_LIMIT = REGOS_GUEST_MESSAGE_LIMIT
app.state.config.REGOS_GUEST_GENERATION_LIMIT = REGOS_GUEST_GENERATION_LIMIT
app.state.config.REGOS_GUEST_SESSION_TTL = REGOS_GUEST_SESSION_TTL
app.state.config.REGOS_GUEST_SHOW_BUTTON = REGOS_GUEST_SHOW_BUTTON
app.state.config.REGOS_CONFIDENCE_ENABLED = REGOS_CONFIDENCE_ENABLED
app.state.config.REGOS_CONFIDENCE_STYLE = REGOS_CONFIDENCE_STYLE
app.state.config.REGOS_CONFIDENCE_HIGH_THRESHOLD = REGOS_CONFIDENCE_HIGH_THRESHOLD
app.state.config.REGOS_CONFIDENCE_MEDIUM_THRESHOLD = REGOS_CONFIDENCE_MEDIUM_THRESHOLD

"""
    if "app.state.config.REGOS_DISCLAIMER_ENABLED" not in c:
        # Use a UNIQUE anchor — "# Chat Endpoints" appears once in main.py
        anchor = "# Chat Endpoints"
        if anchor not in c:
            # Fallback: look for the chat_completions section
            anchor = "##################################\n#\n# Chat"
        c = inject_before(c, anchor, state_block, "RegOS state assignments")
    else:
        print("  [SKIP] RegOS state assignments already present")

    # 3. Add guest rate limiting in chat_completion
    guest_limit_code = """\
    # Guest rate limiting: cap chats AND generations per guest session
    if user.role == "guest":
        from open_webui.config import GUEST_MESSAGE_LIMIT

        # 1. Chat limit (number of conversations)
        guest_chats = Chats.get_chat_list_by_user_id(
            user.id, include_archived=True, limit=GUEST_MESSAGE_LIMIT + 1
        )
        if len(guest_chats) >= GUEST_MESSAGE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Guest chat limit reached. Sign up for unlimited access.",
            )

        # 2. Generation limit (total AI responses across all chats)
        gen_limit = request.app.state.config.REGOS_GUEST_GENERATION_LIMIT
        if gen_limit and gen_limit > 0:
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
                    detail=f"Guest generation limit ({gen_limit}) reached. Sign up for unlimited access.",
                )

"""
    if "Guest rate limiting" not in c:
        # Find the chat_completion function body — inject after the function signature
        anchor = "    if not request.app.state.MODELS:"
        if anchor in c:
            c = inject_before(c, anchor, guest_limit_code, "Guest rate limiting")
        else:
            print("  [WARN] Could not find chat_completion anchor — skipping guest rate limiting")
    else:
        print("  [SKIP] Guest rate limiting already present")

    write_file(f, c)
    print("  [OK] main.py patched")


def patch_backend_configs_router(root: Path):
    """backend/open_webui/routers/configs.py — Add RegOS endpoints."""
    f = root / "backend" / "open_webui" / "routers" / "configs.py"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    regos_endpoints = '''

############################
# RegOS Settings
############################


class RegOSDisclaimerForm(BaseModel):
    enabled: bool
    title: str
    body: str
    accept_label: str


class RegOSGuestForm(BaseModel):
    enabled: bool
    message_limit: int
    generation_limit: int
    session_ttl: int
    show_button: bool


class RegOSConfidenceForm(BaseModel):
    enabled: bool
    style: str
    high_threshold: int
    medium_threshold: int


class RegOSSettingsForm(BaseModel):
    disclaimer: RegOSDisclaimerForm
    guest: RegOSGuestForm
    confidence: RegOSConfidenceForm


@router.get("/regos")
async def get_regos_config(request: Request, user=Depends(get_admin_user)):
    return {
        "disclaimer": {
            "enabled": request.app.state.config.REGOS_DISCLAIMER_ENABLED,
            "title": request.app.state.config.REGOS_DISCLAIMER_TITLE,
            "body": request.app.state.config.REGOS_DISCLAIMER_BODY,
            "accept_label": request.app.state.config.REGOS_DISCLAIMER_ACCEPT_LABEL,
        },
        "guest": {
            "enabled": request.app.state.config.REGOS_GUEST_ENABLED,
            "message_limit": request.app.state.config.REGOS_GUEST_MESSAGE_LIMIT,
            "generation_limit": request.app.state.config.REGOS_GUEST_GENERATION_LIMIT,
            "session_ttl": request.app.state.config.REGOS_GUEST_SESSION_TTL,
            "show_button": request.app.state.config.REGOS_GUEST_SHOW_BUTTON,
        },
        "confidence": {
            "enabled": request.app.state.config.REGOS_CONFIDENCE_ENABLED,
            "style": request.app.state.config.REGOS_CONFIDENCE_STYLE,
            "high_threshold": request.app.state.config.REGOS_CONFIDENCE_HIGH_THRESHOLD,
            "medium_threshold": request.app.state.config.REGOS_CONFIDENCE_MEDIUM_THRESHOLD,
        },
    }


@router.post("/regos")
async def set_regos_config(
    request: Request,
    form_data: RegOSSettingsForm,
    user=Depends(get_admin_user),
):
    data = form_data.model_dump()

    request.app.state.config.REGOS_DISCLAIMER_ENABLED = data["disclaimer"]["enabled"]
    request.app.state.config.REGOS_DISCLAIMER_TITLE = data["disclaimer"]["title"]
    request.app.state.config.REGOS_DISCLAIMER_BODY = data["disclaimer"]["body"]
    request.app.state.config.REGOS_DISCLAIMER_ACCEPT_LABEL = data["disclaimer"]["accept_label"]

    request.app.state.config.REGOS_GUEST_ENABLED = data["guest"]["enabled"]
    request.app.state.config.REGOS_GUEST_MESSAGE_LIMIT = data["guest"]["message_limit"]
    request.app.state.config.REGOS_GUEST_GENERATION_LIMIT = data["guest"]["generation_limit"]
    request.app.state.config.REGOS_GUEST_SESSION_TTL = data["guest"]["session_ttl"]
    request.app.state.config.REGOS_GUEST_SHOW_BUTTON = data["guest"]["show_button"]

    request.app.state.config.REGOS_CONFIDENCE_ENABLED = data["confidence"]["enabled"]
    request.app.state.config.REGOS_CONFIDENCE_STYLE = data["confidence"]["style"]
    request.app.state.config.REGOS_CONFIDENCE_HIGH_THRESHOLD = data["confidence"]["high_threshold"]
    request.app.state.config.REGOS_CONFIDENCE_MEDIUM_THRESHOLD = data["confidence"]["medium_threshold"]

    return await get_regos_config(request, user)


@router.get("/regos/public")
async def get_regos_public_config(request: Request, user=Depends(get_verified_user)):
    """Public-facing subset of RegOS config for non-admin users."""
    return {
        "disclaimer": {
            "enabled": request.app.state.config.REGOS_DISCLAIMER_ENABLED,
            "title": request.app.state.config.REGOS_DISCLAIMER_TITLE,
            "body": request.app.state.config.REGOS_DISCLAIMER_BODY,
            "accept_label": request.app.state.config.REGOS_DISCLAIMER_ACCEPT_LABEL,
        },
        "guest": {
            "enabled": request.app.state.config.REGOS_GUEST_ENABLED,
            "show_button": request.app.state.config.REGOS_GUEST_SHOW_BUTTON,
        },
        "confidence": {
            "enabled": request.app.state.config.REGOS_CONFIDENCE_ENABLED,
            "style": request.app.state.config.REGOS_CONFIDENCE_STYLE,
        },
    }


@router.get("/regos/guest-status")
async def get_regos_guest_status(request: Request):
    """Unauthenticated endpoint for login page guest button visibility."""
    return {
        "enabled": request.app.state.config.REGOS_GUEST_ENABLED,
        "show_button": request.app.state.config.REGOS_GUEST_SHOW_BUTTON,
    }
'''
    c = append_to_file(c, regos_endpoints, "RegOS endpoints")
    write_file(f, c)
    print("  [OK] configs.py patched")


def patch_frontend_configs_api(root: Path):
    """src/lib/apis/configs/index.ts — Append RegOS API functions."""
    f = root / "src" / "lib" / "apis" / "configs" / "index.ts"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    api_functions = """
export const getRegosConfig = async (token: string) => {
\tlet error = null;
\tconst res = await fetch(`${WEBUI_API_BASE_URL}/configs/regos`, {
\t\tmethod: 'GET',
\t\theaders: {
\t\t\t'Content-Type': 'application/json',
\t\t\tAuthorization: `Bearer ${token}`
\t\t}
\t})
\t\t.then(async (res) => {
\t\t\tif (!res.ok) throw await res.json();
\t\t\treturn res.json();
\t\t})
\t\t.catch((err) => {
\t\t\tconsole.error(err);
\t\t\terror = err.detail;
\t\t\treturn null;
\t\t});

\tif (error) {
\t\tthrow error;
\t}

\treturn res;
};

export const updateRegosConfig = async (token: string, config: object) => {
\tlet error = null;
\tconst res = await fetch(`${WEBUI_API_BASE_URL}/configs/regos`, {
\t\tmethod: 'POST',
\t\theaders: {
\t\t\t'Content-Type': 'application/json',
\t\t\tAuthorization: `Bearer ${token}`
\t\t},
\t\tbody: JSON.stringify(config)
\t})
\t\t.then(async (res) => {
\t\t\tif (!res.ok) throw await res.json();
\t\t\treturn res.json();
\t\t})
\t\t.catch((err) => {
\t\t\tconsole.error(err);
\t\t\terror = err.detail;
\t\t\treturn null;
\t\t});

\tif (error) {
\t\tthrow error;
\t}

\treturn res;
};

export const getRegosGuestStatus = async () => {
\tlet error = null;
\tconst res = await fetch(`${WEBUI_API_BASE_URL}/configs/regos/guest-status`, {
\t\tmethod: 'GET',
\t\theaders: {
\t\t\t'Content-Type': 'application/json'
\t\t}
\t})
\t\t.then(async (res) => {
\t\t\tif (!res.ok) throw await res.json();
\t\t\treturn res.json();
\t\t})
\t\t.catch((err) => {
\t\t\tconsole.error(err);
\t\t\terror = err.detail;
\t\t\treturn null;
\t\t});

\tif (error) {
\t\tthrow error;
\t}

\treturn res;
};

export const getRegosPublicConfig = async (token: string) => {
\tlet error = null;
\tconst res = await fetch(`${WEBUI_API_BASE_URL}/configs/regos/public`, {
\t\tmethod: 'GET',
\t\theaders: {
\t\t\t'Content-Type': 'application/json',
\t\t\tAuthorization: `Bearer ${token}`
\t\t}
\t})
\t\t.then(async (res) => {
\t\t\tif (!res.ok) throw await res.json();
\t\t\treturn res.json();
\t\t})
\t\t.catch((err) => {
\t\t\tconsole.error(err);
\t\t\terror = err.detail;
\t\t\treturn null;
\t\t});

\tif (error) {
\t\tthrow error;
\t}

\treturn res;
};"""
    c = append_to_file(c, api_functions, "RegOS API functions")
    write_file(f, c)
    print("  [OK] configs/index.ts patched")


def patch_admin_layout(root: Path):
    """src/routes/(app)/admin/+layout.svelte — Add RegOS tab to nav bar."""
    f = root / "src" / "routes" / "(app)" / "admin" / "+layout.svelte"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    regos_tab = """\

						<a
							class="min-w-fit p-1.5 {$page.url.pathname.includes('/admin/regos')
								? ''
								: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition"
							href="/admin/regos">RegOS</a
						>"""

    # Inject after the Settings link
    anchor = """href="/admin/settings">{$i18n.t('Settings')}</a
						>"""
    c = inject_after(c, anchor, regos_tab, "RegOS admin nav tab")
    write_file(f, c)
    print("  [OK] admin +layout.svelte patched")


def patch_app_layout(root: Path):
    """src/routes/(app)/+layout.svelte — Wire disclaimer modal to RegOS config."""
    f = root / "src" / "routes" / "(app)" / "+layout.svelte"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # 1. Add imports — after existing component imports
    import_code = """\
\timport RegOSDisclaimerModal from '$lib/components/RegOSDisclaimerModal.svelte';
\timport { getRegosPublicConfig } from '$lib/apis/configs';
"""
    if "RegOSDisclaimerModal" not in c:
        # Find a good anchor — import section
        anchor = "import { WEBUI_BASE_URL } from '$lib/constants';"
        if anchor not in c:
            anchor = "const i18n = getContext('i18n');"
        c = inject_after(c, anchor, "\n" + import_code, "RegOS layout imports")
    else:
        print("  [SKIP] RegOS layout imports already present")

    # 2. Add regosConfig variable
    if "let regosConfig" not in c:
        anchor = "let loaded = false;"
        c = inject_after(c, anchor, "\n\tlet regosConfig = null;", "regosConfig variable")

    # 3. Add showRegOSDisclaimer store import — if there's a stores import
    if "showRegOSDisclaimer" not in c:
        # We need to create this store. For simplicity, use a writable store inline.
        # Add it after the loaded variable
        if "let regosConfig" in c:
            anchor2 = "let regosConfig = null;"
            store_code = "\n\timport { writable } from 'svelte/store';\n\tconst showRegOSDisclaimer = writable(false);"
            # Check if writable is already imported
            if "from 'svelte/store'" in c:
                store_code = "\n\tconst showRegOSDisclaimer = writable(false);"
            c = inject_after(c, anchor2, store_code, "showRegOSDisclaimer store")

    # 4. Add onMount fetch — inject before the closing of onMount
    #    This is tricky because we don't know the exact onMount structure.
    #    Instead, add it as a separate onMount block.
    if "getRegosPublicConfig" not in c:
        onmount_code = """
\timport { onMount as onMountRegos } from 'svelte';
\tonMountRegos(async () => {
\t\ttry {
\t\t\tregosConfig = await getRegosPublicConfig(localStorage.token);
\t\t\tif (regosConfig?.disclaimer?.enabled && !localStorage.getItem('regosDisclaimerAcked')) {
\t\t\t\tshowRegOSDisclaimer.set(true);
\t\t\t}
\t\t} catch (e) {
\t\t\tconsole.warn('Could not load RegOS config:', e);
\t\t}
\t});
"""
        # Inject after </script> tag start... actually we need it inside the script.
        # Find the last onMount or before </script>
        anchor3 = "</script>"
        c = inject_before(c, anchor3, onmount_code, "RegOS onMount fetch")

    # 5. Add the modal component in the template
    if "<RegOSDisclaimerModal" not in c:
        # Find a good spot — after the main content area starts
        modal_code = '\n<RegOSDisclaimerModal bind:show={$showRegOSDisclaimer} disclaimerConfig={regosConfig?.disclaimer} />\n'
        # Put it near the end, before the last closing tag
        anchor4 = "{/if}\n"
        # Insert before the very last {/if} in the file
        last_endif_pos = c.rfind("{/if}")
        if last_endif_pos > 0:
            c = c[:last_endif_pos] + modal_code + c[last_endif_pos:]
            print("  [OK] RegOS disclaimer modal added to template")
        else:
            print("  [WARN] Could not find template anchor for disclaimer modal")

    write_file(f, c)
    print("  [OK] app +layout.svelte patched")


def patch_auth_page(root: Path):
    """src/routes/auth/+page.svelte — Add email-based guest access with config check."""
    f = root / "src" / "routes" / "auth" / "+page.svelte"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # 1. Add import
    if "getRegosGuestStatus" not in c:
        anchor = "import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';"
        import_line = "\timport { getRegosGuestStatus } from '$lib/apis/configs';\n"
        c = inject_before(c, anchor, import_line, "getRegosGuestStatus import")

    # 2. Add guestEnabled + email variables
    if "let guestEnabled" not in c and "guestSignInHandler" in c:
        anchor = "let guestLoading = false;"
        c = inject_after(c, anchor, "\n\tlet guestEnabled = false;\n\tlet showGuestEmailInput = false;\n\tlet guestEmail = '';", "guest variables")
    elif "let guestEnabled" not in c:
        print("  [SKIP] No guest infrastructure found in auth page")
        write_file(f, c)
        return

    # 3. Replace guestSignInHandler to include email input flow
    old_handler = """\tconst guestSignInHandler = async () => {
\t\tguestLoading = true;
\t\ttry {
\t\t\tconst sessionUser = await userGuestSignIn().catch((error) => {
\t\t\t\ttoast.error(`${error}`);
\t\t\t\treturn null;
\t\t\t});
\t\t\tawait setSessionUser(sessionUser);
\t\t} finally {
\t\t\tguestLoading = false;
\t\t}
\t};"""
    new_handler = """\tconst guestSignInHandler = async () => {
\t\tif (!showGuestEmailInput) {
\t\t\tshowGuestEmailInput = true;
\t\t\treturn;
\t\t}

\t\tif (!guestEmail.trim() || !guestEmail.includes('@') || !guestEmail.split('@')[1]?.includes('.')) {
\t\t\ttoast.error('Please enter a valid email address.');
\t\t\treturn;
\t\t}

\t\tguestLoading = true;
\t\ttry {
\t\t\tconst sessionUser = await userGuestSignIn(guestEmail.trim()).catch((error) => {
\t\t\t\ttoast.error(`${error}`);
\t\t\t\treturn null;
\t\t\t});
\t\t\tawait setSessionUser(sessionUser);
\t\t} finally {
\t\t\tguestLoading = false;
\t\t}
\t};"""
    if "showGuestEmailInput" not in c or old_handler in c:
        if old_handler in c:
            c = c.replace(old_handler, new_handler)
            print("  [OK] Replaced guestSignInHandler with email flow")

    # 4. Add onMount fetch for guest status
    if "getRegosGuestStatus()" not in c:
        anchor = "loaded = true;"
        guest_fetch = """\

\t\t// Fetch guest access status from RegOS config (unauthenticated endpoint)
\t\ttry {
\t\t\tconst guestStatus = await getRegosGuestStatus();
\t\t\tguestEnabled = guestStatus?.enabled && guestStatus?.show_button;
\t\t} catch (e) {
\t\t\tconsole.warn('Could not fetch guest status:', e);
\t\t\tguestEnabled = false;
\t\t}

\t\t"""
        c = inject_before(c, anchor, guest_fetch, "Guest status fetch in onMount")

    # 5. Make guest button conditional on guestEnabled
    old_condition = "{#if !($config?.onboarding ?? false)}"
    new_condition = "{#if guestEnabled && !($config?.onboarding ?? false)}"
    if old_condition in c and new_condition not in c:
        c = replace_text(c, old_condition, new_condition, "Guest button guestEnabled condition")

    # 6. Replace the guest button template with email input version
    old_guest_button = """<button
\t\t\t\t\t\t\t\t\t\tclass="flex justify-center items-center text-sm w-full text-center text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
\t\t\t\t\t\t\t\t\t\ttype="button"
\t\t\t\t\t\t\t\t\t\tdisabled={guestLoading}
\t\t\t\t\t\t\t\t\t\ton:click={guestSignInHandler}
\t\t\t\t\t\t\t\t\t>
\t\t\t\t\t\t\t\t\t\t{#if guestLoading}
\t\t\t\t\t\t\t\t\t\t\t<Spinner className="size-4 mr-2" />
\t\t\t\t\t\t\t\t\t\t{/if}
\t\t\t\t\t\t\t\t\t\t<span>{$i18n.t('or continue as guest')} &rarr;</span>
\t\t\t\t\t\t\t\t\t</button>"""
    new_guest_template = """{#if showGuestEmailInput}
\t\t\t\t\t\t\t\t\t\t<div class="flex flex-col gap-2">
\t\t\t\t\t\t\t\t\t\t\t<div class="text-xs text-center text-gray-500 dark:text-gray-400">
\t\t\t\t\t\t\t\t\t\t\t\t{$i18n.t('Enter your email to continue as guest')}
\t\t\t\t\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t\t\t\t\t<input
\t\t\t\t\t\t\t\t\t\t\t\tclass="w-full text-sm rounded-lg px-4 py-2.5 bg-gray-50 dark:bg-gray-850 dark:text-gray-100 outline-none border border-gray-200 dark:border-gray-700 focus:border-gray-400 dark:focus:border-gray-500 transition"
\t\t\t\t\t\t\t\t\t\t\t\ttype="email"
\t\t\t\t\t\t\t\t\t\t\t\tbind:value={guestEmail}
\t\t\t\t\t\t\t\t\t\t\t\tplaceholder="your@email.com"
\t\t\t\t\t\t\t\t\t\t\t\tautocomplete="email"
\t\t\t\t\t\t\t\t\t\t\t\ton:keydown={(e) => { if (e.key === 'Enter') guestSignInHandler(); }}
\t\t\t\t\t\t\t\t\t\t\t/>
\t\t\t\t\t\t\t\t\t\t\t<button
\t\t\t\t\t\t\t\t\t\t\t\tclass="flex justify-center items-center text-sm w-full text-center rounded-lg px-4 py-2 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
\t\t\t\t\t\t\t\t\t\t\t\ttype="button"
\t\t\t\t\t\t\t\t\t\t\t\tdisabled={guestLoading}
\t\t\t\t\t\t\t\t\t\t\t\ton:click={guestSignInHandler}
\t\t\t\t\t\t\t\t\t\t\t>
\t\t\t\t\t\t\t\t\t\t\t\t{#if guestLoading}
\t\t\t\t\t\t\t\t\t\t\t\t\t<Spinner className="size-4 mr-2" />
\t\t\t\t\t\t\t\t\t\t\t\t{/if}
\t\t\t\t\t\t\t\t\t\t\t\t<span>{$i18n.t('Continue as Guest')} &rarr;</span>
\t\t\t\t\t\t\t\t\t\t\t</button>
\t\t\t\t\t\t\t\t\t\t\t<button
\t\t\t\t\t\t\t\t\t\t\t\tclass="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition"
\t\t\t\t\t\t\t\t\t\t\t\ttype="button"
\t\t\t\t\t\t\t\t\t\t\t\ton:click={() => { showGuestEmailInput = false; guestEmail = ''; }}
\t\t\t\t\t\t\t\t\t\t\t>
\t\t\t\t\t\t\t\t\t\t\t\t{$i18n.t('Cancel')}
\t\t\t\t\t\t\t\t\t\t\t</button>
\t\t\t\t\t\t\t\t\t\t</div>
\t\t\t\t\t\t\t\t\t{:else}
\t\t\t\t\t\t\t\t\t\t<button
\t\t\t\t\t\t\t\t\t\t\tclass="flex justify-center items-center text-sm w-full text-center text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
\t\t\t\t\t\t\t\t\t\t\ttype="button"
\t\t\t\t\t\t\t\t\t\t\ton:click={guestSignInHandler}
\t\t\t\t\t\t\t\t\t\t>
\t\t\t\t\t\t\t\t\t\t\t<span>{$i18n.t('or continue as guest')} &rarr;</span>
\t\t\t\t\t\t\t\t\t\t</button>
\t\t\t\t\t\t\t\t\t{/if}"""
    if old_guest_button in c and "showGuestEmailInput" not in c.split(old_guest_button)[1][:50]:
        c = c.replace(old_guest_button, new_guest_template)
        print("  [OK] Replaced guest button with email input template")

    write_file(f, c)
    print("  [OK] auth +page.svelte patched")


def patch_guest_endpoint(root: Path):
    """backend/open_webui/routers/auths.py — Replace guest endpoint with email-based flow."""
    f = root / "backend" / "open_webui" / "routers" / "auths.py"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # Replace the old auto-generate guest endpoint with email-based one
    old_guest = '''@router.post("/guest", response_model=SessionUserResponse)
async def guest_signin(
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
):
    """
    Create a temporary guest account with limited permissions.
    No form fields required — auto-generates a throwaway identity.
    Guest JWT expires in 3 hours. Guest role has restricted permissions
    enforced at both backend (access_control.py) and frontend.
    """
    client_ip = request.client.host if request.client else "unknown"
    if signin_rate_limiter.is_limited(f"guest:{client_ip}"):
        raise HTTPException(429, detail=ERROR_MESSAGES.RATE_LIMIT_EXCEEDED)

    # Auto-generate guest identity
    guest_uuid = str(uuid.uuid4())
    guest_email = f"guest_{guest_uuid[:8]}@guest.local"
    guest_name = "Guest"
    guest_password = get_password_hash(str(uuid.uuid4()))

    user = Auths.insert_new_auth(
        email=guest_email,
        password=guest_password,
        name=guest_name,
        profile_image_url="/user.png",
        role="guest",
        db=db,
    )
    if not user:
        raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)

    # Guest JWT expires in 3 hours (not the global JWT_EXPIRES_IN)
    from datetime import timedelta as _td

    guest_expires = _td(hours=3)
    expires_at = int(time.time()) + int(guest_expires.total_seconds())

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

    from open_webui.config import GUEST_USER_PERMISSIONS

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
    }'''

    if old_guest in c and "GuestSigninForm" not in c:
        new_guest = read_file(Path(__file__).parent / "fragments" / "guest_endpoint.py")
        c = c.replace(old_guest, new_guest)
        print("  [OK] Replaced guest endpoint with email-based flow")
    elif "GuestSigninForm" in c:
        print("  [SKIP] Email-based guest endpoint already present")
    else:
        print("  [WARN] Could not find old guest endpoint to replace")

    write_file(f, c)
    print("  [OK] auths.py patched")


def patch_guest_api_frontend(root: Path):
    """src/lib/apis/auths/index.ts — Update userGuestSignIn to accept email."""
    f = root / "src" / "lib" / "apis" / "auths" / "index.ts"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    old_fn = "export const userGuestSignIn = async () => {"
    new_fn = "export const userGuestSignIn = async (email: string) => {"
    if old_fn in c:
        c = c.replace(old_fn, new_fn)
        print("  [OK] Updated userGuestSignIn signature")

    # Add body with email to the guest fetch call ONLY.
    # Previous version used a broad anchor that matched ALL fetch calls in the
    # file, injecting `body: JSON.stringify({ email })` into getSessionUser()
    # and userSignOut() where `email` is not in scope — causing a
    # ReferenceError that wiped localStorage.token on every page refresh.
    old_guest_fetch = """\tfetch(`${WEBUI_API_BASE_URL}/auths/guest`, {
\t\tmethod: 'POST',
\t\theaders: {
\t\t\t'Content-Type': 'application/json'
\t\t},
\t\tcredentials: 'include'
\t})"""
    new_guest_fetch = """\tfetch(`${WEBUI_API_BASE_URL}/auths/guest`, {
\t\tmethod: 'POST',
\t\theaders: {
\t\t\t'Content-Type': 'application/json'
\t\t},
\t\tcredentials: 'include',
\t\tbody: JSON.stringify({ email })
\t})"""
    if old_guest_fetch in c:
        c = c.replace(old_guest_fetch, new_guest_fetch)
        print("  [OK] Added email body to guest fetch")
    elif "JSON.stringify({ email })" in c:
        print("  [SKIP] Guest API already sends email")
    else:
        print("  [WARN] Could not locate guest fetch block — manual check needed")

    write_file(f, c)
    print("  [OK] auths/index.ts patched")


def patch_users_api_roles(root: Path):
    """backend/open_webui/routers/users.py — Add roles filter parameter."""
    f = root / "backend" / "open_webui" / "routers" / "users.py"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # Add roles parameter to get_users endpoint
    old_sig = """async def get_users(
    query: Optional[str] = None,
    order_by: Optional[str] = None,
    direction: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_admin_user),"""
    new_sig = """async def get_users(
    query: Optional[str] = None,
    order_by: Optional[str] = None,
    direction: Optional[str] = None,
    page: Optional[int] = 1,
    roles: Optional[str] = None,
    user=Depends(get_admin_user),"""

    if "roles: Optional[str] = None" not in c:
        c = replace_text(c, old_sig, new_sig, "Add roles param to get_users")

        # Add roles filter processing (handles both single-quote and double-quote styles)
        old_filter_sq = "    filter['direction'] = direction\n\n    filter['direction'] = direction\n\n    result = Users.get_users"
        new_filter_sq = "    if roles:\n        filter['roles'] = [r.strip() for r in roles.split(',') if r.strip()]\n\n    filter['direction'] = direction\n\n    filter['direction'] = direction\n\n    result = Users.get_users"
        old_filter_dq = '    filter["direction"] = direction\n\n    result = Users.get_users'
        new_filter_dq = '    if roles:\n        filter["roles"] = [r.strip() for r in roles.split(",") if r.strip()]\n\n    filter["direction"] = direction\n\n    result = Users.get_users'
        if old_filter_sq in c:
            c = replace_text(c, old_filter_sq, new_filter_sq, "Add roles to filter dict")
        else:
            c = replace_text(c, old_filter_dq, new_filter_dq, "Add roles to filter dict")
    else:
        print("  [SKIP] roles parameter already present")

    write_file(f, c)
    print("  [OK] users.py router patched")


def patch_users_frontend_api(root: Path):
    """src/lib/apis/users/index.ts — Add roles parameter to getUsers."""
    f = root / "src" / "lib" / "apis" / "users" / "index.ts"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # Add roles param to function signature
    old_sig = """export const getUsers = async (
\ttoken: string,
\tquery?: string,
\torderBy?: string,
\tdirection?: string,
\tpage = 1
) => {"""
    new_sig = """export const getUsers = async (
\ttoken: string,
\tquery?: string,
\torderBy?: string,
\tdirection?: string,
\tpage = 1,
\troles?: string
) => {"""

    if "roles?: string" not in c:
        c = replace_text(c, old_sig, new_sig, "Add roles param to getUsers")

        # Add roles to searchParams
        direction_block = """\tif (direction) {
\t\tsearchParams.set('direction', direction);
\t}"""
        direction_with_roles = """\tif (direction) {
\t\tsearchParams.set('direction', direction);
\t}

\tif (roles) {
\t\tsearchParams.set('roles', roles);
\t}"""
        c = replace_text(c, direction_block, direction_with_roles, "Add roles searchParam")
    else:
        print("  [SKIP] roles parameter already present in getUsers")

    write_file(f, c)
    print("  [OK] users/index.ts patched")


def patch_users_admin_guests_tab(root: Path):
    """src/lib/components/admin/Users.svelte — Add Guests tab."""
    f = root / "src" / "lib" / "components" / "admin" / "Users.svelte"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # 1. Add 'guests' to valid tab list
    old_tabs = "selectedTab = ['overview', 'groups'].includes(tabFromPath) ? tabFromPath : 'overview';"
    new_tabs = "selectedTab = ['overview', 'guests', 'groups'].includes(tabFromPath) ? tabFromPath : 'overview';"
    if "guests" not in c:
        c = replace_text(c, old_tabs, new_tabs, "Add guests to tab list")

        # 2. Add Guests tab link before Groups link (upstream uses <a> tags now)
        # Try new <a>-based format first, fall back to old <button>-based format
        groups_anchor_a = '<a\n\t\t\tid="groups"\n\t\t\thref="/admin/users/groups"'
        groups_anchor_btn = '<button\n\t\t\tid="groups"\n\t\t\tclass="px-0.5 py-1 min-w-fit rounded-lg'
        guests_tab_a = '''<a
\t\t\tid="guests"
\t\t\thref="/admin/users/guests"
\t\t\tdraggable="false"
\t\t\tclass="px-0.5 py-1 min-w-fit rounded-lg lg:flex-none flex text-right transition select-none {selectedTab ===
\t\t\t'guests'
\t\t\t\t? ''
\t\t\t\t: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
\t\t>
\t\t\t<div class=" self-center mr-2">
\t\t\t\t<svg
\t\t\t\t\txmlns="http://www.w3.org/2000/svg"
\t\t\t\t\tviewBox="0 0 16 16"
\t\t\t\t\tfill="currentColor"
\t\t\t\t\tclass="size-4"
\t\t\t\t>
\t\t\t\t\t<path
\t\t\t\t\t\tfill-rule="evenodd"
\t\t\t\t\t\td="M15 8A7 7 0 1 1 1 8a7 7 0 0 1 14 0Zm-5-2a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm-2 9c-2.227 0-4.193-1.14-5.343-2.87a6.958 6.958 0 0 1 2.076-1.633A5.012 5.012 0 0 1 8 9.5c1.153 0 2.216.39 3.063 1.044.383.295.74.634 1.064 1.017A6.978 6.978 0 0 1 8 15Z"
\t\t\t\t\t\tclip-rule="evenodd"
\t\t\t\t\t/>
\t\t\t\t</svg>
\t\t\t</div>
\t\t\t<div class=" self-center">{$i18n.t('Guests')}</div>
\t\t</a>

\t\t'''
        guests_tab_btn = """<button
\t\t\tid="guests"
\t\t\tclass="px-0.5 py-1 min-w-fit rounded-lg lg:flex-none flex text-right transition {selectedTab ===
\t\t\t'guests'
\t\t\t\t? ''
\t\t\t\t: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
\t\t\ton:click={() => {
\t\t\t\tgoto('/admin/users/guests');
\t\t\t}}
\t\t>
\t\t\t<div class=" self-center mr-2">
\t\t\t\t<svg
\t\t\t\t\txmlns="http://www.w3.org/2000/svg"
\t\t\t\t\tviewBox="0 0 16 16"
\t\t\t\t\tfill="currentColor"
\t\t\t\t\tclass="size-4"
\t\t\t\t>
\t\t\t\t\t<path
\t\t\t\t\t\tfill-rule="evenodd"
\t\t\t\t\t\td="M15 8A7 7 0 1 1 1 8a7 7 0 0 1 14 0Zm-5-2a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm-2 9c-2.227 0-4.193-1.14-5.343-2.87a6.958 6.958 0 0 1 2.076-1.633A5.012 5.012 0 0 1 8 9.5c1.153 0 2.216.39 3.063 1.044.383.295.74.634 1.064 1.017A6.978 6.978 0 0 1 8 15Z"
\t\t\t\t\t\tclip-rule="evenodd"
\t\t\t\t\t/>
\t\t\t\t</svg>
\t\t\t</div>
\t\t\t<div """
        if groups_anchor_a in c:
            c = replace_text(c, groups_anchor_a, guests_tab_a + groups_anchor_a, "Add Guests tab link")
        else:
            c = replace_text(c, groups_anchor_btn, guests_tab_btn + "\n\n\t\t" + groups_anchor_btn, "Add Guests tab button")

        # 3. Update tab rendering — add guests tab between overview and groups
        old_render = """\t\t{#if selectedTab === 'overview'}
\t\t\t<UserList />
\t\t{:else if selectedTab === 'groups'}"""
        new_render = """\t\t{#if selectedTab === 'overview'}
\t\t\t<UserList excludeRoles={['guest']} />
\t\t{:else if selectedTab === 'guests'}
\t\t\t<UserList filterRole="guest" />
\t\t{:else if selectedTab === 'groups'}"""
        c = replace_text(c, old_render, new_render, "Add Guests tab rendering")
    else:
        print("  [SKIP] Guests tab already present")

    write_file(f, c)
    print("  [OK] Users.svelte patched")


def patch_userlist_role_filter(root: Path):
    """src/lib/components/admin/Users/UserList.svelte — Add role filtering props."""
    f = root / "src" / "lib" / "components" / "admin" / "Users" / "UserList.svelte"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    if "export let filterRole" not in c:
        # Add role filter props after i18n context
        anchor = "\tconst i18n = getContext('i18n');\n\n\tlet page = 1;"
        replacement = """\tconst i18n = getContext('i18n');

\t// Optional role filtering props
\texport let filterRole: string | undefined = undefined;   // e.g. "guest" — show only guests
\texport let excludeRoles: string[] | undefined = undefined; // e.g. ["guest"] — hide guests from overview

\t// Build the roles query param: "guest" for include, "!guest" for exclude
\t$: rolesParam = filterRole
\t\t? filterRole
\t\t: excludeRoles?.length
\t\t\t? excludeRoles.map((r) => `!${r}`).join(',')
\t\t\t: undefined;

\tlet page = 1;"""
        c = replace_text(c, anchor, replacement, "Add role filter props")

        # Update getUserList to pass roles
        old_call = "const res = await getUsers(localStorage.token, query, orderBy, direction, page).catch("
        new_call = "const res = await getUsers(localStorage.token, query, orderBy, direction, page, rolesParam).catch("
        c = replace_text(c, old_call, new_call, "Pass roles to getUsers")
    else:
        print("  [SKIP] Role filter props already present")

    write_file(f, c)
    print("  [OK] UserList.svelte patched")


def patch_model_access_control(root: Path):
    """backend/open_webui/utils/models.py — Include 'guest' role in model access filtering."""
    f = root / "backend" / "open_webui" / "utils" / "models.py"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    # Handle both double-quote and single-quote styles (upstream may use either)
    old_dq = '''    if (
        user.role == "user"
        or (user.role == "admin" and not BYPASS_ADMIN_ACCESS_CONTROL)
    ) and not BYPASS_MODEL_ACCESS_CONTROL:'''
    new_dq = '''    if (
        user.role in ("user", "guest")
        or (user.role == "admin" and not BYPASS_ADMIN_ACCESS_CONTROL)
    ) and not BYPASS_MODEL_ACCESS_CONTROL:'''
    old_sq = "        user.role == 'user' or (user.role == 'admin' and not BYPASS_ADMIN_ACCESS_CONTROL)"
    new_sq = "        user.role in ('user', 'guest') or (user.role == 'admin' and not BYPASS_ADMIN_ACCESS_CONTROL)"

    if "guest" in c and "user.role in" in c:
        print("  [SKIP] guest role already in model access filter")
    elif old_dq in c:
        c = replace_text(c, old_dq, new_dq, "Add guest role to model access filter")
    else:
        c = replace_text(c, old_sq, new_sq, "Add guest role to model access filter")
    write_file(f, c)
    print("  [OK] models.py patched — guest role included in access control")


def patch_requirements(root: Path):
    """backend/requirements.txt — Add neo4j driver so it's baked into the Docker image."""
    f = root / "backend" / "requirements.txt"
    print(f"\n[PATCH] {f.relative_to(root)}")
    c = read_file(f)

    if "neo4j" not in c:
        # Insert before the ## Databases section
        anchor = "## Databases\npymongo"
        injection = "## Neo4j (RegOS Graph-RAG)\nneo4j\n\n## Databases\npymongo"
        c = replace_text(c, anchor, injection, "Add neo4j to requirements.txt")
    else:
        print("  [SKIP] neo4j already in requirements.txt")

    write_file(f, c)
    print("  [OK] requirements.txt patched")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 apply-patches.py /path/to/open-webui")
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()

    if not (root / "backend" / "open_webui").is_dir():
        print(f"ERROR: {root} does not look like an Open WebUI source tree")
        sys.exit(1)

    print("=" * 60)
    print("  RegOS Source Patcher")
    print(f"  Target: {root}")
    print("=" * 60)

    errors = []

    # Copy new files
    script_dir = Path(__file__).parent
    new_files_dir = script_dir / "new"
    if new_files_dir.is_dir():
        print("\n[COPY] New files...")
        for src_file in new_files_dir.rglob("*"):
            if src_file.is_file():
                rel = src_file.relative_to(new_files_dir)
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst)
                print(f"  [OK] {rel}")

    # Apply surgical patches
    patches = [
        patch_backend_config,
        patch_backend_main,
        patch_backend_configs_router,
        patch_frontend_configs_api,
        patch_admin_layout,
        patch_app_layout,
        patch_auth_page,
        patch_guest_endpoint,
        patch_guest_api_frontend,
        patch_users_api_roles,
        patch_users_frontend_api,
        patch_users_admin_guests_tab,
        patch_userlist_role_filter,
        patch_model_access_control,
        patch_requirements,
    ]

    for patch_fn in patches:
        try:
            patch_fn(root)
        except PatchError as e:
            errors.append(str(e))
            print(f"  [ERROR] {e}")
        except Exception as e:
            errors.append(f"{patch_fn.__name__}: {e}")
            print(f"  [ERROR] {patch_fn.__name__}: {e}")

    print("\n" + "=" * 60)
    if errors:
        print(f"  COMPLETED WITH {len(errors)} ERROR(S):")
        for err in errors:
            print(f"    - {err}")
        sys.exit(1)
    else:
        print("  ALL PATCHES APPLIED SUCCESSFULLY")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
