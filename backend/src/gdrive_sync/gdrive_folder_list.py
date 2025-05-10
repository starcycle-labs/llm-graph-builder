import os
import csv
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
PARENT_FOLDER_ID = "1o-90rlncgOVfE7LpZIVgSoKGsKWAcnG9"
OUTPUT_CSV = f".logs/folder_list_{datetime.now().strftime('%Y-%m-%d')}.csv"  # Output CSV file with date

def _create_credentials_dict():
    """Create a credentials dictionary from environment variables"""
    return {
        "type": "service_account",
        "project_id": os.getenv("GCP_PROJECT_ID"),
        "private_key_id": os.getenv("GCP_PRIVATE_KEY_ID"),
        "private_key": os.getenv("GCP_PRIVATE_KEY"),
        "client_email": os.getenv("GCP_CLIENT_EMAIL"),
        "client_id": os.getenv("GCP_CLIENT_ID"),
        "auth_uri": os.getenv("GCP_AUTH_URI"),
        "token_uri": os.getenv("GCP_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GCP_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("GCP_CLIENT_CERT_URL"),
        "universe_domain": os.getenv("GCP_UNIVERSE_DOMAIN")
    }

# Authenticate using the service account
def authenticate_gdrive():
    try:
        # Create credentials from environment variables
        creds_dict = _create_credentials_dict()
        
        # Validate required credentials
        required_fields = ["project_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if not creds_dict.get(field)]
        
        if missing_fields:
            raise Exception(f"Missing required Google Drive credentials: {', '.join(missing_fields)}")
        
        # Create credentials object from dictionary
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        raise Exception(f"Failed to authenticate: {str(e)}")

def get_folders(service):
    """Get all folders in the parent folder"""
    try:
        results = service.files().list(
            q=f"'{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="files(id, name, owners)"
        ).execute()
        return results.get('files', [])
    except Exception as e:
        raise Exception(f"Failed to get folders: {str(e)}")

def write_to_csv(folders):
    """Write folder information to CSV file"""
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Folder Name', 'Folder ID', 'Owner Email'])
        for folder in folders:
            writer.writerow([
                folder.get('name', ''),
                folder.get('id', ''),
                folder.get('owners', [{}])[0].get('emailAddress', '')
            ])

if __name__ == "__main__":
    service = authenticate_gdrive()
    folders = get_folders(service)
    write_to_csv(folders)
    print(f"Folder names, IDs, and owners have been written to {OUTPUT_CSV}.") 