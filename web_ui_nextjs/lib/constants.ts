// Shared types and constants for the voice agent

export type InteractionMode = "voice" | "text";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  timestamp: Date;
  audioChunks?: Uint8Array[];
}

export interface VoiceOption {
  id: string;
  name: string;
  style: string;
  value: string;
}

export const VOICE_OPTIONS: VoiceOption[] = [
  {
    id: "voiceCardSarah",
    name: "Sarah",
    style: "Natural",
    value: "en-US-JennyNeural",
  },
  {
    id: "voiceCardDavid",
    name: "David",
    style: "Formal",
    value: "en-US-DavisNeural",
  },
];

export const TARGET_SAMPLE_RATE = 16000;
export const KEEPALIVE_INTERVAL_MS = 15000;
export const BYTES_PER_SECOND = TARGET_SAMPLE_RATE * 2;
export const STREAM_RENDER_INTERVAL_MS = 50;

export const QUICK_ACTIONS = [
  { label: "Check eligibility", action: "Check eligibility" },
  { label: "Documents list", action: "Documents list" },
];

// Helpers
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function decodeBase64ToUint8(base64: string): Uint8Array {
  const decoded = atob(base64);
  const bytes = new Uint8Array(decoded.length);
  for (let i = 0; i < decoded.length; i++) {
    bytes[i] = decoded.charCodeAt(i);
  }
  return bytes;
}
