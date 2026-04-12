"""
Warehouse Creation
==================
Creates a BigQuery warehouse via the IQ API.

Usage (standalone):
  python create_warehouse_api.py --env dev --email demo+test@sarasanalytics.com --company-name "TestCo" --project-id my-gcp-project --dataset my_dataset

Called by the orchestrator with user_id + token directly (no re-auth).
"""

import sys
import argparse
import requests

from env_config import get_config, add_env_arg
from step3_get_token import get_auth_token


def create_warehouse(
    user_id: int = None,
    token: str = None,
    company_name: str = "",
    project_id: str = "",
    dataset: str = "",
    env: str = None,
    # Legacy params for standalone CLI use
    email: str = None,
    password: str = None,
    manual_token: str = None,
) -> bool:
    cfg = get_config(env)

    # If user_id and token provided directly (from orchestrator), use them
    if user_id and token:
        print(f"\n=== [{cfg.env_name}] Creating Warehouse for User {user_id} ===")
    else:
        # Standalone mode: authenticate to get user_id and token
        print(f"\n=== [{cfg.env_name}] Step 1: Getting Auth Token ===")
        auth_result = get_auth_token(email, password, env=env, manual_token=manual_token)

        if not auth_result.get("success"):
            print(f"\nError: Could not retrieve token. Reason: {auth_result.get('error')}")
            return False

        user_id = auth_result.get("user_id")
        token = auth_result.get("id_token")

    if not user_id:
        print("\nError: No user_id available.")
        return False

    print(f"  User ID: {user_id}")

    # Environment-aware warehouse name (e.g. "Google Prod IQ")
    env_label = cfg.env_name.capitalize()
    wh_name = f"{company_name} {env_label} IQ".strip()

    payload = {
        "name": wh_name,
        "user_id": user_id,
        "warehouse_type": "bigquery",
        "is_active": True,
        "config": {
            "project_id": project_id,
            "dataset": dataset
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"  POST {cfg.WAREHOUSE_URL}")

    try:
        response = requests.post(
            cfg.WAREHOUSE_URL,
            json=payload,
            headers=headers,
            timeout=30
        )

        print(f"  Response Status: {response.status_code}")

        if response.status_code in (200, 201):
            print(f"\n  SUCCESS: Warehouse created!")
            print(f"  Response: {response.text}")
            return True
        else:
            print(f"\n  FAILED: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"\n  FAILED: Network error: {e}")
        return False


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Create a warehouse in Saras IQ")
    add_env_arg(parser)
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", default=None, help="User password (default from env config)")
    parser.add_argument("--company-name", required=True, help="Company name for warehouse label")
    parser.add_argument("--project-id", required=True, help="GCP Project ID")
    parser.add_argument("--dataset", required=True, help="BigQuery dataset")
    args = parser.parse_args()

    cfg = get_config(args.env)
    password = args.password or cfg.DEFAULT_PASSWORD

    create_warehouse(
        email=args.email,
        password=password,
        company_name=args.company_name,
        project_id=args.project_id,
        dataset=args.dataset,
        env=args.env,
    )


if __name__ == "__main__":
    main()
