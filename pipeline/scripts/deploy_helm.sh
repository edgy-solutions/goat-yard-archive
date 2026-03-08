#!/bin/bash
set -e

# Usage: ./scripts/deploy_helm.sh [prod|test] [--force-conflicts]

# K3s sets KUBECONFIG to /etc/rancher/k3s/k3s.yaml by default on Ubuntu sessions.
# We explicitly override this to the user's config to avoid permission denied errors
# when running helm/kubectl without sudo.
export KUBECONFIG=~/.kube/config

ENV=$1
CHART_DIR="./charts/goat-yard-archive"

FORCE_FLAG=""
if [ "$2" == "--force-conflicts" ]; then
    FORCE_FLAG="--force-conflicts"
fi

if [ -z "$ENV" ]; then
    echo "Usage: $0 [prod|test] [--force-conflicts]"
    exit 1
fi

echo "🚀 Deploying to environment: $ENV"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

if ! command_exists helm; then
    echo "❌ Error: 'helm' is not installed."
    exit 1
fi

if ! command_exists kubectl; then
    echo "❌ Error: 'kubectl' is not installed."
    exit 1
fi

if [ "$ENV" == "prod" ]; then
    echo "----------------------------------------"
    echo "📦 PROD: Deploying Backend..."
    echo "----------------------------------------"
    # Ensure namespace exists
    kubectl create namespace gya-backend --dry-run=client -o yaml | kubectl apply -f -
    
    helm upgrade --install gya-backend "$CHART_DIR" \
      -f "$CHART_DIR/values-backend.yaml" \
      --namespace gya-backend \
      $FORCE_FLAG \
      --wait

    echo "----------------------------------------"
    echo "📦 PROD: Deploying Frontend..."
    echo "----------------------------------------"
    # Ensure namespace exists
    kubectl create namespace gya-frontend --dry-run=client -o yaml | kubectl apply -f -
    
    helm upgrade --install gya-frontend "$CHART_DIR" \
      -f "$CHART_DIR/values-frontend.yaml" \
      --namespace gya-frontend \
      $FORCE_FLAG \
      --wait
      
    echo "✅ Production deployment complete!"

elif [ "$ENV" == "test" ]; then
    NAMESPACE="gya-test"
    
    echo "----------------------------------------"
    echo "🛠️  TEST: Setting up Namespace ($NAMESPACE)..."
    echo "----------------------------------------"
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    echo "----------------------------------------"
    echo "🛠️  TEST: Deploying Weaviate (Standalone)..."
    echo "----------------------------------------"
    # Add repo if missing
    helm repo add weaviate https://weaviate.github.io/weaviate-helm 2>/dev/null || true
    helm repo update weaviate
    
    # Deploy Weaviate
    helm upgrade --install weaviate weaviate/weaviate \
      --namespace "$NAMESPACE" \
      --set modules.text2vec-transformers.enabled=true \
      --set modules.text2vec-transformers.tag=sentence-transformers-all-mpnet-base-v2 \
      --wait

    echo "----------------------------------------"
    echo "🛠️  TEST: Deploying Backend Features (Postgres)..."
    echo "----------------------------------------"
    # Deploying backend chart but to test namespace
    # Note: fullnameOverride in values-backend.yaml will keep service names consistent
    helm upgrade --install gya-backend-test "$CHART_DIR" \
      -f "$CHART_DIR/values-backend.yaml" \
      --namespace "$NAMESPACE" \
      $FORCE_FLAG \
      --wait

    echo "----------------------------------------"
    echo "🛠️  TEST: Deploying Frontend Features (API, UI, MinIO)..."
    echo "----------------------------------------"
    # Secrets handling: Provide a generic secrets.yaml or environment-specific secrets-test.yaml
    SECRET_ARGS=""
    if [ -f "$CHART_DIR/secrets.yaml" ]; then
        SECRET_ARGS="$SECRET_ARGS -f $CHART_DIR/secrets.yaml"
    fi
    if [ -f "$CHART_DIR/secrets-test.yaml" ]; then
        SECRET_ARGS="$SECRET_ARGS -f $CHART_DIR/secrets-test.yaml"
    fi

    # Verify values-test.yaml exists
    if [ ! -f "$CHART_DIR/values-test.yaml" ]; then
        echo "❌ Error: $CHART_DIR/values-test.yaml not found!"
        exit 1
    fi

    # Use eval to handle the conditionally concatenated string of secrets files safely
    eval helm upgrade --install gya-frontend-test "$CHART_DIR" \
      -f "$CHART_DIR/values-frontend.yaml" \
      -f "$CHART_DIR/values-test.yaml" \
      $SECRET_ARGS \
      --namespace "$NAMESPACE" \
      $FORCE_FLAG \
      --wait

    echo "✅ Test deployment complete!"
    echo ""
    echo "Run ingestion using:"
    echo "kubectl port-forward svc/weaviate 8080:80 -n $NAMESPACE"
    echo "export WEAVIATE_URL='http://localhost:8080'"

else
    echo "❌ Error: Invalid environment '$ENV'. Use 'prod' or 'test'."
    exit 1
fi
