import { useRef, useCallback, useEffect } from "react";
import { getSharedAudioContext } from "./sharedAudio";
import { TARGET_SAMPLE_RATE } from "@/lib/constants";

export function useAudioPlayer(
  playbackSpeedRef: React.MutableRefObject<number>,
  onPlaybackComplete?: () => void,
) {
  const audioQueueRef = useRef<Uint8Array[]>([]);
  const isPlayingRef = useRef(false);
  const nextStartTimeRef = useRef(0);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const isProcessingQueueRef = useRef(false);
  const onPlaybackCompleteRef = useRef(onPlaybackComplete);
  onPlaybackCompleteRef.current = onPlaybackComplete;

  const playAudioQueue = useCallback(async () => {
    // Guard against concurrent invocations (e.g. during AudioContext.resume())
    if (isProcessingQueueRef.current) return;
    if (audioQueueRef.current.length === 0) return;

    isProcessingQueueRef.current = true;

    try {
      const audioCtx = getSharedAudioContext();
      if (!audioCtx) return;

      if (audioCtx.state === "suspended") {
        try {
          console.log("🔈 Resuming suspended AudioContext");
          await audioCtx.resume();
        } catch (e) {
          console.error("Failed to resume AudioContext", e);
        }
      }

      // Identify if the clock has passed our next scheduled time
      if (
        !isPlayingRef.current ||
        nextStartTimeRef.current < audioCtx.currentTime
      ) {
        nextStartTimeRef.current = audioCtx.currentTime + 0.05; // 50ms protective buffer
        isPlayingRef.current = true;
      }

      while (audioQueueRef.current.length > 0) {
        const chunk = audioQueueRef.current.shift();
        if (!chunk || chunk.length < 2) continue;

        // Extract raw PCM16 and convert directly to Float32 [-1.0, 1.0] using DataView
        const view = new DataView(
          chunk.buffer,
          chunk.byteOffset,
          chunk.byteLength,
        );
        const sampleCount = Math.floor(chunk.byteLength / 2);
        const float32 = new Float32Array(sampleCount);
        for (let i = 0; i < sampleCount; i++) {
          const int16 = view.getInt16(i * 2, true); // little-endian
          float32[i] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7fff;
        }

        // Fast buffer application
        const audioBuffer = audioCtx.createBuffer(
          1,
          float32.length,
          TARGET_SAMPLE_RATE,
        );
        audioBuffer.getChannelData(0).set(float32);

        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        // Do not alter playbackRate because it destructively changes pitch in Web Audio API.
        // Speed adjustments are handled by Azure SSML prosody rate on the backend.
        source.playbackRate.value = 1.0;
        source.connect(audioCtx.destination);

        // Schedule chunk gaplessly
        source.start(nextStartTimeRef.current);
        activeSourcesRef.current.push(source);

        // Cleanup node once played naturally
        source.onended = () => {
          const index = activeSourcesRef.current.indexOf(source);
          if (index > -1) activeSourcesRef.current.splice(index, 1);
          if (
            activeSourcesRef.current.length === 0 &&
            audioQueueRef.current.length === 0
          ) {
            isPlayingRef.current = false;
            // Notify caller that all audio has finished playing
            onPlaybackCompleteRef.current?.();
          }
        };

        // Extend the gapless cursor by the exact timeline duration
        const duration = audioBuffer.duration;
        nextStartTimeRef.current += duration;
      }
    } finally {
      isProcessingQueueRef.current = false;
    }

    // If new chunks arrived while we were processing (e.g. during await resume()),
    // kick off another pass.
    if (audioQueueRef.current.length > 0) {
      playAudioQueue();
    }
  }, [playbackSpeedRef]);

  const enqueueChunk = useCallback(
    async (chunk: Uint8Array) => {
      audioQueueRef.current.push(chunk);
      playAudioQueue();
    },
    [playAudioQueue],
  );

  const playChunks = useCallback(
    async (chunks: Uint8Array[]) => {
      // Used when clicking 'Listen' on a past chat message
      activeSourcesRef.current.forEach((source) => {
        try {
          source.stop();
          source.disconnect();
        } catch (e) {}
      });
      activeSourcesRef.current = [];
      audioQueueRef.current = [];
      isPlayingRef.current = false;
      nextStartTimeRef.current = 0;

      chunks.forEach((chunk) => audioQueueRef.current.push(chunk));
      playAudioQueue();
    },
    [playAudioQueue],
  );

  const stopPlayback = useCallback(() => {
    activeSourcesRef.current.forEach((source) => {
      try {
        source.stop();
        source.disconnect();
      } catch (e) {}
    });
    activeSourcesRef.current = [];
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    nextStartTimeRef.current = 0;
  }, []);

  useEffect(() => {
    return () => {
      stopPlayback();
    };
  }, [stopPlayback]);

  return { enqueueChunk, stopPlayback, playChunks };
}
