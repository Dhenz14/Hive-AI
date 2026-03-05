"""Passkeys and WebAuthn — credential creation, authentication, conditional UI, server verification."""

PAIRS = [
    (
        "security/webauthn-registration",
        "Show the full WebAuthn registration flow including credential creation options, browser API calls, and server-side processing of the attestation response.",
        '''WebAuthn registration (credential creation) flow end-to-end:

```
┌────────┐      ┌────────────┐      ┌──────────────┐
│ Browser │ ──▶  │  RP Server │ ──▶  │ Authenticator │
│  (JS)   │ ◀──  │  (Python)  │ ◀──  │  (Platform)   │
└────────┘      └────────────┘      └──────────────┘

1. Browser requests registration options from server
2. Server generates challenge + PublicKeyCredentialCreationOptions
3. Browser calls navigator.credentials.create()
4. Authenticator creates keypair, returns attestation
5. Browser sends attestation to server
6. Server verifies and stores credential
```

```python
# --- Server: generate registration options (FastAPI + py_webauthn) ---

from typing import Optional
from dataclasses import dataclass, field
import secrets
import json

from fastapi import FastAPI, HTTPException, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import webauthn
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialCreationOptions,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    RegistrationCredential,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes

app = FastAPI()

RP_ID = "example.com"
RP_NAME = "Example Corp"
RP_ORIGIN = "https://example.com"


@dataclass
class UserAccount:
    user_id: bytes
    username: str
    display_name: str
    credentials: list[dict] = field(default_factory=list)


# In-memory store (use a real DB in production)
users_db: dict[str, UserAccount] = {}
challenges_db: dict[str, bytes] = {}


class RegistrationOptionsRequest(BaseModel):
    username: str
    display_name: str


@app.post("/api/webauthn/register/options")
async def registration_options(req: RegistrationOptionsRequest) -> JSONResponse:
    """Generate PublicKeyCredentialCreationOptions for registration."""
    # Find or create user
    user = users_db.get(req.username)
    if user is None:
        user = UserAccount(
            user_id=secrets.token_bytes(32),
            username=req.username,
            display_name=req.display_name,
        )
        users_db[req.username] = user

    # Exclude existing credentials to prevent re-registration
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in user.credentials
    ]

    # Generate options using py_webauthn
    options = webauthn.generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=user.user_id,
        user_name=user.username,
        user_display_name=user.display_name,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude_credentials,
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,  # ES256 (-7)
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,  # RS256 (-257)
        ],
        timeout=60000,  # 60 seconds
    )

    # Store challenge for verification
    challenges_db[req.username] = options.challenge

    # Serialize to JSON
    options_json = webauthn.options_to_json(options)
    return JSONResponse(content=json.loads(options_json))
```

```javascript
// --- Browser: call navigator.credentials.create() ---

async function registerPasskey(username, displayName) {
  // Step 1: Get options from server
  const optionsRes = await fetch("/api/webauthn/register/options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, display_name: displayName }),
  });
  const options = await optionsRes.json();

  // Step 2: Decode base64url fields for the browser API
  options.challenge = base64urlToBuffer(options.challenge);
  options.user.id = base64urlToBuffer(options.user.id);
  if (options.excludeCredentials) {
    options.excludeCredentials = options.excludeCredentials.map((c) => ({
      ...c,
      id: base64urlToBuffer(c.id),
    }));
  }

  // Step 3: Create credential via platform authenticator
  let credential;
  try {
    credential = await navigator.credentials.create({
      publicKey: options,
    });
  } catch (err) {
    if (err.name === "InvalidStateError") {
      throw new Error("A passkey already exists for this account.");
    }
    if (err.name === "NotAllowedError") {
      throw new Error("Registration was cancelled or timed out.");
    }
    throw err;
  }

  // Step 4: Encode response for transmission to server
  const attestationResponse = {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      attestationObject: bufferToBase64url(
        credential.response.attestationObject
      ),
      clientDataJSON: bufferToBase64url(credential.response.clientDataJSON),
    },
    authenticatorAttachment: credential.authenticatorAttachment,
  };

  // Add transports if available (important for future authentication)
  if (credential.response.getTransports) {
    attestationResponse.response.transports =
      credential.response.getTransports();
  }

  // Step 5: Send to server for verification
  const verifyRes = await fetch("/api/webauthn/register/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      credential: attestationResponse,
    }),
  });

  if (!verifyRes.ok) {
    const err = await verifyRes.json();
    throw new Error(err.detail || "Registration verification failed");
  }

  return await verifyRes.json();
}

// --- Base64URL helpers ---
function base64urlToBuffer(base64url) {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const pad = base64.length % 4 === 0 ? "" : "=".repeat(4 - (base64.length % 4));
  const binary = atob(base64 + pad);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0)).buffer;
}

function bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
```

```python
# --- Server: verify registration response ---

class RegistrationVerifyRequest(BaseModel):
    username: str
    credential: dict


@app.post("/api/webauthn/register/verify")
async def registration_verify(req: RegistrationVerifyRequest) -> dict:
    """Verify attestation and store the new credential."""
    user = users_db.get(req.username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    challenge = challenges_db.pop(req.username, None)
    if challenge is None:
        raise HTTPException(status_code=400, detail="No pending challenge")

    try:
        # Build RegistrationCredential from the raw dict
        credential = RegistrationCredential.parse_raw(
            json.dumps(req.credential)
        )

        # Verify the attestation
        verification = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Verification failed: {e}",
        )

    # Store the credential for future authentication
    user.credentials.append({
        "credential_id": bytes_to_base64url(verification.credential_id),
        "public_key": bytes_to_base64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        "transports": req.credential.get("response", {}).get("transports", []),
        "aaguid": str(verification.aaguid) if verification.aaguid else None,
        "credential_type": verification.credential_type.value,
        "attestation_format": verification.fmt,
        "created_at": "2026-03-04T00:00:00Z",
    })

    return {
        "status": "ok",
        "credential_id": bytes_to_base64url(verification.credential_id),
        "message": f"Passkey registered for {user.username}",
    }
```

| Registration Step | Actor | Data Exchanged |
|---|---|---|
| 1. Request options | Browser -> Server | username, display_name |
| 2. Generate options | Server | challenge, user.id, rp.id, pubKeyCredParams |
| 3. Create credential | Browser -> Authenticator | options (challenge, rp, user) |
| 4. Attestation response | Authenticator -> Browser | attestationObject, clientDataJSON |
| 5. Send for verify | Browser -> Server | credential.id, attestation, clientDataJSON |
| 6. Verify + store | Server | credential_public_key, sign_count |

Key patterns:

1. **Challenge freshness** -- generate a unique challenge per registration, expire it after use
2. **Exclude credentials** -- pass existing credential IDs to prevent duplicate registration
3. **Resident key preferred** -- enables discoverable credentials (passkeys) without username input
4. **Transport hints** -- store getTransports() result for smarter authenticator selection later
5. **Attestation: none** -- unless you need hardware attestation, skip it to reduce friction
6. **Error mapping** -- map InvalidStateError and NotAllowedError to user-friendly messages
7. **COSE algorithms** -- always support ES256; add RS256 for broader compatibility'''
    ),
    (
        "security/webauthn-authentication",
        "Show the complete WebAuthn authentication (assertion) flow with server challenge generation, browser credential.get(), and server-side assertion verification.",
        '''WebAuthn authentication (assertion) flow:

```
┌────────┐      ┌────────────┐      ┌──────────────┐
│ Browser │ ──▶  │  RP Server │ ──▶  │ Authenticator │
│  (JS)   │ ◀──  │  (Python)  │ ◀──  │  (Platform)   │
└────────┘      └────────────┘      └──────────────┘

1. Browser requests authentication options
2. Server generates challenge + allowCredentials list
3. Browser calls navigator.credentials.get()
4. Authenticator signs challenge, returns assertion
5. Browser sends assertion to server
6. Server verifies signature, updates sign count
```

```python
# --- Server: generate authentication options ---

from webauthn.helpers.structs import (
    PublicKeyCredentialRequestOptions,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
    AuthenticationCredential,
    PublicKeyCredentialType,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
import webauthn

class AuthOptionsRequest(BaseModel):
    username: Optional[str] = None  # None for discoverable credential flow


@app.post("/api/webauthn/auth/options")
async def authentication_options(req: AuthOptionsRequest) -> JSONResponse:
    """Generate authentication options (assertion request)."""
    allow_credentials: list[PublicKeyCredentialDescriptor] = []

    if req.username:
        # Username-provided flow: restrict to user's credentials
        user = users_db.get(req.username)
        if user is None:
            # Don't reveal whether user exists — return valid options anyway
            # The authentication will fail at verify time
            pass
        else:
            allow_credentials = [
                PublicKeyCredentialDescriptor(
                    id=base64url_to_bytes(c["credential_id"]),
                    type=PublicKeyCredentialType.PUBLIC_KEY,
                    transports=c.get("transports", []),
                )
                for c in user.credentials
            ]

    # For discoverable credentials (passkeys), allowCredentials is empty
    # The authenticator will show available passkeys for this RP
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow_credentials if allow_credentials else None,
        user_verification=UserVerificationRequirement.PREFERRED,
        timeout=60000,
    )

    # Store challenge keyed by session or username
    session_key = req.username or "discoverable"
    challenges_db[session_key] = options.challenge

    options_json = webauthn.options_to_json(options)
    return JSONResponse(content=json.loads(options_json))


class AuthVerifyRequest(BaseModel):
    username: Optional[str] = None
    credential: dict


@app.post("/api/webauthn/auth/verify")
async def authentication_verify(req: AuthVerifyRequest) -> dict:
    """Verify assertion and sign the user in."""
    session_key = req.username or "discoverable"
    challenge = challenges_db.pop(session_key, None)
    if challenge is None:
        raise HTTPException(status_code=400, detail="No pending challenge")

    credential_id_b64 = req.credential.get("id", "")

    # Find the stored credential across all users
    stored_cred: Optional[dict] = None
    owner: Optional[UserAccount] = None

    if req.username:
        user = users_db.get(req.username)
        if user:
            for c in user.credentials:
                if c["credential_id"] == credential_id_b64:
                    stored_cred = c
                    owner = user
                    break
    else:
        # Discoverable flow: search all users
        for user in users_db.values():
            for c in user.credentials:
                if c["credential_id"] == credential_id_b64:
                    stored_cred = c
                    owner = user
                    break
            if stored_cred:
                break

    if stored_cred is None or owner is None:
        raise HTTPException(status_code=400, detail="Unknown credential")

    try:
        auth_credential = AuthenticationCredential.parse_raw(
            json.dumps(req.credential)
        )

        verification = webauthn.verify_authentication_response(
            credential=auth_credential,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
            credential_public_key=base64url_to_bytes(stored_cred["public_key"]),
            credential_current_sign_count=stored_cred["sign_count"],
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Authentication failed: {e}",
        )

    # Update sign count to detect cloned authenticators
    stored_cred["sign_count"] = verification.new_sign_count

    # Issue session token (JWT, session cookie, etc.)
    session_token = create_session_token(owner.user_id, owner.username)

    return {
        "status": "ok",
        "username": owner.username,
        "token": session_token,
    }


def create_session_token(user_id: bytes, username: str) -> str:
    """Create a session token after successful authentication."""
    import jwt
    import datetime

    payload = {
        "sub": bytes_to_base64url(user_id),
        "username": username,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=8),
        "auth_method": "webauthn",
    }
    return jwt.encode(payload, "your-secret-key", algorithm="HS256")
```

```javascript
// --- Browser: authenticate with passkey ---

async function authenticateWithPasskey(username = null) {
  // Step 1: Get authentication options
  const optionsRes = await fetch("/api/webauthn/auth/options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  const options = await optionsRes.json();

  // Step 2: Decode challenge
  options.challenge = base64urlToBuffer(options.challenge);

  // Decode allowCredentials if present
  if (options.allowCredentials) {
    options.allowCredentials = options.allowCredentials.map((c) => ({
      ...c,
      id: base64urlToBuffer(c.id),
    }));
  }

  // Step 3: Get assertion from authenticator
  let assertion;
  try {
    assertion = await navigator.credentials.get({
      publicKey: options,
    });
  } catch (err) {
    if (err.name === "NotAllowedError") {
      throw new Error("Authentication cancelled or timed out.");
    }
    throw err;
  }

  // Step 4: Encode assertion for server
  const assertionResponse = {
    id: assertion.id,
    rawId: bufferToBase64url(assertion.rawId),
    type: assertion.type,
    response: {
      authenticatorData: bufferToBase64url(
        assertion.response.authenticatorData
      ),
      clientDataJSON: bufferToBase64url(assertion.response.clientDataJSON),
      signature: bufferToBase64url(assertion.response.signature),
      userHandle: assertion.response.userHandle
        ? bufferToBase64url(assertion.response.userHandle)
        : null,
    },
  };

  // Step 5: Verify on server
  const verifyRes = await fetch("/api/webauthn/auth/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      credential: assertionResponse,
    }),
  });

  if (!verifyRes.ok) {
    throw new Error("Authentication verification failed");
  }

  return await verifyRes.json();
}
```

```python
# --- Sign count validation and clone detection ---

def validate_sign_count(
    stored_count: int,
    reported_count: int,
    credential_id: str,
) -> bool:
    """
    Detect cloned authenticators via sign count anomalies.

    The sign count should always increase. If it doesn't,
    the authenticator may have been cloned.
    """
    if reported_count == 0 and stored_count == 0:
        # Some authenticators don't support sign counters
        return True

    if reported_count > stored_count:
        return True

    # Sign count didn't increase — possible clone
    import logging
    logger = logging.getLogger("webauthn.security")
    logger.warning(
        "Possible authenticator clone detected! "
        f"credential_id={credential_id} "
        f"stored_count={stored_count} "
        f"reported_count={reported_count}"
    )
    return False


# --- Multi-device credential management ---

@app.get("/api/webauthn/credentials")
async def list_credentials(username: str) -> list[dict]:
    """List all registered passkeys for a user."""
    user = users_db.get(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return [
        {
            "credential_id": c["credential_id"][:16] + "...",
            "created_at": c.get("created_at"),
            "last_used": c.get("last_used"),
            "sign_count": c["sign_count"],
            "aaguid": c.get("aaguid"),
            "transports": c.get("transports", []),
        }
        for c in user.credentials
    ]


@app.delete("/api/webauthn/credentials/{credential_id}")
async def delete_credential(username: str, credential_id: str) -> dict:
    """Remove a registered passkey (e.g., lost device)."""
    user = users_db.get(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    original_count = len(user.credentials)
    user.credentials = [
        c for c in user.credentials
        if c["credential_id"] != credential_id
    ]

    if len(user.credentials) == original_count:
        raise HTTPException(status_code=404, detail="Credential not found")

    if len(user.credentials) == 0:
        # Don't let user remove their last credential
        raise HTTPException(
            status_code=400,
            detail="Cannot remove last credential. Register a new one first.",
        )

    return {"status": "ok", "remaining_credentials": len(user.credentials)}
```

| Assertion Field | Purpose | Size |
|---|---|---|
| authenticatorData | RP ID hash + flags + sign count | 37+ bytes |
| clientDataJSON | type, challenge, origin, crossOrigin | ~150 bytes |
| signature | Signed over authenticatorData + SHA256(clientDataJSON) | 64-256 bytes |
| userHandle | user.id from registration (discoverable only) | 0-64 bytes |

Key patterns:

1. **Empty allowCredentials** -- omit for discoverable credential (passkey) flow
2. **Sign count tracking** -- detect cloned authenticators by monitoring counter increments
3. **User enumeration prevention** -- return valid options even for unknown usernames
4. **Transport hints** -- include transports in allowCredentials for better UX
5. **Session tokens** -- issue JWT or session cookie only after successful verification
6. **Credential lifecycle** -- let users list, name, and revoke their passkeys
7. **Timeout handling** -- map NotAllowedError to user-friendly timeout message'''
    ),
    (
        "security/passkey-ux-conditional-ui",
        "Explain passkey UX patterns including conditional UI (autofill), progressive enrollment, and cross-device authentication with code examples.",
        '''Passkey UX patterns: conditional UI, progressive enrollment, and cross-device auth:

```javascript
// --- Conditional UI (WebAuthn autofill) ---
// Allows passkey sign-in from the browser's autofill dropdown
// without showing a separate modal dialog.

async function initConditionalUI() {
  // Feature detection: check if conditional mediation is available
  if (!window.PublicKeyCredential ||
      !PublicKeyCredential.isConditionalMediationAvailable) {
    console.log("Conditional UI not supported");
    return false;
  }

  const isAvailable =
    await PublicKeyCredential.isConditionalMediationAvailable();
  if (!isAvailable) {
    console.log("Conditional mediation not available");
    return false;
  }

  // Get authentication options (no username needed for discoverable)
  const optionsRes = await fetch("/api/webauthn/auth/options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: null }),
  });
  const options = await optionsRes.json();
  options.challenge = base64urlToBuffer(options.challenge);

  // Start conditional mediation — this returns when user picks
  // a passkey from the autofill dropdown
  try {
    const assertion = await navigator.credentials.get({
      publicKey: options,
      mediation: "conditional",  // <-- Key: triggers autofill UI
    });

    // User selected a passkey from autofill — verify it
    return await verifyAssertion(assertion);
  } catch (err) {
    if (err.name === "AbortError") {
      // User typed a password instead — fall through to password flow
      return null;
    }
    throw err;
  }
}

// HTML: the input MUST have autocomplete="username webauthn"
// <input type="text" name="username" autocomplete="username webauthn" />

// Initialize on page load (non-blocking)
document.addEventListener("DOMContentLoaded", () => {
  initConditionalUI().then((result) => {
    if (result?.status === "ok") {
      window.location.href = "/dashboard";
    }
    // If null, user is using password — form handles it
  });
});
```

```javascript
// --- Progressive enrollment: prompt after password login ---

class PasskeyEnrollment {
  constructor() {
    this.DISMISS_KEY = "passkey_prompt_dismissed";
    this.MAX_DISMISSALS = 3;
  }

  shouldPrompt() {
    // Check if platform authenticator is available
    if (!window.PublicKeyCredential) return false;

    // Check dismissal count
    const dismissed = parseInt(
      localStorage.getItem(this.DISMISS_KEY) || "0", 10
    );
    if (dismissed >= this.MAX_DISMISSALS) return false;

    return true;
  }

  async isPasskeyCapable() {
    if (!window.PublicKeyCredential) return false;

    try {
      // Check for platform authenticator (Touch ID, Windows Hello, etc.)
      const available =
        await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
      return available;
    } catch {
      return false;
    }
  }

  async promptAfterLogin(username, displayName) {
    if (!this.shouldPrompt()) return;

    const capable = await this.isPasskeyCapable();
    if (!capable) return;

    // Show enrollment dialog
    const dialog = this.createDialog();
    document.body.appendChild(dialog);

    return new Promise((resolve) => {
      dialog.querySelector("#passkey-enroll-yes").addEventListener(
        "click",
        async () => {
          dialog.remove();
          try {
            await registerPasskey(username, displayName);
            this.showSuccess();
            resolve(true);
          } catch (err) {
            console.error("Passkey enrollment failed:", err);
            resolve(false);
          }
        }
      );

      dialog.querySelector("#passkey-enroll-later").addEventListener(
        "click",
        () => {
          dialog.remove();
          const count = parseInt(
            localStorage.getItem(this.DISMISS_KEY) || "0", 10
          );
          localStorage.setItem(this.DISMISS_KEY, String(count + 1));
          resolve(false);
        }
      );
    });
  }

  createDialog() {
    const dialog = document.createElement("dialog");
    dialog.innerHTML = `
      <div class="passkey-prompt">
        <h2>Simplify your sign-in</h2>
        <p>
          Create a passkey to sign in with your fingerprint, face,
          or screen lock — no password needed.
        </p>
        <div class="passkey-prompt-actions">
          <button id="passkey-enroll-yes" class="btn-primary">
            Create a passkey
          </button>
          <button id="passkey-enroll-later" class="btn-secondary">
            Not now
          </button>
        </div>
      </div>
    `;
    dialog.showModal();
    return dialog;
  }

  showSuccess() {
    // Reset dismissal counter on success
    localStorage.removeItem(this.DISMISS_KEY);
    // Show success toast/banner
  }
}

// Usage after successful password login:
const enrollment = new PasskeyEnrollment();
await enrollment.promptAfterLogin(user.username, user.displayName);
```

```javascript
// --- Cross-device authentication (hybrid transport) ---
// User authenticates on phone for desktop sign-in

async function crossDeviceAuth() {
  const optionsRes = await fetch("/api/webauthn/auth/options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: null }),
  });
  const options = await optionsRes.json();
  options.challenge = base64urlToBuffer(options.challenge);

  // Don't restrict transports — allow hybrid (cross-device)
  // The browser will show QR code for phone-based auth
  if (options.allowCredentials) {
    options.allowCredentials = options.allowCredentials.map((c) => ({
      ...c,
      id: base64urlToBuffer(c.id),
      // Include "hybrid" transport to enable cross-device
      transports: [...(c.transports || []), "hybrid"],
    }));
  }

  try {
    const assertion = await navigator.credentials.get({
      publicKey: options,
    });

    return await verifyAssertion(assertion);
  } catch (err) {
    if (err.name === "NotAllowedError") {
      return { error: "Cross-device authentication cancelled" };
    }
    throw err;
  }
}

// --- Feature detection utility ---

async function getPasskeyCapabilities() {
  const caps = {
    webauthnSupported: !!window.PublicKeyCredential,
    conditionalUIAvailable: false,
    platformAuthenticator: false,
    hybridTransport: false,
  };

  if (!caps.webauthnSupported) return caps;

  try {
    caps.platformAuthenticator =
      await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch { /* ignore */ }

  try {
    if (PublicKeyCredential.isConditionalMediationAvailable) {
      caps.conditionalUIAvailable =
        await PublicKeyCredential.isConditionalMediationAvailable();
    }
  } catch { /* ignore */ }

  // Hybrid is supported on most modern browsers/OSes
  caps.hybridTransport = caps.webauthnSupported &&
    navigator.userAgent.includes("Chrome") || // Chromium
    navigator.userAgent.includes("Safari");    // WebKit

  return caps;
}

// --- Adaptive sign-in page logic ---

async function initSignInPage() {
  const caps = await getPasskeyCapabilities();

  const passwordForm = document.getElementById("password-form");
  const passkeyButton = document.getElementById("passkey-button");

  if (caps.conditionalUIAvailable) {
    // Best UX: show autofill-integrated passkey option
    initConditionalUI();
    // Also show password form as fallback
    passwordForm.style.display = "block";
    passkeyButton.style.display = "none"; // Not needed with conditional UI
  } else if (caps.platformAuthenticator) {
    // Show explicit passkey button
    passkeyButton.style.display = "block";
    passkeyButton.addEventListener("click", () => {
      authenticateWithPasskey();
    });
    passwordForm.style.display = "block";
  } else {
    // No passkey support: password only
    passwordForm.style.display = "block";
    passkeyButton.style.display = "none";
  }
}
```

| UX Pattern | When to Use | Browser Support |
|---|---|---|
| Conditional UI (autofill) | Default sign-in page | Chrome 108+, Safari 16.4+ |
| Explicit passkey button | When conditional UI unavailable | All WebAuthn browsers |
| Progressive enrollment | After password login | All WebAuthn browsers |
| Cross-device (hybrid) | Desktop auth via phone | Chrome 108+, Safari 16+ |
| Re-authentication | Sensitive actions | All WebAuthn browsers |

Key patterns:

1. **Conditional mediation** -- set `mediation: "conditional"` and `autocomplete="username webauthn"` on input
2. **Feature detection first** -- always check `isUserVerifyingPlatformAuthenticatorAvailable()` before showing passkey options
3. **Progressive enrollment** -- prompt after password login, respect dismissals (max 3), reset on success
4. **Fallback gracefully** -- always keep password flow available alongside passkeys
5. **Cross-device via hybrid** -- include "hybrid" transport in allowCredentials for QR-code phone auth
6. **Adaptive UI** -- detect capabilities and show the best available sign-in method
7. **Non-blocking init** -- start conditional UI on DOMContentLoaded without blocking the password form'''
    ),
    (
        "security/webauthn-server-verification",
        "Show comprehensive server-side WebAuthn verification using py_webauthn including attestation parsing, credential storage in a database, and security checks.",
        '''Server-side WebAuthn verification with py_webauthn, database storage, and security checks:

```python
# --- Database models for credential storage (SQLAlchemy) ---

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import (
    Column, String, Integer, LargeBinary, DateTime,
    ForeignKey, Boolean, Text, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    webauthn_user_id: Mapped[bytes] = mapped_column(
        LargeBinary(64), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    credentials: Mapped[list[WebAuthnCredential]] = relationship(
        "WebAuthnCredential", back_populates="user", cascade="all, delete-orphan"
    )


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"
    __table_args__ = (
        Index("ix_credential_id", "credential_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    credential_id: Mapped[bytes] = mapped_column(
        LargeBinary(1024), nullable=False, unique=True
    )
    public_key: Mapped[bytes] = mapped_column(
        LargeBinary(1024), nullable=False
    )
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    aaguid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    fmt: Mapped[str] = mapped_column(String(32), default="none")
    credential_type: Mapped[str] = mapped_column(
        String(32), default="public-key"
    )
    transports: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_discoverable: Mapped[bool] = mapped_column(Boolean, default=False)
    nickname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship("User", back_populates="credentials")
```

```python
# --- Comprehensive verification service ---

from dataclasses import dataclass
from typing import Optional
import logging
import secrets

import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AttestationConveyancePreference,
    AuthenticatorAttachment,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    RegistrationCredential,
    AuthenticationCredential,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("webauthn.service")


@dataclass
class WebAuthnConfig:
    rp_id: str
    rp_name: str
    rp_origin: str | list[str]  # Can be multiple origins
    timeout: int = 60000
    attestation: AttestationConveyancePreference = (
        AttestationConveyancePreference.NONE
    )
    require_user_verification: bool = True


class WebAuthnService:
    """Production WebAuthn service with database-backed credential storage."""

    def __init__(self, config: WebAuthnConfig, db: AsyncSession) -> None:
        self.config = config
        self.db = db
        self._challenge_store: dict[str, bytes] = {}

    # --- Registration ---

    async def generate_registration_options(
        self,
        user: User,
        authenticator_attachment: Optional[AuthenticatorAttachment] = None,
    ) -> dict:
        """Generate registration options with exclude list."""
        # Get existing credentials to exclude
        result = await self.db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user.id)
            .where(WebAuthnCredential.revoked == False)
        )
        existing = result.scalars().all()

        exclude_credentials = [
            PublicKeyCredentialDescriptor(
                id=cred.credential_id,
                type=PublicKeyCredentialType.PUBLIC_KEY,
                transports=cred.transports or [],
            )
            for cred in existing
        ]

        options = webauthn.generate_registration_options(
            rp_id=self.config.rp_id,
            rp_name=self.config.rp_name,
            user_id=user.webauthn_user_id,
            user_name=user.username,
            user_display_name=user.display_name,
            attestation=self.config.attestation,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=authenticator_attachment,
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=(
                    UserVerificationRequirement.REQUIRED
                    if self.config.require_user_verification
                    else UserVerificationRequirement.PREFERRED
                ),
            ),
            exclude_credentials=exclude_credentials,
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.EDDSA,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
            timeout=self.config.timeout,
        )

        # Store challenge (use Redis in production for distributed systems)
        self._challenge_store[str(user.id)] = options.challenge

        return webauthn.options_to_json(options)

    async def verify_registration(
        self,
        user: User,
        credential_json: str,
        nickname: Optional[str] = None,
    ) -> WebAuthnCredential:
        """Verify registration response and store credential."""
        challenge = self._challenge_store.pop(str(user.id), None)
        if challenge is None:
            raise ValueError("No pending registration challenge")

        credential = RegistrationCredential.parse_raw(credential_json)

        # Handle multiple origins (e.g., web + mobile)
        origins = (
            self.config.rp_origin
            if isinstance(self.config.rp_origin, list)
            else [self.config.rp_origin]
        )

        verification = None
        last_error = None
        for origin in origins:
            try:
                verification = webauthn.verify_registration_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=self.config.rp_id,
                    expected_origin=origin,
                    require_user_verification=(
                        self.config.require_user_verification
                    ),
                )
                break
            except Exception as e:
                last_error = e
                continue

        if verification is None:
            raise ValueError(f"Registration verification failed: {last_error}")

        # Check for duplicate credential ID
        existing = await self.db.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.credential_id
                == verification.credential_id
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Credential already registered")

        # Store in database
        db_credential = WebAuthnCredential(
            user_id=user.id,
            credential_id=verification.credential_id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
            aaguid=str(verification.aaguid) if verification.aaguid else None,
            fmt=verification.fmt,
            credential_type=verification.credential_type.value,
            is_discoverable=True,
            nickname=nickname or f"Passkey {len(user.credentials) + 1}",
        )
        self.db.add(db_credential)
        await self.db.commit()

        logger.info(
            "Credential registered",
            extra={
                "user_id": str(user.id),
                "credential_id": bytes_to_base64url(
                    verification.credential_id
                )[:16],
                "fmt": verification.fmt,
                "aaguid": str(verification.aaguid),
            },
        )

        return db_credential

    # --- Authentication ---

    async def verify_authentication(
        self,
        credential_json: str,
        session_key: str,
    ) -> tuple[User, WebAuthnCredential]:
        """Verify authentication assertion and return user."""
        challenge = self._challenge_store.pop(session_key, None)
        if challenge is None:
            raise ValueError("No pending authentication challenge")

        auth_credential = AuthenticationCredential.parse_raw(credential_json)

        # Look up stored credential
        result = await self.db.execute(
            select(WebAuthnCredential)
            .where(
                WebAuthnCredential.credential_id
                == base64url_to_bytes(auth_credential.id)
            )
            .where(WebAuthnCredential.revoked == False)
        )
        stored = result.scalar_one_or_none()
        if stored is None:
            raise ValueError("Unknown or revoked credential")

        # Load user
        user_result = await self.db.execute(
            select(User).where(User.id == stored.user_id)
        )
        user = user_result.scalar_one()

        # Verify assertion
        origins = (
            self.config.rp_origin
            if isinstance(self.config.rp_origin, list)
            else [self.config.rp_origin]
        )

        verification = None
        for origin in origins:
            try:
                verification = webauthn.verify_authentication_response(
                    credential=auth_credential,
                    expected_challenge=challenge,
                    expected_rp_id=self.config.rp_id,
                    expected_origin=origin,
                    credential_public_key=stored.public_key,
                    credential_current_sign_count=stored.sign_count,
                    require_user_verification=(
                        self.config.require_user_verification
                    ),
                )
                break
            except Exception as e:
                last_error = e
                continue

        if verification is None:
            logger.warning(
                "Authentication verification failed",
                extra={"user_id": str(user.id)},
            )
            raise ValueError("Authentication verification failed")

        # Sign count validation
        if not self._validate_sign_count(
            stored.sign_count,
            verification.new_sign_count,
            stored,
        ):
            logger.critical(
                "Possible authenticator clone detected!",
                extra={
                    "user_id": str(user.id),
                    "credential_id": bytes_to_base64url(
                        stored.credential_id
                    )[:16],
                },
            )
            # Optionally revoke the credential
            # stored.revoked = True

        # Update sign count and last used
        stored.sign_count = verification.new_sign_count
        stored.last_used_at = datetime.now(timezone.utc)
        await self.db.commit()

        return user, stored

    def _validate_sign_count(
        self,
        stored: int,
        reported: int,
        credential: WebAuthnCredential,
    ) -> bool:
        """Check sign count for clone detection."""
        if stored == 0 and reported == 0:
            return True  # Authenticator doesn't track sign count
        return reported > stored
```

```python
# --- Security middleware and rate limiting ---

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict


class WebAuthnSecurityMiddleware(BaseHTTPMiddleware):
    """Rate limiting and security headers for WebAuthn endpoints."""

    def __init__(self, app, max_attempts: int = 5, window_seconds: int = 300):
        super().__init__(app)
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/webauthn/"):
            client_ip = request.client.host if request.client else "unknown"

            # Rate limit verification endpoints
            if "/verify" in request.url.path:
                if self._is_rate_limited(client_ip):
                    from starlette.responses import JSONResponse
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many attempts. Try again later."},
                    )
                self._record_attempt(client_ip)

        response = await call_next(request)

        # Security headers for WebAuthn pages
        if request.url.path.startswith("/api/webauthn/"):
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"

        return response

    def _is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        attempts = self._attempts[client_ip]
        # Remove expired attempts
        attempts[:] = [t for t in attempts if now - t < self.window_seconds]
        return len(attempts) >= self.max_attempts

    def _record_attempt(self, client_ip: str) -> None:
        self._attempts[client_ip].append(time.time())
```

| Security Check | Purpose | Consequence if Skipped |
|---|---|---|
| Challenge verification | Prevents replay attacks | Attacker reuses captured assertion |
| Origin validation | Prevents phishing | Assertion from attacker's site accepted |
| RP ID check | Ensures correct relying party | Cross-site credential theft |
| Sign count | Detects cloned authenticators | Cloned keys go unnoticed |
| User verification flag | Ensures biometric/PIN was used | Stolen device can auth without UV |
| Rate limiting | Prevents brute force | Unlimited verification attempts |
| Credential revocation | Disable lost/stolen devices | Compromised credential stays active |

Key patterns:

1. **Multi-origin support** -- verify against multiple origins for web + mobile apps
2. **Database-backed storage** -- store credential_id, public_key, sign_count in PostgreSQL with proper indexes
3. **Credential lifecycle** -- support registration, listing, nickname, revocation, last_used tracking
4. **Clone detection** -- monitor sign count anomalies and alert on possible cloned authenticators
5. **Rate limiting** -- limit verification attempts per IP to prevent brute force
6. **Structured logging** -- log registration and authentication events with credential metadata
7. **No-cache headers** -- prevent caching of WebAuthn API responses to avoid stale challenges'''
    ),
]
