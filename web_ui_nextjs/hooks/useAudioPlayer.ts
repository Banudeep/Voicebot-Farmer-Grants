import { useRef, useCallback } from "react";

export function useAudioPlayer(
  send: (data: any) => void,
  playbackSpeedRef: React.MutableRefObject<number>
) {
  const audioContextRef = useRef<AudioContext | null>(null);
  const nextStartTimeRef = useRef<number>(0);
  const sourceNodesRef = useRef<AudioBufferSourceNode[]>([]);

  const initAudioContext = useCallback(async () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new window.AudioContext({ sampleRate: 16000 });
    }
    if (audioContextRef.current.state === "suspended") {
      await audioContextRef.current.resume();
    }
    return audioContextRef.current;
  }, []);

  const playChunk = useCallback(async (chunk: Uint8Array, audioCtx: AudioContext) => {
    const int16Array = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.byteLength / 2);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }
    
    const audioBuffer = audioCtx.createBuffer(1, float32Array.length, 16000);
    audioBuffer.copyToChannel(float32Array, 0);

    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.playbackRate.value = playbackSpeedRef.current;
    source.connect(audioCtx.destination);
    
    const startTime = Math.max(audioCtx.currentTime, nextStartTimeRef.current);
    source.start(startTime);
    sourceNodesRef.current.push(source);
    
    nextStartTimeRef.current = startTime + (audioBuffer.duration / playbackSpeedRef.current);
  }, [playbackSpeedRef]);

  const enqueueChunk = useCallback(async (chunk: Uint8Array) => {
    const audioCtx = await initAudioContext();
    await playChunk(chunk, audioCtx);
  }, [initAudioContext, playChunk]);

  const playChunks = useCallback(async (chunks: Uint8Array[]) => {
    const audioCtx = await initAudioContext();
    nextStartTimeRef.current = audioCtx.currentTime;
    for (const chunk of chunks) {
      await playChunk(chunk, audioCtx);
    }
  }, [initAudioContext, playChunk]);

  const stopPlayback = useCallback(() => {
    sourceNodesRef.current.forEach(source => {
      try { source.stop(); } catch(e) {}
    });
    sourceNodesRef.current = [];
    nextStartTimeRef.current = 0;
  }, []);

  return { enqueueChunk, stopPlayback, playChunks };
}
