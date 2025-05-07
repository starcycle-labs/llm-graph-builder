# Set your GCP project ID, region and service name
$PROJECT_ID = "starcycle-dev-424300"  # Change this to your project ID
$REGION = "us-central1"          # Change if you're using a different region
$SERVICE_NAME = "knowledge-graph-backend"    # Name for your Cloud Run service
$IMAGE_NAME = "knowledge-graph-backend"      # Name for your Docker image

# Build the Docker image
$BuildPath = "${REGION}-docker.pkg.dev/${PROJECT_ID}/${IMAGE_NAME}/${SERVICE_NAME}:latest"
Write-Host "Build Path: $BuildPath"

# Check if image exists in registry
Write-Host "Checking for existing image..."
$imageExists = $false
try {
    $result = gcloud artifacts docker images list $BuildPath --format="value(digest)" 2>$null
    if ($result) {
        $imageExists = $true
        Write-Host "Found existing image, pulling for cache..."
        docker pull $BuildPath
    }
} catch {
    Write-Host "No existing image found, will perform full build"
}

# Build the image
Write-Host "Building image..."
docker build --progress=plain -t $BuildPath .

# Push the image to AR
docker push $BuildPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to push image to AR" -ForegroundColor Red
    exit 1
}

# Deploy to Cloud Run
Write-Host "`n=== Deploying to Cloud Run ===" -ForegroundColor Green
gcloud run deploy $SERVICE_NAME `
  --image $BuildPath `
  --platform managed `
  --region $REGION `
  --allow-unauthenticated `
  --port 8080 `
  --project $PROJECT_ID `
  --max-instances 1 `
  --memory 16Gi `
  --cpu 4

# Get the URL of the deployed service
$SERVICE_URL = gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format "value(status.url)" --project $PROJECT_ID
Write-Host "Service deployed at: $SERVICE_URL"

# Print the current date and time in a custom format
Write-Output ("Finished deployment: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

