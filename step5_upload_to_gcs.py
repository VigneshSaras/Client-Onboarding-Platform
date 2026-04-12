"""
Step 5: Upload files to Google Cloud Storage
=============================================
Usage:
  python step5_upload_to_gcs.py  # runs test upload
"""

import os
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError


def upload_to_gcs(source_file_path: str, bucket_name: str, destination_blob_name: str) -> bool:
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        print(f"Uploading '{source_file_path}' to 'gs://{bucket_name}/{destination_blob_name}'...")
        blob.upload_from_filename(source_file_path)
        print(f"SUCCESS: Uploaded to 'gs://{bucket_name}/{destination_blob_name}'")
        return True

    except GoogleAPIError as api_error:
        print(f"GCP API Error: {api_error}")
        return False
    except FileNotFoundError:
        print(f"Local Error: File '{source_file_path}' not found.")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


if __name__ == "__main__":
    from env_config import get_config
    cfg = get_config()

    print(f"--- Test upload to {cfg.GCS_BUCKET} ---")
    test_path = "test_config_dummy.yaml"
    with open(test_path, "w") as f:
        f.write("name: test_configuration\npurpose: testing_gcs_upload\n")

    upload_to_gcs(test_path, cfg.GCS_BUCKET, f"{cfg.GCS_BASE_PATH}/company_yamls/test_config_dummy.yaml")

    if os.path.exists(test_path):
        os.remove(test_path)
