
import os
import shutil
import glob

# Mapping source directories to volume prefixes
SOURCES = [
    (r"C:\Users\cnogr\git\extract\extracted_images", "vol1"),
    (r"C:\Users\cnogr\git\extract\extracted_images_7", "vol7")
]

TARGET_DIR = r"C:\Users\cnogr\git\extract\frontend\public\scans"

def setup_scans():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        print(f"Created {TARGET_DIR}")

    for source_dir, prefix in SOURCES:
        if not os.path.exists(source_dir):
            print(f"Source dir not found: {source_dir}")
            continue
            
        files = glob.glob(os.path.join(source_dir, "*.png"))
        print(f"Found {len(files)} images in {source_dir} for {prefix}")
        
        for f in files:
            filename = os.path.basename(f)
            # New filename: volX_pageY_image1.png
            new_filename = f"{prefix}_{filename}"
            
            target = os.path.join(TARGET_DIR, new_filename)
            # Copy if doesn't exist or if we want to ensure it's there
            shutil.copy2(f, target)
            
    print("Done copying images.")

if __name__ == "__main__":
    setup_scans()
