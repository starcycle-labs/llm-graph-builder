from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import logging
import os
from pathlib import Path
from src.shared.llm_graph_builder_exception import LLMGraphBuilderException
from dotenv import load_dotenv
import io

# Load environment variables
load_dotenv()

# Set up base directory and paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MERGED_DIR = BASE_DIR / "merged_files"
CREDENTIALS_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_FILE')

if CREDENTIALS_FILE:
    key_file = BASE_DIR / "src" / "gdrive_sync" / CREDENTIALS_FILE
    if key_file.exists():
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(key_file)

def _authenticate_gdrive():
    """Authenticate with Google Drive API"""
    try:
        if not CREDENTIALS_FILE:
            raise LLMGraphBuilderException("Google Drive credentials file not specified")
        
        key_file = BASE_DIR / "src" / "gdrive_sync" / CREDENTIALS_FILE
        if not key_file.exists():
            raise LLMGraphBuilderException(f"Credentials file not found at {key_file}")
        
        credentials = service_account.Credentials.from_service_account_file(
            str(key_file),
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        logging.error(f"Error authenticating with Google Drive: {str(e)}")
        raise LLMGraphBuilderException(f"Failed to authenticate with Google Drive: {str(e)}")

def get_folder_files_info(folder_id):
    """Get metadata for all files in a Google Drive folder"""
    try:
        service = _authenticate_gdrive()
        
        # Get folder name and remove 'Customers | ' prefix
        folder_metadata = service.files().get(
            fileId=folder_id,
            fields='id, name'
        ).execute()
        folder_name = folder_metadata.get('name', '')
        if folder_name.startswith('Customers | '):
            folder_name = folder_name[len('Customers | '):]
        
        # Get list of files in the folder
        results = service.files().list(
            q=f"'{folder_id}' in parents",
            fields="files(id, name, mimeType, size)"
        ).execute()
        
        files = results.get('files', [])
        
        # Format file metadata
        lst_file_metadata = []
        for file in files:
            logging.info(f"Found file: {file['name']} with MIME type: {file['mimeType']}")
            lst_file_metadata.append({
                'fileName': file['name'],
                'fileSize': int(file.get('size', 0)),
                'fileId': file['id'],
                'mimeType': file['mimeType'],
                'folderName': folder_name  # Add folder name to each file's metadata
            })
        
        return lst_file_metadata
    except Exception as e:
        logging.error(f"Error listing files in Google Drive folder: {str(e)}")
        raise LLMGraphBuilderException(f"Failed to list Google Drive files: {str(e)}")

def _download_file(file_id, file_name=None):
    """Download a file from Google Drive and save it locally"""
    try:
        service = _authenticate_gdrive()
        
        # Log the full path we're using
        logging.info(f"MERGED_DIR path: {MERGED_DIR}")
        logging.info(f"Full path being used: {os.path.abspath(MERGED_DIR)}")
        
        # Get file metadata if file_name not provided
        if not file_name:
            file_metadata = service.files().get(fileId=file_id, fields='id, name, mimeType').execute()
            file_name = file_metadata['name']
            mime_type = file_metadata['mimeType']
        else:
            # Get mime type if we have the file name
            file_metadata = service.files().get(fileId=file_id, fields='id, mimeType').execute()
            mime_type = file_metadata['mimeType']
        
        logging.info(f"File {file_name} has MIME type: {mime_type}")
        
        # Create merged_files directory if it doesn't exist
        os.makedirs(MERGED_DIR, exist_ok=True)
        
        # Handle Google Workspace files
        if mime_type in ['application/vnd.google-apps.document', 
                        'application/vnd.google-apps.spreadsheet']:
            
            # Map Google Workspace types to export MIME types
            export_mime_types = {
                'application/vnd.google-apps.document': 'application/pdf',
                'application/vnd.google-apps.spreadsheet': 'text/csv',
            }
            
            # Map to file extensions
            extensions = {
                'application/vnd.google-apps.document': '.pdf',
                'application/vnd.google-apps.spreadsheet': '.csv',
            }
            
            # Get the appropriate export MIME type
            export_mime_type = export_mime_types.get(mime_type)
            if not export_mime_type:
                raise LLMGraphBuilderException(f"Unsupported Google Workspace file type: {mime_type}")
            
            # Export the file
            request = service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            file_extension = extensions.get(mime_type)
            
        else:
            # Handle regular files
            request = service.files().get_media(fileId=file_id)
            file_extension = ''
        
        # Download the file
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logging.info(f"Download progress: {int(status.progress() * 100)}%")
        
        # Sanitize filename for Windows compatibility
        sanitized_name = file_name.replace('|', '-').replace(':', '-').replace('/', '-').replace('\\', '-')
        if file_extension and not sanitized_name.endswith(file_extension):
            sanitized_name += file_extension
            
        local_path = MERGED_DIR / sanitized_name
        
        # Save the file locally
        fh.seek(0)
        with open(local_path, 'wb') as f:
            f.write(fh.read())
            f.flush()
            os.fsync(f.fileno())
        
        return str(local_path), sanitized_name
    except Exception as e:
        logging.error(f"Error downloading file from Google Drive: {str(e)}")
        raise LLMGraphBuilderException(f"Failed to download file: {str(e)}")                