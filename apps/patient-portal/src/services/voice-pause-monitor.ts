/** Local energy detection only; samples never leave the browser or get stored. */
export function watchSpeechPause(stream: MediaStream, onPause: () => void): () => void {
    if (typeof window.AudioContext === "undefined") return () => {};
    let context: AudioContext;
    try { context = new window.AudioContext(); } catch { return () => {}; }
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const started = performance.now();
    let lastSpeech = started;
    let heardSpeech = false;
    let stopped = false;
    function cleanup() {
        if (stopped) return;
        stopped = true;
        clearInterval(timer);
        source.disconnect();
        analyser.disconnect();
        void context.close().catch(() => {});
    }
    const timer = setInterval(() => {
        analyser.getFloatTimeDomainData(samples);
        const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
        const now = performance.now();
        if (rms >= 0.02) { heardSpeech = true; lastSpeech = now; }
        // A pause ends an answer, never consent. Silence and long recordings are bounded.
        if ((heardSpeech && now - lastSpeech >= 1800) || (!heardSpeech && now - started >= 15000) || now - started >= 60000) {
            cleanup(); onPause();
        }
    }, 100);
    void context.resume().catch(cleanup);
    return cleanup;
}
