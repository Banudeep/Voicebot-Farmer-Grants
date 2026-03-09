"""
Azure Blob Storage Logger
Uploads chat transcripts and audio recordings to Azure Blob Storage.
"""
import json
import io
import traceback
import wave
from datetime import datetime
from typing import Optional

import config

# Azure Blob Storage SDK
try:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    HAS_BLOB_STORAGE = True
except ImportError:
    HAS_BLOB_STORAGE = False
    BlobServiceClient = None


class BlobStorageLogger:
    """Handles uploading transcripts and recordings to Azure Blob Storage"""
    
    def __init__(self):
        self.enabled = config.ENABLE_BLOB_LOGGING
        self.client: Optional[BlobServiceClient] = None
        self._initialized = False
        
        if not self.enabled:
            print("[INFO] Blob logging disabled (set ENABLE_BLOB_LOGGING=true to enable)")
            return
        
        if not HAS_BLOB_STORAGE:
            print("[WARN] azure-storage-blob not installed. Run: pip install azure-storage-blob")
            self.enabled = False
            return
        
        if not config.AZURE_STORAGE_CONNECTION_STRING:
            print("[WARN] AZURE_STORAGE_CONNECTION_STRING not set - blob logging disabled")
            self.enabled = False
            return
        
        try:
            self.client = BlobServiceClient.from_connection_string(
                config.AZURE_STORAGE_CONNECTION_STRING
            )
            
            # Ensure containers exist
            try:
                self.client.create_container(config.AZURE_BLOB_CONTAINER_TRANSCRIPTS)
                print(f"  Created container: {config.AZURE_BLOB_CONTAINER_TRANSCRIPTS}")
            except Exception:
                pass  # Container likely exists
                
            try:
                self.client.create_container(config.AZURE_BLOB_CONTAINER_RECORDINGS)
                print(f"  Created container: {config.AZURE_BLOB_CONTAINER_RECORDINGS}")
            except Exception:
                pass  # Container likely exists

            self._initialized = True
            print(f"Blob Storage connected")
            print(f"  Transcripts → {config.AZURE_BLOB_CONTAINER_TRANSCRIPTS}")
            print(f"  Recordings  → {config.AZURE_BLOB_CONTAINER_RECORDINGS}")
        except Exception as e:
            print(f"[WARN] Failed to connect to Blob Storage: {e}")
            self.enabled = False
    
    def _get_blob_path(self, session_id: str, extension: str) -> str:
        """Generate blob path: {date}/{session_id}.{ext}"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return f"{date_str}/{session_id}.{extension}"
    
    async def upload_transcript(
        self, 
        session_id: str, 
        messages: list,
        started_at: datetime,
        ended_at: datetime
    ) -> bool:
        """
        Upload chat transcript as JSON to blob storage.
        
        Args:
            session_id: Unique session identifier
            messages: List of message dicts [{timestamp, role, text}, ...]
            started_at: Session start time
            ended_at: Session end time
            
        Returns:
            True if upload succeeded, False otherwise
        """
        if not self.enabled or not self._initialized:
            return False
        
        if not messages:
            if config.DEBUG:
                print("[INFO] No messages to upload - skipping transcript")
            return False
        
        try:
            # Build transcript JSON
            transcript_data = {
                "session_id": session_id,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "message_count": len(messages),
                "messages": messages
            }
            
            json_bytes = json.dumps(transcript_data, indent=2).encode('utf-8')
            blob_path = self._get_blob_path(session_id, "json")
            
            # Upload to blob storage
            container_client = self.client.get_container_client(
                config.AZURE_BLOB_CONTAINER_TRANSCRIPTS
            )
            blob_client = container_client.get_blob_client(blob_path)
            
            blob_client.upload_blob(
                json_bytes,
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json")
            )
            
            print(f"Transcript uploaded: {blob_path} ({len(messages)} messages)")
            return True
            
        except Exception as e:
            print(f"[WARN] Failed to upload transcript: {e}")
            if config.DEBUG:
                traceback.print_exc()
            return False
    
    async def upload_recording(
        self,
        session_id: str,
        audio_chunks: list,
        sample_rate: int = None
    ) -> bool:
        """
        Upload audio recording as WAV to blob storage.
        
        Args:
            session_id: Unique session identifier
            audio_chunks: List of raw audio bytes chunks
            sample_rate: Audio sample rate (defaults to config.STT_SAMPLE_RATE)
            
        Returns:
            True if upload succeeded, False otherwise
        """
        if not self.enabled or not self._initialized:
            return False
        
        if not audio_chunks:
            if config.DEBUG:
                print("[INFO] No audio to upload - skipping recording")
            return False
        
        try:
            # Combine audio chunks
            audio_data = b''.join(audio_chunks)
            
            if len(audio_data) == 0:
                return False
            
            # Create WAV file in memory
            wav_buffer = io.BytesIO()
            sample_rate = sample_rate or config.STT_SAMPLE_RATE
            
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes per sample
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data)
            
            wav_bytes = wav_buffer.getvalue()
            blob_path = self._get_blob_path(session_id, "wav")
            
            # Upload to blob storage
            container_client = self.client.get_container_client(
                config.AZURE_BLOB_CONTAINER_RECORDINGS
            )
            blob_client = container_client.get_blob_client(blob_path)
            
            blob_client.upload_blob(
                wav_bytes,
                overwrite=True,
                content_settings=ContentSettings(content_type="audio/wav")
            )
            
            # Calculate duration for logging
            duration = len(audio_data) / (sample_rate * 2)
            print(f"Recording uploaded: {blob_path} ({duration:.1f}s, {len(wav_bytes)} bytes)")
            return True
            
        except Exception as e:
            print(f"[WARN] Failed to upload recording: {e}")
            if config.DEBUG:
                traceback.print_exc()
            return False


# Singleton instance
_blob_logger: Optional[BlobStorageLogger] = None


def get_blob_logger() -> BlobStorageLogger:
    """Get or create the singleton BlobStorageLogger instance"""
    global _blob_logger
    if _blob_logger is None:
        _blob_logger = BlobStorageLogger()
    return _blob_logger
