#!/bin/bash
set -e

echo "🐳 Testing Docker Build Locally"
echo "================================"

# Get version from pyproject.toml
VERSION=$(poetry version --short)
echo "📦 Version: $VERSION"

# Generate image name (lowercase)
REPO_NAME=$(basename "$(git config --get remote.origin.url)" .git | tr '[:upper:]' '[:lower:]')
USER_NAME=$(git config --get remote.origin.url | sed 's/.*[:/]\([^/]*\)\/.*/\1/' | tr '[:upper:]' '[:lower:]')
IMAGE_NAME="ghcr.io/${USER_NAME}/${REPO_NAME}"

echo "🏷️  Image name: $IMAGE_NAME"
echo "🏷️  Tags to build:"
echo "   - ${IMAGE_NAME}:${VERSION}-dev"
echo "   - ${IMAGE_NAME}:dev"

# Build the image
echo ""
echo "🔨 Building Docker image..."
docker build \
  --build-arg VERSION="${VERSION}-dev" \
  --tag "${IMAGE_NAME}:${VERSION}-dev" \
  --tag "${IMAGE_NAME}:dev" \
  --platform linux/amd64 \
  .

echo ""
echo "✅ Build completed successfully!"
echo ""
echo "🧪 Test the image:"
echo "   docker run --rm ${IMAGE_NAME}:dev --help"
echo ""
echo "🚀 To push manually (requires authentication):"
echo "   docker login ghcr.io"
echo "   docker push ${IMAGE_NAME}:${VERSION}-dev"
echo "   docker push ${IMAGE_NAME}:dev"
