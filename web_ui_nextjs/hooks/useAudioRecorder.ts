import { useState, useRef, useCallback } from "react";
import { arrayBufferToBase64 } from "@/lib/constants";

export function useAudioRecorder(
  send: (data: any) => void,
  sessionStartedRef: React.MutableRefObject<boolean>
) {
  const [isRecording, setIsRecording] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);

  const startRecording = useCallback(async () => {
    if (typeof window === "undefined" || !navigator.mediaDevices) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const audioCtx = new window.AudioContext({ sampleRate: 16000 });
      audioContextRef.current = audioCtx;

      await audioCtx.audioWorklet.addModule("/audio-processor.js");

      const source = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, "audio-processor");
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (event) => {
        if (!sessionStartedRef.current) return;
        
        if (event.data.type === "audioData") {
          const audioBuffer = event.data.audio;
          send({
            type: "audio_input",
            audio: arrayBufferToBase64(audioBuffer),
          });
        }
      };

      source.connect(workletNode);
      workletNode.connect(audioCtx.destination);
      
      setIsRecording(true);
      sessionStartedRef.current = true;
    } catch (err) {
      console.error("Failed to start recording:", err);
    }
  }, [send, sessionStartedRef]);

  const stopRecording = useCallback(() => {
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setIsRecording(false);
  }, []);

  return { isRecording, startRecording, stopRecording };
}
