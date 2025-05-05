# Set your GCP project ID, region and service name
$PROJECT_ID = "starcycle-dev-424300"  # Change this to your project ID
$REGION = "us-central1"          # Change if you're using a different region
$PROXY_NAME = "knowledge-graph-frontend"    # Name for your Cloud Run service
$IMAGE_NAME = "knowledge-graph-frontend"      # Name for your Docker image

# Verify gcloud project
$CURRENT_PROJECT = $(gcloud config get-value project)
if ($CURRENT_PROJECT -ne $PROJECT_ID) {
    Write-Host "Switching to project $PROJECT_ID" -ForegroundColor Yellow
    gcloud config set project $PROJECT_ID
}

# Print the current date and time in a custom format
Write-Output ("Starting deployment at: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

# Build the Docker image with no cache
$BuildPath = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${IMAGE_NAME}/knowledge-graph-frontend:latest"
Write-Host "Build Path: $BuildPath"
docker build --no-cache -t $BuildPath `
  --build-arg DEPLOYMENT_ENV=dev `
  --build-arg VITE_SKIP_AUTH=$env:VITE_SKIP_AUTH `
  --build-arg REACT_APP_AUTH_DISABLED=$env:REACT_APP_AUTH_DISABLED `
  .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Frontend image build failed" -ForegroundColor Red
    exit 1
}

# Push the image to AR
docker push $BuildPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to push frontend image to AR" -ForegroundColor Red
    exit 1
}

# Build and push the oauth proxy image
$OAuthProxyImage = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${IMAGE_NAME}/knowledge-graph-oauth-proxy:latest"
docker build --no-cache -t $OAuthProxyImage ./nginx-proxy
if ($LASTEXITCODE -ne 0) {
    Write-Host "Oauth proxy image build failed" -ForegroundColor Red
    exit 1
}

docker push $OAuthProxyImage
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to push oauth proxy image to AR" -ForegroundColor Red
    exit 1
}

# Deploy using service.yaml
gcloud run services replace service.yaml --region $REGION

# Print the current date and time in a custom format
Write-Output ("Finished deployment at: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
