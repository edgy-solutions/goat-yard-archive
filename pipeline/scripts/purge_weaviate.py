import weaviate
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def purge_weaviate():
    # Connect to Weaviate
    client = weaviate.connect_to_local(
        headers={
            "X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY", "")
        }
    )

    try:
        print("Connected to Weaviate.")
        
        collections_to_purge = ["CommentaryChunk", "TheologicalEntity"]
        
        for collection_name in collections_to_purge:
            if client.collections.exists(collection_name):
                print(f"Deleting collection: {collection_name}...")
                client.collections.delete(collection_name)
                print(f"  Deleted {collection_name}.")
            else:
                print(f"Collection {collection_name} does not exist.")
                
        print("\nPurge complete. All data reset.")
        
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    purge_weaviate()
