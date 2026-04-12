"""
LangGraph Orchestrator for Saras Client Onboarding (Multi-Env)
==============================================================
Runs the full onboarding pipeline: account creation -> email verification ->
token retrieval -> role assignment -> GCS upload -> warehouse creation.

Usage:
  python onboard_client.py --env dev --first John --last Doe --email john@example.com --company Acme --project-id my-project --dataset my_dataset
  python onboard_client.py --env dev  # interactive mode
  python onboard_client.py  # fully interactive
"""

import sys
import argparse
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

from env_config import get_config, add_env_arg
from step1_create_account import create_account
# step2 uses playwright/greenlet — lazy-import to avoid DLL issues when skipping email
# from step2_verify_email import verify_and_set_password
from step3_get_token import get_auth_token, set_manual_token
from step4_assign_roles import assign_roles, verify_user_exists
from gcs_upload import upload_directory
from create_warehouse_api import create_warehouse
from browser_login import login_and_capture_token


class OnboardingState(TypedDict):
    env: str
    first_name: str
    last_name: str
    email: str
    company_name: str
    product_type: str
    revenue: str
    password: str
    project_id: str
    dataset: str
    logic_dir: Optional[str]
    yaml_dir: Optional[str]
    super_admin_token: Optional[str]

    # Generated values
    user_id: Optional[int]
    company_id: Optional[str]
    auth_token: Optional[str]       # Super admin token (for roles, user lookup)
    user_token: Optional[str]       # New user's token (for warehouse creation)
    errors: list[str]


def format_error(state: OnboardingState, step: str, error: str) -> OnboardingState:
    state["errors"].append(f"[{step}] {error}")
    print(f"\n  Error in {step}: {error}")
    return state


def node_create_account(state: OnboardingState):
    print("\n[Node: Create Account] Executing...")
    result = create_account(
        first_name=state["first_name"],
        last_name=state["last_name"],
        email=state["email"],
        company=state["company_name"],
        revenue=state["revenue"],
        product=state["product_type"],
        env=state["env"],
    )
    if result.get("success"):
        state["user_id"] = result.get("user_id")
        print(f"  Account Created: User ID {state['user_id']}")
    else:
        state = format_error(state, "Create Account", result.get("error"))
    return state


def node_verify_email(state: OnboardingState):
    if state["errors"]:
        return state

    print("\n[Node: Verify Email] Executing via Playwright...")
    cfg = get_config(state["env"])
    try:
        from step2_verify_email import verify_and_set_password
        result = verify_and_set_password(
            target_email=state["email"],
            password=state["password"],
            outlook_email=cfg.OUTLOOK_EMAIL,
            outlook_pw=cfg.OUTLOOK_PASSWORD,
            headless=True,
            env=state["env"],
        )
        if result.get("success"):
            print(f"  Email verified and password set")
        else:
            state = format_error(state, "Verify Email", result.get("error"))
    except Exception as e:
        import traceback
        err_msg = f"{repr(e)}\n{traceback.format_exc()}"
        state = format_error(state, "Verify Email", err_msg)
    return state


def node_get_token(state: OnboardingState):
    """
    Get super admin token, then lookup the NEW user's real company_id
    via GET /user/{userId}. This avoids using the admin's company_id.

    - DEV: Firebase REST API (auto, we have the key)
    - TEST/PROD: Playwright browser login OR pre-cached manual token
    """
    if state["errors"]:
        return state
    print("\n[Node: Get Admin Token & Lookup User] Executing...")
    cfg = get_config(state["env"])

    if not cfg.REQUIRES_MANUAL_TOKEN:
        # DEV/TEST: Firebase auto-login
        auth_result = get_auth_token(
            cfg.SUPER_ADMIN_EMAIL, cfg.SUPER_ADMIN_PASSWORD, env=state["env"]
        )
    else:
        # PROD: Use pre-cached token if provided at startup, else browser login
        if state.get("super_admin_token"):
            print(f"  Using pre-cached admin token")
            auth_result = {"success": True, "id_token": state["super_admin_token"]}
        else:
            print(f"  Logging in as super admin via browser...")
            auth_result = login_and_capture_token(
                email=cfg.SUPER_ADMIN_EMAIL,
                password=cfg.SUPER_ADMIN_PASSWORD,
                env=state["env"],
                headless=True,
            )

    if not auth_result.get("success"):
        return format_error(state, "Get Admin Token", auth_result.get("error"))

    state["auth_token"] = auth_result.get("id_token")
    admin_token = state["auth_token"]
    print(f"  [Admin Token Captured]: {str(admin_token)[:40]}...[TRUNCATED]")
    print("  -> Going to use this token to authenticate with User API and assign IQ Admin roles.")

    # Now lookup the NEW user to get their real company_id
    if state.get("user_id"):
        print(f"  Looking up User {state['user_id']} to get real company_id...")
        lookup = verify_user_exists(state["user_id"], admin_token, env=state["env"])
        if lookup.get("success"):
            user_data = lookup["user"]
            real_company_id = user_data.get("companyId") or user_data.get("company_id") or user_data.get("company", {}).get("companyId")
            if real_company_id:
                state["company_id"] = real_company_id
                print(f"  User's Company ID: {state['company_id']}")
            else:
                print(f"  Warning: User data did not contain companyId. Data: {user_data}")
        else:
            print(f"  Warning: Could not lookup user: {lookup.get('error')}")

    if not state.get("company_id"):
        print(f"  Warning: company_id still unknown — GCS upload may fail.")

    return state


def node_assign_roles(state: OnboardingState):
    if state["errors"] or not state.get("user_id"):
        return state
    print("\n[Node: Assign Roles] Executing via Super Admin...")
    p_type = "IQ" if "iq" in state["product_type"].lower() else "DATON"
    roles_to_assign = ["iq admin"]

    result = assign_roles(
        user_id=state["user_id"],
        role_names=roles_to_assign,
        product_type=p_type,
        env=state["env"],
    )
    if result.get("success"):
        print(f"  Roles assigned successfully.")
    else:
        state = format_error(state, "Assign Roles", result.get("error"))
    return state


def node_get_user_token(state: OnboardingState):
    """
    Sign in as the NEW user to get their bearer token.
    This token is needed for warehouse creation (API requires the user's own token).
    """
    if state["errors"]:
        return state
    print("\n[Node: Get New User Token] Executing...")
    cfg = get_config(state["env"])
    
    import time
    max_retries = 3
    auth_result = {}
    
    for attempt in range(1, max_retries + 1):
        if not cfg.REQUIRES_MANUAL_TOKEN:
            print(f"  Signing in as {state['email']} via Firebase API directly (Attempt {attempt})...")
            auth_result = get_auth_token(state["email"], state["password"], env=state["env"])
        else:
            print(f"  Signing in as {state['email']} via browser (Playwright) (Attempt {attempt})...")
            print(f"  A browser window will open, log in automatically, and capture the token.")
            auth_result = login_and_capture_token(
                email=state["email"],
                password=state["password"],
                env=state["env"],
                headless=True,
            )
            
        if auth_result.get("success"):
            # Check if custom claims (userId, companyId, AND backend roles) have propagated
            u_id = auth_result.get("user_id")
            c_id = auth_result.get("company_id")
            jwt_data = auth_result.get("jwt_payload", {})
            
            # The backend stores roles either in 'saras_claims', 'roles', or inside 'roleIds'
            has_claims = bool(jwt_data.get("saras_claims") or jwt_data.get("roleIds") or jwt_data.get("roles"))
            
            if u_id and c_id and has_claims:
                print(f"  -> Claims fully synced internally! (Roles: {jwt_data.get('saras_claims')})")
                break
            else:
                print(f"  [Wait] Role claims not propagated to Firebase yet (uid={u_id}, claims={has_claims}). Retrying in 5s...")
                time.sleep(5)
        else:
            break

    if auth_result.get("success"):
        state["user_token"] = auth_result.get("id_token")
        tok = state["user_token"]
        print(f"  [User Token Captured]: {str(tok)[:40]}...[TRUNCATED]")
        print("  -> Going to use this token to authorize GCS folder creation, API requests, and BigQuery Warehouse.")
        
        comp_id = auth_result.get("company_id")
        if comp_id:
            state["company_id"] = str(comp_id)
            print(f"  -> Extracted Company ID natively from Token payload: {state['company_id']}")
    else:
        state = format_error(state, "Get User Token", auth_result.get("error"))

    return state


def _validate_token_basic(token: str) -> tuple:
    """Validate a JWT token (basic — no admin claims required)."""
    import json
    import base64
    import time

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False, {"error": f"Not a valid JWT (expected 3 parts, got {len(parts)})"}

        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        exp = payload.get("exp", 0)
        now = time.time()
        expires_in_sec = exp - now

        if expires_in_sec <= 0:
            mins_ago = int(abs(expires_in_sec) / 60)
            return False, {"error": f"Token expired {mins_ago} minutes ago. Please get a fresh one."}

        return True, {
            "name": payload.get("name", "Unknown"),
            "email": payload.get("email", "Unknown"),
            "user_id": payload.get("userId"),
            "company_id": payload.get("companyId"),
            "expires_in_min": int(expires_in_sec / 60),
        }

    except Exception as e:
        return False, {"error": f"Could not decode token: {e}"}


def node_upload_gcs(state: OnboardingState):
    if state["errors"] or not state.get("company_id"):
        return state
    print("\n[Node: Upload GCS] Executing...")
    cfg = get_config(state["env"])
    company_id = str(state["company_id"])
    success = True

    if not state.get("logic_dir") and not state.get("yaml_dir"):
        print("  -> SKIPPED: No local directories provided for Business Logic or YAMLs.")

    if state.get("logic_dir"):
        print(f"  -> Uploading logic from {state['logic_dir']}")
        if not upload_directory(company_id, state["logic_dir"], f"{cfg.GCS_BASE_PATH}/company_business_logic", env=state["env"]):
            success = False

    if state.get("yaml_dir"):
        print(f"  -> Uploading yamls from {state['yaml_dir']}")
        if not upload_directory(company_id, state["yaml_dir"], f"{cfg.GCS_BASE_PATH}/company_yamls", env=state["env"]):
            success = False

    if success:
        print("  Completed GCS upload")
    return state


def node_create_warehouse(state: OnboardingState):
    if state["errors"]:
        return state
    if not state.get("user_token"):
        return format_error(state, "Create Warehouse", "No user token available — cannot create warehouse")
    print("\n[Node: Create Warehouse] Executing...")
    result = create_warehouse(
        user_id=state["user_id"],
        token=state["user_token"],       # Use NEW USER's token, not admin's
        company_name=state["company_name"],
        project_id=state["project_id"],
        dataset=state["dataset"],
        env=state["env"],
    )
    if result:
        print("  Warehouse Created")
    else:
        state = format_error(state, "Create Warehouse", "Failed to create warehouse")
    return state


def build_workflow():
    workflow = StateGraph(OnboardingState)

    workflow.add_node("account", node_create_account)
    workflow.add_node("email", node_verify_email)
    workflow.add_node("token", node_get_token)
    workflow.add_node("roles", node_assign_roles)
    workflow.add_node("user_token", node_get_user_token)
    workflow.add_node("gcs", node_upload_gcs)
    workflow.add_node("warehouse", node_create_warehouse)

    workflow.add_edge(START, "account")
    workflow.add_edge("account", "email")
    workflow.add_edge("email", "token")
    workflow.add_edge("token", "roles")
    workflow.add_edge("roles", "user_token")
    workflow.add_edge("user_token", "gcs")
    workflow.add_edge("gcs", "warehouse")
    workflow.add_edge("warehouse", END)

    return workflow.compile()




def _validate_token(token: str) -> tuple:
    """
    Validate a JWT token: check it decodes, isn't expired, has admin claims.
    Returns (is_valid: bool, info: dict).
    """
    import json
    import base64
    import time

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False, {"error": "Not a valid JWT (expected 3 parts, got {})".format(len(parts))}

        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Check expiration
        exp = payload.get("exp", 0)
        now = time.time()
        expires_in_sec = exp - now

        if expires_in_sec <= 0:
            mins_ago = int(abs(expires_in_sec) / 60)
            return False, {"error": f"Token expired {mins_ago} minutes ago. Please get a fresh one."}

        # Check admin claims
        claims = payload.get("saras_claims", [])
        has_admin = any(c in claims for c in ["SarasAdmin", "IQAdmin"])

        if not has_admin:
            return False, {"error": f"Token does not have admin claims. Found: {claims}. Need SarasAdmin or IQAdmin."}

        return True, {
            "name": payload.get("name", "Unknown"),
            "email": payload.get("email", "Unknown"),
            "claims": claims,
            "user_id": payload.get("userId"),
            "company_id": payload.get("companyId"),
            "expires_in_min": int(expires_in_sec / 60),
        }

    except Exception as e:
        return False, {"error": f"Could not decode token: {e}"}


def collect_inputs_interactive(args):
    """Collect all inputs upfront before running the workflow."""
    from env_config import ENVIRONMENTS

    # ── 1. Environment (always first) ────────────────────────────────
    if not args.env:
        env_list = list(ENVIRONMENTS.keys())
        print("\n" + "=" * 60)
        print("  Saras Client Onboarding - Environment Selection")
        print("=" * 60)
        for i, env_name in enumerate(env_list, 1):
            print(f"  {i}. {env_name.upper()}")
        choice = input(f"\nSelect environment (1-{len(env_list)}): ").strip()
        try:
            args.env = env_list[int(choice) - 1]
        except (ValueError, IndexError):
            args.env = env_list[0]
            print(f"  Defaulting to: {args.env}")

    cfg = get_config(args.env)

    # ── 2. All company & project details ─────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  [{cfg.env_name.upper()}] Enter Client Onboarding Details")
    print(f"{'=' * 60}\n")

    print("-- Company Details --")
    args.first = args.first or input("  First Name           : ").strip()
    args.last = args.last or input("  Last Name            : ").strip()
    args.email = args.email or input("  Work Email           : ").strip()
    args.company = args.company or input("  Company Name         : ").strip()

    if not args.product:
        print("\n  Product Options:")
        print("    1. Saras IQ")
        print("    2. Saras Pulse")
        print("    3. Saras Daton")
        print("    4. Other")
        prod_choice = input("  Select product (1-4) [1]: ").strip() or "1"
        product_map = {"1": "Saras IQ", "2": "Saras Pulse", "3": "Saras Daton", "4": "Other"}
        args.product = product_map.get(prod_choice, "Saras IQ")

    if not args.revenue:
        print("\n  Revenue Options:")
        print("    1. <$15M")
        print("    2. $15-50M")
        print("    3. $50-100M")
        print("    4. $100-200M")
        print("    5. $200M+")
        rev_choice = input("  Select revenue (1-5) [1]: ").strip() or "1"
        revenue_map = {"1": "<$15M", "2": "$15-50M", "3": "$50-100M", "4": "$100-200M", "5": "$200M+"}
        args.revenue = revenue_map.get(rev_choice, "<$15M")

    print("\n-- Warehouse / BigQuery Details --")
    args.project_id = args.project_id or input("  GCP Project ID       : ").strip()
    args.dataset = args.dataset or input("  BigQuery Dataset ID  : ").strip()

    print("\n-- Account Security --")
    if not getattr(args, "password", None):
        pw_input = input(f"  New User Password    [{cfg.DEFAULT_PASSWORD}]: ").strip()
        args.password = pw_input if pw_input else cfg.DEFAULT_PASSWORD

    print("\n-- File Uploads (optional) --")
    args.logic_dir = args.logic_dir or input("  Business Logic Dir   (Enter to skip): ").strip() or None
    args.yaml_dir = args.yaml_dir or input("  Company YAML Dir     (Enter to skip): ").strip() or None

    # ── 3. Confirm before executing ──────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  Review - Onboarding [{cfg.env_name.upper()}]")
    print(f"{'=' * 60}")
    print(f"  Environment      : {cfg.env_name.upper()}")
    print(f"  Name             : {args.first} {args.last}")
    print(f"  Email            : {args.email}")
    print(f"  Company          : {args.company}")
    print(f"  Product          : {args.product}")
    print(f"  Revenue          : {args.revenue}")
    print(f"  GCP Project ID   : {args.project_id}")
    print(f"  BigQuery Dataset : {args.dataset}")
    print(f"  Business Logic   : {args.logic_dir or '(none)'}")
    print(f"  Company YAMLs    : {args.yaml_dir or '(none)'}")
    print(f"  Authentication   : {'Automated via Browser' if cfg.REQUIRES_MANUAL_TOKEN else 'Fully Automated via Firebase (No GUI)'}")
    print(f"  Password         : {args.password}")
    print(f"{'=' * 60}")

    confirm = input("\n  Proceed with onboarding? (Y/n): ").strip().lower()
    if confirm in ("n", "no"):
        print("\n  Aborted by user.")
        sys.exit(0)

    return args, cfg


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="LangGraph Orchestrator for Saras Client Onboarding (Multi-Env)")
    add_env_arg(parser)

    parser.add_argument("--first", help="First Name")
    parser.add_argument("--last", help="Last Name")
    parser.add_argument("--password", help="New User Password")
    parser.add_argument("--email", help="Work Email")
    parser.add_argument("--company", help="Company Name")
    parser.add_argument("--product", help="Product (e.g. Saras IQ)")
    parser.add_argument("--revenue", help="Revenue Bracket")
    parser.add_argument("--project-id", help="GCP Project ID")
    parser.add_argument("--dataset", help="BigQuery Dataset")
    parser.add_argument("--logic-dir", help="Path to local business logic files")
    parser.add_argument("--yaml-dir", help="Path to local yaml files")

    args = parser.parse_args()

    # If all required args provided via CLI, use them directly; otherwise go interactive
    all_provided = args.env and args.first and args.last and args.email and args.company and args.project_id and args.dataset
    if all_provided:
        cfg = get_config(args.env)
    else:
        args, cfg = collect_inputs_interactive(args)

    env_name = args.env or "dev"
    super_admin_token = getattr(args, 'super_admin_token', None)

    # Pre-cache the manual token so step3/step4/warehouse won't ask again
    if super_admin_token:
        set_manual_token(env_name, super_admin_token)

    initial_state = OnboardingState(
        env=env_name,
        first_name=args.first,
        last_name=args.last,
        email=args.email,
        company_name=args.company,
        product_type=args.product or "Saras IQ",
        revenue=args.revenue or "<$15M",
        password=args.password,
        project_id=args.project_id,
        dataset=args.dataset,
        logic_dir=args.logic_dir,
        yaml_dir=args.yaml_dir,
        super_admin_token=super_admin_token,
        user_id=None,
        company_id=None,
        auth_token=None,
        user_token=None,
        errors=[],
    )

    print("\n" + "=" * 60)
    print(f"  Starting Onboarding Workflow [{cfg.env_name.upper()}]")
    print("=" * 60)

    app = build_workflow()
    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("  Onboarding Summary")
    print("=" * 60)
    print(f"  Environment : {cfg.env_name.upper()}")
    print(f"  Company     : {final_state['company_name']}")
    print(f"  Email       : {final_state['email']}")
    print(f"  User ID     : {final_state.get('user_id')}")
    print(f"  Company ID  : {final_state.get('company_id')}")
    print(f"  Project ID  : {final_state['project_id']}")
    print(f"  Dataset     : {final_state['dataset']}")

    if final_state["errors"]:
        print("\n  Completed with Errors:")
        for err in final_state["errors"]:
            print(f"  - {err}")
    else:
        print("\n  Onboarding fully successful!")


if __name__ == "__main__":
    main()
