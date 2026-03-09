export const getSharedAudioContext = () => {
  if (typeof window === "undefined") return null;
  // @ts-ignore
  if (!window.__sharedAudioContext) {
    // @ts-ignore
    const ctx = new window.AudioContext();
    
    // Auto-resume on user interactions to prevent suspension block
    const resumeCtx = () => {
        if (ctx.state === 'suspended') {
            ctx.resume().catch(console.error);
        }
    };
    window.addEventListener('click', resumeCtx, { once: true });
    window.addEventListener('touchstart', resumeCtx, { once: true });
    window.addEventListener('keydown', resumeCtx, { once: true });
    
    // @ts-ignore
    window.__sharedAudioContext = ctx;
  }
  // @ts-ignore
  return window.__sharedAudioContext as AudioContext;
};
