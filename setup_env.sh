#!/bin/bash
# Setup script to create .env file for rag_prod.py

echo "Setting up .env file for RAG pipeline..."
echo ""

# Check if .env already exists
if [ -f .env ]; then
    echo "⚠️  .env file already exists. Backing up to .env.backup"
    cp .env .env.backup
fi

# Create .env file
cat > .env << 'EOF'
# Google Cloud Platform Configuration
# REQUIRED: Set your GCP project ID
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# REQUIRED: Set your GCP region
GOOGLE_CLOUD_REGION=us-central1

# Vertex AI Model Configuration
# Embedding model - options: textembedding-gecko@001, textembedding-gecko@003, text-embedding-004
VERTEX_EMBEDDING_MODEL=textembedding-gecko@003

# Text generation model - options: gemini-1.5-pro, gemini-1.5-flash, text-bison@001
VERTEX_TEXT_MODEL=gemini-1.5-pro

# Optional: Path to GCP service account JSON key file
# If not set, will use Application Default Credentials (ADC)
# GCP_SERVICE_ACCOUNT_KEY=/path/to/service-account-key.json

# Cache and Storage Configuration
CACHE_DIR=./rag_cache
FAISS_INDEX_PATH=./rag_cache/faiss.index

# Chunking Parameters
CHUNK_SIZE_WORDS=200
CHUNK_OVERLAP_WORDS=30

# Retrieval Parameters
TOP_K=40
EXPAND_FRACTION=0.15

# Embedding Dimensions (adjust based on your embedding model)
# textembedding-gecko@001: 768
# textembedding-gecko@003: 768
# text-embedding-004: 768
EMBED_DIM=768

# Decoder embedding dimension (for projection MLP)
DECODER_EMB_DIM=4096

# Random seed for reproducibility
RANDOM_SEED=42
EOF

echo "✅ Created .env file"
echo ""
echo "⚠️  IMPORTANT: Please edit .env and set the following required variables:"
echo "   - GOOGLE_CLOUD_PROJECT (your GCP project ID)"
echo "   - VERTEX_EMBEDDING_MODEL (if different from default)"
echo "   - VERTEX_TEXT_MODEL (if different from default)"
echo ""
echo "You can edit it with: nano .env  or  vim .env"

