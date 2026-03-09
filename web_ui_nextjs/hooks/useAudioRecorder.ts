import { useState, useRef, useCallback } from "react";
import { arrayBufferToBase64 } from "@/lib/constants";
import { getSharedAudioContext } from "./sharedAudio";

export function useAudioRecorder(
  send: (data: any) => void,
  sessionStartedRef: React.MutableRefObject<boolean>,
) {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const smoothedLevelRef = useRef(0);

  const startRecording = useCallback(async () => {
    if (typeof window === "undefined" || !navigator.mediaDevices) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;

      const audioCtx = getSharedAudioContext()!;
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
            type: "input_audio_buffer.append",
            audio: arrayBufferToBase64(audioBuffer),
          });

          // Smooth the RMS value for a natural visual animation
          const rms = event.data.rms ?? 0;
          // Normalize RMS: typical speech is 0.01–0.15, clamp to 0–1
          const normalized = Math.min(1, rms / 0.12);
          const smoothing = 0.3;
          smoothedLevelRef.current =
            smoothedLevelRef.current * smoothing + normalized * (1 - smoothing);
          setAudioLevel(smoothedLevelRef.current);
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
      // Intentionally NOT closing the shared context so the player can still use it
      audioContextRef.current = null;
    }
    setIsRecording(false);
    setAudioLevel(0);
    smoothedLevelRef.current = 0;
  }, []);

  return { isRecording, audioLevel, startRecording, stopRecording };
}
