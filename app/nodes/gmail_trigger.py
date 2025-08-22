import base64
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

from app.nodes.base import BaseNode

class GmailTriggerNode(BaseNode):
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.modify'
    ]
    
    def __init__(
        self,
        node_id: str,
        name: str,
        email_address: str,
        credentials_file_path: str,
        token_file_path: Optional[str] = None,
        filter_sender: Optional[str] = None,
        filter_subject_contains: Optional[str] = None,
        only_unread: bool = True,
        mark_as_read: bool = False,
        polling_interval: int = 30,
        max_results: int = 10
    ):
        super().__init__(id=node_id, name=name, type="trigger")

        self.email_address = email_address
        self.credentials_file_path = credentials_file_path
        self.token_file_path = token_file_path or "gmail_token.json"

        self.filter_sender = filter_sender
        self.filter_subject_contains = filter_subject_contains
        self.only_unread = only_unread
        self.mark_as_read = mark_as_read

        self.polling_interval = polling_interval
        self.max_results = max_results

        self.credentials = None
        self.gmail_service = None
        

        self.last_checked = None
        

        self.logger = logging.getLogger(f"GmailTriggerNode_{self.id}")
    
    async def start(self) -> bool:

        try:
            self.logger.info(f"Starting Gmail trigger node '{self.name}'")
            
            # Authenticate with Gmail
            success = await self.authenticate()
            if not success:
                self.logger.error("Gmail authentication failed")
                return False
            
            self.isActive = True
            self.logger.info(f"Gmail trigger node '{self.name}' started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Gmail node: {str(e)}")
            self.isActive = False
            return False
    
    async def stop(self) -> None:

        self.isActive = False
        await self.disconnect()
        self.logger.info(f"Gmail trigger node '{self.name}' stopped")
    
    async def execute_once(self) -> List[Dict[str, Any]]:

        if not self.isActive:
            self.logger.warning(f"Attempted to execute inactive node '{self.name}'")
            return []
        
        try:
            self.logger.debug(f"Checking for new emails in '{self.email_address}'")
            
            # Fetch new emails from Gmail
            raw_emails = await self.fetch_new_emails()
            
            if not raw_emails:
                self.logger.debug("No new emails found")
                return []
            
            # Parse emails into standardized format
            parsed_emails = []
            for raw_email in raw_emails:
                try:
                    parsed_email = await self.parse_email(raw_email)
                    
                    # Apply filters
                    if self._should_process_email(parsed_email):
                        parsed_emails.append(parsed_email)
                        self.logger.info(f"Email accepted: '{parsed_email['subject']}' from {parsed_email['from']}")
                        
                        # Mark as read if configured
                        if self.mark_as_read:
                            await self.mark_email_as_read(raw_email)
                    else:
                        self.logger.debug(f"Email filtered out: '{parsed_email['subject']}' from {parsed_email['from']}")
                        
                except Exception as e:
                    self.logger.error(f"Failed to parse email: {str(e)}")
                    continue
            
            self.logger.info(f"Found {len(parsed_emails)} new emails after filtering")
            return parsed_emails
            
        except Exception as e:
            self.logger.error(f"Failed to execute email check: {str(e)}")
            return []
    
    async def authenticate(self) -> bool:

        try:
            self.logger.info("Starting Gmail authentication...")
            
            # Try to load existing credentials
            if self.token_file_path:
                try:
                    self.credentials = Credentials.from_authorized_user_file(
                        self.token_file_path, self.SCOPES
                    )
                    self.logger.info("Loaded existing Gmail credentials")
                except Exception:
                    self.logger.info("No existing credentials found")
            
            # If no valid credentials, go through OAuth flow
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    # Try to refresh expired credentials
                    self.logger.info("Refreshing expired Gmail credentials")
                    self.credentials.refresh(Request())
                else:
                    # Run OAuth flow
                    self.logger.info("Starting OAuth flow for Gmail")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file_path, self.SCOPES
                    )
                    self.credentials = flow.run_local_server(port=0)
                
                # Save credentials for next time
                if self.token_file_path:
                    with open(self.token_file_path, 'w') as token:
                        token.write(self.credentials.to_json())
                    self.logger.info("Saved Gmail credentials to file")
            
            # Build Gmail service
            self.gmail_service = build('gmail', 'v1', credentials=self.credentials)
            
            # Test the connection
            profile = self.gmail_service.users().getProfile(userId='me').execute()
            self.logger.info(f"Gmail authentication successful for: {profile['emailAddress']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Gmail authentication failed: {str(e)}")
            return False
    
    async def disconnect(self) -> None:

        self.gmail_service = None
        self.credentials = None
        self.logger.info("Gmail connection cleaned up")
    
    async def fetch_new_emails(self) -> List[Any]:

        if not self.gmail_service:
            self.logger.error("Gmail service not initialized")
            return []
        
        try:
            # Build query string
            query_parts = []
            
            # Only unread emails
            if self.only_unread:
                query_parts.append("is:unread")
            
            # Filter by sender
            if self.filter_sender:
                query_parts.append(f"from:{self.filter_sender}")
            
            # Filter by subject content
            if self.filter_subject_contains:
                query_parts.append(f'subject:"{self.filter_subject_contains}"')
            
            # Only emails after last check (if we've checked before)
            if self.last_checked:
                epoch_time = int(self.last_checked.timestamp())
                query_parts.append(f"after:{epoch_time}")
            
            query = " ".join(query_parts)
            self.logger.debug(f"Gmail query: {query}")
            
            # Search for messages
            results = self.gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=self.max_results,
                labelIds=['INBOX']
            ).execute()
            
            messages = results.get('messages', [])
            
            if messages:
                self.logger.info(f"Found {len(messages)} messages matching criteria")
                
                # Fetch full message details
                full_messages = []
                for message in messages:
                    full_message = self.gmail_service.users().messages().get(
                        userId='me',
                        id=message['id'],
                        format='full'
                    ).execute()
                    full_messages.append(full_message)
                
                # Update last checked time
                self.last_checked = datetime.utcnow()
                return full_messages
            else:
                self.logger.debug("No new messages found")
                self.last_checked = datetime.utcnow()
                return []
                
        except HttpError as e:
            self.logger.error(f"Gmail API error: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"Failed to fetch Gmail messages: {str(e)}")
            return []
    
    async def parse_email(self, raw_email: Any) -> Dict[str, Any]:

        try:

            headers = {}
            for header in raw_email['payload'].get('headers', []):
                headers[header['name'].lower()] = header['value']
            

            body = self._extract_body_from_payload(raw_email['payload'])
            

            label_ids = raw_email.get('labelIds', [])
            is_read = 'UNREAD' not in label_ids
            

            internal_date = int(raw_email['internalDate'])
            received_at = datetime.fromtimestamp(internal_date / 1000).isoformat() + 'Z'
            
            parsed_email = {
                "id": raw_email['id'],
                "thread_id": raw_email['threadId'],
                "from": headers.get('from', ''),
                "to": headers.get('to', ''),
                "cc": headers.get('cc', ''),
                "bcc": headers.get('bcc', ''),
                "subject": headers.get('subject', ''),
                "body": body,
                "received_at": received_at,
                "is_read": is_read,
                "labels": label_ids,
                "snippet": raw_email.get('snippet', ''),
                "size_estimate": raw_email.get('sizeEstimate', 0)
            }
            
            return parsed_email
            
        except Exception as e:
            self.logger.error(f"Failed to parse Gmail message: {str(e)}")

            return {
                "id": raw_email.get('id', 'unknown'),
                "thread_id": raw_email.get('threadId', 'unknown'),
                "from": "unknown",
                "to": "unknown",
                "subject": "Failed to parse",
                "body": "Error parsing email content",
                "received_at": datetime.utcnow().isoformat() + 'Z',
                "is_read": False,
                "labels": [],
                "snippet": "",
                "size_estimate": 0
            }
    
    def _extract_body_from_payload(self, payload: Dict[str, Any]) -> str:

        body = ""
        
        try:

            if 'body' in payload and 'data' in payload['body']:
                body_data = payload['body']['data']
                body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                return body
            

            if 'parts' in payload:
                for part in payload['parts']:

                    mime_type = part.get('mimeType', '')
                    
                    if mime_type == 'text/plain' and 'data' in part.get('body', {}):
                        body_data = part['body']['data']
                        body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                        break
                    elif mime_type == 'text/html' and 'data' in part.get('body', {}):

                        if not body:
                            body_data = part['body']['data']
                            body = base64.urlsafe_b64decode(body_data).decode('utf-8')
            
        except Exception as e:
            self.logger.warning(f"Failed to extract body: {str(e)}")
            body = "Could not extract email body"
        
        return body
    
    def _should_process_email(self, parsed_email: Dict[str, Any]) -> bool:


        from_email = parsed_email["from"]
        if "<" in from_email and ">" in from_email:
            from_email = from_email.split("<")[1].split(">")[0].strip()
        
        self.logger.debug(f"Checking email from '{from_email}' with subject '{parsed_email['subject']}'")
        

        if self.filter_sender and from_email != self.filter_sender:
            self.logger.debug(f"Email filtered out - sender '{from_email}' doesn't match filter '{self.filter_sender}'")
            return False
        

        if (self.filter_subject_contains and 
            self.filter_subject_contains.lower() not in parsed_email["subject"].lower()):
            self.logger.debug(f"Email filtered out - subject '{parsed_email['subject']}' doesn't contain '{self.filter_subject_contains}'")
            return False
        
        self.logger.debug("Email passed all filters!")
        return True
    
    async def mark_email_as_read(self, raw_email: Any) -> bool:

        try:
            message_id = raw_email['id']
            

            self.gmail_service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            self.logger.debug(f"Marked email {message_id} as read")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to mark email as read: {str(e)}")
            return False
    

    async def execute(self) -> Any:

        emails = await self.execute_once()
        if emails:

            self.setOutput({
                "trigger": "new_email",
                "timestamp": datetime.utcnow().isoformat(),
                "emails_count": len(emails),
                "emails": emails
            })
        return self.getOutput()