import os
from pathlib import Path
import requests
import json
from dotenv import load_dotenv
from src.gdrive_sync.gdrive_to_database import get_folder_files_info, _download_file, MERGED_DIR
from src.gdrive_sync.gdrive_folder_list import authenticate_gdrive
import time
import urllib.parse
import base64
from datetime import datetime
import re
from googleapiclient.http import MediaIoBaseDownload
from io import BytesIO
import logging
import csv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

load_dotenv()

# Add API base URL configuration
API_BASE_URL = os.getenv('API_BASE_URL')
CHUNK_SIZE = 5242880  # 5MB chunks to match UI configuration
DEFAULT_DATABASE = 'neo4j'  # Default database for system operations

# Get chunking parameters from environment
GRAPH_CHUNK_SIZE = int(os.getenv('GRAPH_CHUNK_SIZE', 200))
GRAPH_CHUNK_OVERLAP = int(os.getenv('GRAPH_CHUNK_OVERLAP', 20))
GRAPH_CHUNK_LIMIT = int(os.getenv('GRAPH_CHUNK_LIMIT', 50))

def sanitize_database_name(folder_name):
    """Convert folder name to a valid Neo4j database name"""
    logging.info(f"Original folder name: {folder_name}")
    
    # Remove the "Customers | " prefix if it exists
    if folder_name.startswith("Customers | "):
        folder_name = folder_name[11:]  # Remove "Customers | "
        logging.info(f"After removing 'Customers | ' prefix: {folder_name}")
    
    # Convert to lowercase
    sanitized = folder_name.lower()
    # Keep only alphanumeric characters
    sanitized = ''.join(c for c in sanitized if c.isalnum())
    logging.info(f"After converting to camelCase: {sanitized}")
    
    # If the name starts with a number, prefix with 'company'
    if sanitized[0].isdigit():
        sanitized = 'company' + sanitized
        logging.info(f"After handling numeric prefix: {sanitized}")
        
    # Limit length to 63 characters (Neo4j limit)
    final_name = sanitized[:63]
    logging.info(f"Final database name: {final_name}")
    return final_name

def check_available_databases():
    """Check available databases using the default neo4j database"""
    try:
        logging.info(f"Checking available databases using system database: {DEFAULT_DATABASE}")
        
        form_data = {
            'uri': os.getenv('NEO4J_URI'),
            'userName': os.getenv('NEO4J_USERNAME'),
            'password': os.getenv('NEO4J_PASSWORD'),
            'database': 'neo4j',  # Explicitly use system database
            'email': ''
        }
        
        logging.info(f"Making request to {API_BASE_URL}/list_databases")
        response = requests.post(f'{API_BASE_URL}/list_databases', data=form_data)
        logging.info(f"Response status: {response}")
        response.raise_for_status()
        
        # Get raw database names and sanitize them
        raw_databases = response.json().get('data', {}).get('databases', [])
        databases = [sanitize_database_name(db) for db in raw_databases]
        logging.info(f"Available databases after sanitization: {databases}")
        return databases
    except Exception as e:
        logging.error(f"Error checking available databases: {str(e)}")
        raise

def create_database(database_name):
    """Create the specified database"""
    try:
        logging.info(f"Creating database {database_name}...")

        # Create the database
        form_data = {
            'uri': os.getenv('NEO4J_URI'),
            'userName': os.getenv('NEO4J_USERNAME'),
            'password': os.getenv('NEO4J_PASSWORD'),
            'database': database_name,  # Pass the target database name
            'email': ''
        }
        
        logging.info(f"Calling /create_database endpoint with database: {database_name}")
        response = requests.post(f'{API_BASE_URL}/create_database', data=form_data)
        response.raise_for_status()
        logging.info(f"Database {database_name} created successfully")
        
    except Exception as e:
        logging.error(f"Error creating database: {str(e)}")
        raise


def delete_database(database_name):
    """Delete the specified database"""
    try:
        logging.info(f"Deleting database {database_name}...")
        
        # First check if database exists
        databases = check_available_databases()
        if database_name not in databases:
            logging.info(f"Database {database_name} does not exist, skipping deletion")
            return
        
        # Delete the database
        form_data = {
            'uri': os.getenv('NEO4J_URI'),
            'userName': os.getenv('NEO4J_USERNAME'),
            'password': os.getenv('NEO4J_PASSWORD'),
            'database': database_name,  # Pass the target database name
            'email': ''
        }
        
        logging.info(f"Calling /delete_database endpoint with database: {database_name}")
        
        # Delete database
        response = requests.post(f'{API_BASE_URL}/delete_database', data=form_data)
        logging.info(f"Delete database response status: {response.status_code}")
        
        response.raise_for_status()
        logging.info(f"Database {database_name} deleted successfully")
            
    except Exception as e:
        logging.error(f"Error managing database: {str(e)}")
        raise

def sanitize_filename(filename):
    """Convert filename to a valid Windows filename"""
    # Remove any path components
    filename = os.path.basename(filename)
    # Replace spaces and special characters with underscores
    sanitized = re.sub(r'[\\/*?:"<>|]', '_', filename)
    sanitized = sanitized.replace(' ', '_')
    # Remove any non-ASCII characters
    sanitized = ''.join(c for c in sanitized if ord(c) < 128)
    return sanitized

def upload_file_direct(file_id, file_name, database_name, service, model='diffbot'):
    """Upload a file directly from Google Drive to Neo4j"""
    try:
        logging.info(f"Starting direct upload for {file_name}")
        logging.info(f"Using database name: {database_name}")
        
        # Get file metadata
        file = service.files().get(fileId=file_id, fields='size,mimeType').execute()
        mime_type = file.get('mimeType', '')
        file_size = file.get('size', 0)
        
        logging.info(f"File metadata - Size: {file_size} bytes, MIME: {mime_type}")
        
        # Skip unsupported Google Workspace file types
        if mime_type in ['application/vnd.google-apps.form', 'application/vnd.google-apps.drawing', 'application/vnd.google-apps.script']:
            logging.warning(f"Skipping unsupported Google Workspace file type: {mime_type} for {file_name}")
            return

        # skip presentation files
        if mime_type in ['application/vnd.google-apps.presentation']:
            logging.warning(f"Skipping presentation file type: {mime_type} for {file_name}")
            return

        # Skip files with unknown or application/octet-stream type
        if mime_type == '' or mime_type == 'application/octet-stream':
            logging.warning(f"Skipping file with unknown type: {file_name}")
            return
            
        # Handle Google Docs and Sheets
        if mime_type == 'application/vnd.google-apps.document':
            logging.info("Converting Google Doc to PDF...")
            # Export as PDF
            request = service.files().export(fileId=file_id, mimeType='application/pdf')
            file_name = file_name.replace('.gdoc', '.pdf')
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            logging.info("Converting Google Sheet to CSV...")
            # Export as CSV
            request = service.files().export(fileId=file_id, mimeType='text/csv')
            file_name = file_name.replace('.sheet', '.csv')
        else:
            # Regular file download
            request = service.files().get_media(fileId=file_id)
        
        # Create a BytesIO object to store the file
        file_buffer = BytesIO()
        
        # Download the file
        logging.info("Starting file download...")
        downloader = MediaIoBaseDownload(file_buffer, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logging.info(f"Download progress: {int(status.progress() * 100)}%")
        
        # Get the file data
        file_data = file_buffer.getvalue()
        file_size = len(file_data)
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        logging.info(f"File size: {file_size} bytes")
        logging.info(f"Total chunks: {total_chunks}")
        
        # Base64 encode password like the frontend
        encoded_password = base64.b64encode(os.getenv('NEO4J_PASSWORD').encode('ascii')).decode('ascii')
        
        # Sanitize the filename for chunk storage
        safe_filename = sanitize_filename(file_name)
        logging.info(f"Using sanitized filename: {safe_filename}")
        
        for chunk_number in range(1, total_chunks + 1):
            start = (chunk_number - 1) * CHUNK_SIZE
            end = min(start + CHUNK_SIZE, file_size)
            
            logging.info(f"Processing chunk {chunk_number}/{total_chunks}")
            logging.info(f"Chunk size: {end - start} bytes")
            logging.info(f"Using database name: {database_name}")
            
            # Get the chunk from the file data
            chunk = file_data[start:end]
            
            # Prepare form data
            form_data = {
                'chunkNumber': str(chunk_number),
                'totalChunks': str(total_chunks),
                'originalname': safe_filename,  # Use sanitized filename
                'model': model,
                'uri': os.getenv('NEO4J_URI'),
                'userName': os.getenv('NEO4J_USERNAME'),
                'password': os.getenv('NEO4J_PASSWORD'),
                'database': database_name,
                'email': '',
                'file_source': 'google_drive',
                'file_size': str(file_size),
                'file_type': safe_filename.split('.')[-1].upper(),  # Use sanitized filename
                'processingTotalTime': '0',
                'nodesCount': '0',
                'relationshipsCount': '0',
                'uploadProgress': '0',
                'processingProgress': 'undefined',
                'retryOptionStatus': 'false',
                'retryOption': '',
                'chunkNodeCount': '0',
                'chunkRelCount': '0',
                'entityNodeCount': '0',
                'entityEntityRelCount': '0',
                'communityNodeCount': '0',
                'communityRelCount': '0',
                'createdAt': datetime.now().isoformat()
            }
            
            files = {
                'file': (safe_filename, chunk)  # Use sanitized filename
            }
            
            logging.info(f"Uploading chunk to /upload endpoint")
            logging.info(f"Database name in request: {database_name}")
            response = requests.post(f'{API_BASE_URL}/upload', data=form_data, files=files)
            response.raise_for_status()
            logging.info(f"Chunk upload response: {response.status_code}")
            
            time.sleep(1)
            
            logging.info(f"Checking document status")
            status_response = requests.get(f'{API_BASE_URL}/document_status/{safe_filename}?url={os.getenv("NEO4J_URI")}&userName={os.getenv("NEO4J_USERNAME")}&password={encoded_password}&database={database_name}')
            logging.info(f"Status check response: {status_response.status_code}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                logging.info(f"Status data: {status_data}")
                if status_data.get('Status') == 'Failed':
                    raise Exception(f"Document processing failed: {status_data.get('error', 'Unknown error')}")
            else:
                logging.error(f"Status check failed with status code: {status_response.status_code}")
                logging.error(f"Response content: {status_response.text}")
            
            progress = (chunk_number / total_chunks) * 100
            logging.info(f"Uploaded chunk {chunk_number}/{total_chunks} ({progress:.1f}%)")
            
        logging.info(f"Successfully uploaded {safe_filename} to database: {database_name}")
        
        # After successful upload, trigger extraction
        extract_form_data = {
            'uri': os.getenv('NEO4J_URI'),
            'userName': os.getenv('NEO4J_USERNAME'),
            'password': os.getenv('NEO4J_PASSWORD'),
            'database': database_name,
            'model': model,
            'file_name': safe_filename,
            'source_type': 'local file',
            'email': '',
            'token_chunk_size': GRAPH_CHUNK_SIZE,
            'chunk_overlap': GRAPH_CHUNK_OVERLAP,
            'chunks_to_combine': GRAPH_CHUNK_LIMIT
        }
        
        logging.info(f"Triggering extraction for {safe_filename}")
        extract_response = requests.post(f'{API_BASE_URL}/extract', data=extract_form_data)
        extract_response.raise_for_status()
        logging.info(f"Extraction triggered successfully: {extract_response.status_code}")

        # After successful extraction, trigger post-processing to create necessary indexes
        post_processing_form_data = {
            'uri': os.getenv('NEO4J_URI'),
            'userName': os.getenv('NEO4J_USERNAME'),
            'password': os.getenv('NEO4J_PASSWORD'),
            'database': database_name,
            'tasks': json.dumps(['enable_hybrid_search_and_fulltext_search_in_bloom']),
            'email': ''
        }
        
        logging.info("Triggering post-processing to create indexes")
        post_processing_response = requests.post(f'{API_BASE_URL}/post_processing', data=post_processing_form_data)
        post_processing_response.raise_for_status()
        logging.info("Post-processing completed successfully")
        
    except Exception as e:
        logging.error(f"Error uploading file {file_name} to database: {database_name}")
        logging.error(f"Error details: {str(e)}")
        raise

def process_gdrive_file_direct(file_id, file_name, database_name, service):
    """Process a single Google Drive file directly"""
    try:
        logging.info(f"Processing file: {file_name} (ID: {file_id})")
        
        # Skip .folder files
        if file_name.endswith('.folder'):
            logging.info(f"Skipping .folder file: {file_name}")
            return
            
        # Get file metadata to check if it's a folder
        file_metadata = service.files().get(fileId=file_id, fields='mimeType,name').execute()
        mime_type = file_metadata.get('mimeType', '')
        actual_name = file_metadata.get('name', '')
        
        logging.info(f"File details - Name: {actual_name}, MIME: {mime_type}")
        
        # Skip folders
        if mime_type == 'application/vnd.google-apps.folder':
            logging.info(f"Skipping folder: {actual_name}")
            return
            
        # Upload file directly from Google Drive
        upload_file_direct(file_id, file_name, database_name, service)
        
    except Exception as e:
        logging.error(f"Error processing file {file_name}: {str(e)}")
        raise

def process_folder_direct(folder_id, folder_name, service):
    """Process all files in a single folder directly"""
    try:
        logging.info(f"Starting to process folder: {folder_name}")
        
        # Create database name from folder name
        database_name = sanitize_database_name(folder_name)
        logging.info(f"Final database name to be used: {database_name}")
        
        # Check if database exists before trying operations
        logging.info("Checking if database exists...")
        databases = check_available_databases()
        database_exists = database_name in databases
        logging.info(f"Database exists check: {database_exists}")
        logging.info(f"Current databases: {databases}")
        
        if database_exists:
            try:
                logging.info(f"Database {database_name} exists, attempting to delete")
                delete_database(database_name)
                
                # Wait for deletion to complete
                time.sleep(2)
                
                # Verify deletion
                databases = check_available_databases()
                if database_name in databases:
                    raise Exception(f"Failed to delete database {database_name} - database still exists after deletion")
                logging.info(f"Successfully deleted database {database_name}")
            except Exception as e:
                logging.error(f"Failed to delete database {database_name}: {str(e)}")
                raise

        try:
            logging.info(f"Creating new database: {database_name}")
            create_database(database_name)
            
            # Wait for creation to complete
            time.sleep(2)
            
            # Verify creation
            databases = check_available_databases()
            if database_name not in databases:
                raise Exception(f"Database {database_name} was not created successfully")
            logging.info(f"Successfully created database {database_name}")
        except Exception as e:
            if "Database name or alias already exists" in str(e):
                logging.warning(f"Database {database_name} already exists, continuing with existing database")
            else:
                logging.error(f"Failed to create database {database_name}: {str(e)}")
                raise

        # Get list of files in folder
        files = get_folder_files_info(folder_id)
        logging.info(f"Found {len(files)} files in folder")
        
        # Process each file
        for file in files:
            try:
                logging.info(f"Processing file: {file['fileName']}")
                logging.info(f"Using database name: {database_name}")
                process_gdrive_file_direct(
                    file['fileId'],
                    file['fileName'],
                    database_name,
                    service
                )
            except Exception as e:
                logging.error(f"Failed to process {file['fileName']}: {str(e)}")
                # Don't re-raise here - continue with next file
                continue
                
        logging.info(f"=== Completed processing folder: {folder_name} ===")
                
    except Exception as e:
        logging.error(f"Error processing folder {folder_name}: {str(e)}")
        raise

def process_folders_direct(folder_ids):
    """Process multiple folders from a list of folder IDs directly"""
    try:
        # Authenticate with Google Drive
        service = authenticate_gdrive()
        
        for folder_id in folder_ids:
            try:
                # Get folder details
                folder = service.files().get(
                    fileId=folder_id,
                    fields='name'
                ).execute()
                
                folder_name = folder.get('name', f'folder_{folder_id}')
                process_folder_direct(folder_id, folder_name, service)
                
            except Exception as e:
                logging.error(f"Failed to process folder {folder_id}: {str(e)}")
                raise  # Re-raise to stop processing on any folder failure
                
    except Exception as e:
        logging.error(f"Error in main process: {str(e)}")
        raise

def get_folder_ids_from_csv(csv_path=f'.logs/folder_list_{datetime.now().strftime("%Y-%m-%d")}.csv'):
    """Read folder IDs from the CSV file"""
    try:
        with open(csv_path, 'r') as file:
            reader = csv.DictReader(file)
            folders = list(reader)
            
        folder_ids = [folder['Folder ID'] for folder in folders]
        logging.info(f"Found {len(folder_ids)} folders in CSV file")
        return folder_ids
        
    except Exception as e:
        logging.error(f"Error reading CSV file: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        # Get folder IDs from CSV
        folder_ids = get_folder_ids_from_csv('.logs/folder_list_2025-05-09.csv')

        
        process_folders_direct(folder_ids)
    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
        exit(1) 