#!/usr/bin/env python3
"""
Upload Excel files from Fleet_Dashboard_Files/ to Google Drive
"""

import os
import glob
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_drive():
    # Load credentials from the JSON file
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    SERVICE_ACCOUNT_FILE = 'credentials.json'
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        
        # Build the Drive service
        service = build('drive', 'v3', credentials=credentials)
        
        # Find all Excel files in Fleet_Dashboard_Files folder
        excel_files = glob.glob('Fleet_Dashboard_Files/*.xlsx') + glob.glob('Fleet_Dashboard_Files/*.xls')
        
        if not excel_files:
            print("❌ No Excel files found to upload")
            return
        
        # Upload each file
        for file_path in excel_files:
            file_name = os.path.basename(file_path)
            
            # File metadata
            file_metadata = {
                'name': file_name,  # Keep original filename
                'parents': [os.environ.get('GOOGLE_DRIVE_FOLDER_ID')]
            }
            
            # Upload file
            print(f"📤 Uploading {file_name} to Google Drive...")
            media = MediaFileUpload(file_path, resumable=True)
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            print(f"✅ Successfully uploaded {file_name} to Google Drive. File ID: {file.get('id')}")
    
    except Exception as e:
        print(f"❌ Error uploading to Google Drive: {str(e)}")
        raise

if __name__ == '__main__':
    upload_to_drive()