import litellm
import os
import pytest
import time

def test_direct_ollama_embedding():
    """Test direct connection to Ollama server"""
    litellm.api_key = "anything"
    api_base = "http://192.168.1.179:11434"
    
    try:
        response = litellm.embedding(
            model="ollama/qwen3-embedding:latest",
            input=["Hello world"],
            api_base=api_base
        )
        assert response is not None
        assert "data" in response
        assert len(response.data) > 0
        assert "embedding" in response.data[0]
        print("Success! Direct Ollama worked.")
    except Exception as e:
        pytest.fail(f"Direct Ollama Failed: {e}")

@pytest.mark.skipif(os.environ.get("TEST_CLUSTER") != "1", reason="Requires cluster proxy to be running")
def test_litellm_proxy_embedding():
    """Test connection through LiteLLM proxy"""
    litellm.api_key = "anything"
    
    # Use environment variable or fallback to cluster DNS
    api_base = os.getenv("LITELLM_PROXY_URL", "http://litellm-service.gya-test.svc.cluster.local:4000")
    
    try:
        response = litellm.embedding(
            model="openai/qwen3-embedding",
            input=["Hello world"],
            api_base=api_base
        )
        assert response is not None
        assert "data" in response
        assert len(response.data) > 0
        assert "embedding" in response.data[0]
        print("Success! Proxy worked.")
    except Exception as e:
        pytest.fail(f"Proxy Failed: {e}")

if __name__ == "__main__":
    test_direct_ollama_embedding()
    # The proxy test will likely fail outside the cluster, but we include it for cluster testing
    print("Run with pytest test/test_litellm_proxy.py")
