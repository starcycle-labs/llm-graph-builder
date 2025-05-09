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

# Set up base directory and paths
BASE_DIR = Path.cwd()  # Use current working directory
CREDENTIALS_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_FILE')

if CREDENTIALS_FILE:
    key_file = BASE_DIR / "src" / "gdrive_sync" / CREDENTIALS_FILE
    if key_file.exists():
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_file)

# Authenticate using the service account
def authenticate_gdrive():
    try:
        if not CREDENTIALS_FILE:
            raise Exception("Google Drive credentials file not specified")
        
        key_file = BASE_DIR / "src" / "gdrive_sync" / CREDENTIALS_FILE
        if not key_file.exists():
            raise Exception(f"Credentials file not found at {key_file}")
            
        creds = service_account.Credentials.from_service_account_file(
            str(key_file),
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        raise Exception(f"Failed to authenticate: {str(e)}")

# Get folder names, IDs, and owners from Google Drive
def get_folders(service, folder_id=PARENT_FOLDER_ID):
    """
    Retrieve folder names, IDs, and owners from the specified folder
    """
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'"
    results = service.files().list(
        q=query,
        fields="files(id, name, owners)"
    ).execute()
    return results.get('files', [])

# Write folder names, IDs, and owners to a CSV file
def write_to_csv(folders, output_file=OUTPUT_CSV):
    with open(output_file, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Folder Name', 'Folder ID', 'Owner'])  # Header
        for folder in folders:
            owner_names = ', '.join([owner['emailAddress'] for owner in folder['owners']])
            writer.writerow([folder['name'], folder['id'], owner_names])

if __name__ == "__main__":
    service = authenticate_gdrive()
    folders = get_folders(service)
    write_to_csv(folders)
    print(f"Folder names, IDs, and owners have been written to {OUTPUT_CSV}.") 