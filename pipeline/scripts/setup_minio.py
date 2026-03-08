
import os
import glob
import json
import mimetypes
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

load_dotenv()

# Configuration (match values.yaml)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000") # Use port-forward or ingress
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "scans")
BASE_DIR = Path(os.getenv("COMMENTARY_DATA_DIR", os.getcwd()))
FRONTEND_PUBLIC_DIR = Path("frontend/public")

import sys

if not SECRET_KEY:
    print("❌ ERROR: MINIO_SECRET_KEY environment variable is not set or empty.")
    sys.exit(1)

def set_public_policy(client, bucket_name):
    """Set Public Read Only policy for the bucket."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": "*"},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
            }
        ]
    }
    client.set_bucket_policy(bucket_name, json.dumps(policy))
    print(f"✅ Public Read policy set for {bucket_name}")

def main(filter_str=None):
    # Strip protocol from endpoint as Minio client requires raw host
    endpoint = MINIO_ENDPOINT.strip()
    secure_connection = False
    
    if endpoint.startswith("https://"):
        endpoint = endpoint.replace("https://", "")
        secure_connection = True
    elif endpoint.startswith("http://"):
        endpoint = endpoint.replace("http://", "")
        
    # Remove any trailing paths (like /scans) if someone adds it to the endpoint var
    if "/" in endpoint:
        # Since http:// was already stripped, the first slash delineates the host from the path
        endpoint = endpoint.split("/")[0]

    print(f"🔌 Connecting to MinIO via '{endpoint}' (secure={secure_connection}) with bucket '{BUCKET_NAME}'...")

    # Initialize Client
    try:
        client = Minio(
            endpoint,
            access_key=ACCESS_KEY,
            secret_key=SECRET_KEY,
            secure=secure_connection,
            region="us-east-1" # Bypasses XML region check which fails on local ingresses
        )
    except Exception as e:
        print(f"❌ Failed to initialize Minio client configuration: {e}")
        sys.exit(1)

    # Make bucket
    try:
        if not client.bucket_exists(BUCKET_NAME):
            client.make_bucket(BUCKET_NAME)
            print(f"✅ Created bucket: {BUCKET_NAME}")
        else:
            print(f"ℹ️ Bucket {BUCKET_NAME} already exists")
    except Exception as e:
        print(f"❌ Critical connection error to MinIO: {e}\nCheck MINIO_ENDPOINT ({endpoint}) or network routing.")
        sys.exit(1)

    # Set Policy
    try:
        set_public_policy(client, BUCKET_NAME)
    except S3Error as e:
        print(f"❌ Error setting policy: {e}")

    # Upload Scans
    print(f"📂 Scanning extracted volumes in {BASE_DIR}...")
    files = list(BASE_DIR.glob("volume*/*.png"))
    files = [f for f in files if f.is_file()]
    
    # Also add the default gill images from frontend public dir
    root_images = list(FRONTEND_PUBLIC_DIR.glob("gill*.png"))
    files.extend(root_images)
    
    # Add KJV Index based on build_bible_index logic
    _env_data_dir = os.getenv("COMMENTARY_DATA_DIR")
    if _env_data_dir:
        kjv_index = Path(_env_data_dir).parent / "kjv_fast_lookup.json"
    else:
        # Fallback to repo root, assuming setup_minio is in scripts/
        kjv_index = Path(__file__).parent.parent.parent / "kjv_fast_lookup.json"
        
    if kjv_index.exists():
        files.append(kjv_index)
    else:
        print(f"⚠️ Warning: {kjv_index} not found. Skipping upload.")
    
    # Apply Filter natively against Volumes instead of arbitrary strings
    if filter_str:
        print(f"🔍 Filtering for Volume: '{filter_str}'")
        # Ensure we keep the global assets (gill_*.png and the kjv index)
        files = [f for f in files if (f in root_images) or (f == kjv_index) or (f"volume{filter_str}" in f.parts)]

    print(f"Found {len(files)} files to sync.")

    for i, file_path in enumerate(files):
        # Rel path in bucket
        # If it's a scan (in BASE_DIR), keep relative structure (e.g., volume1/pageX.png)
        # If it's a default image or index, put at root of bucket
        if BASE_DIR in file_path.parents:
            object_name = file_path.relative_to(BASE_DIR).as_posix()
        else:
            object_name = file_path.name
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        
        try:
            client.fput_object(
                BUCKET_NAME, 
                object_name, 
                str(file_path),
                content_type=content_type,
                part_size=100 * 1024 * 1024  # 100MB threshold bypasses broken multipart proxy XML responses
            )
            if i % 100 == 0:
                print(f"Uploaded {i}/{len(files)}: {object_name}")
        except Exception as e:
            print(f"❌ Failed to upload {object_name}: {e}")
            # Do not sys.exit() here, let it try the rest of the files
            
    print("✅ Sync Complete!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync images to MinIO")
    parser.add_argument("--volume", help="Volume number (e.g. '1') to synchronize exclusively.")
    args = parser.parse_args()
    
    main(filter_str=args.volume)
