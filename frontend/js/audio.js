// Web Audio API Synthesizer for instant momentum alerts without external files
class SoundAlertService {
  constructor() {
    this.ctx = null;
    this.enabled = true;
    this._initContext();
  }

  _initContext() {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    } catch (e) {
      console.warn("Web Audio API not supported:", e);
    }
  }

  _resumeContext() {
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  playAlert(severity = "HIGH") {
    if (!this.enabled) return;
    if (!this.ctx) this._initContext();
    if (!this.ctx) return;

    this._resumeContext();

    const now = this.ctx.currentTime;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    osc.connect(gain);
    gain.connect(this.ctx.destination);

    if (severity === "HIGH") {
      // High urgency double-beep / ascending chime (880Hz -> 1320Hz)
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.12);
      osc.frequency.setValueAtTime(880, now + 0.16);
      osc.frequency.exponentialRampToValueAtTime(1400, now + 0.32);

      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.45);

      osc.start(now);
      osc.stop(now + 0.45);
    } else {
      // Normal momentum pulse chime (587Hz -> 880Hz)
      osc.type = "triangle";
      osc.frequency.setValueAtTime(587.33, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.2);

      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);

      osc.start(now);
      osc.stop(now + 0.3);
    }
  }

  toggle() {
    this.enabled = !this.enabled;
    if (this.enabled) {
      this.playAlert("NORMAL");
    }
    return this.enabled;
  }
}

window.soundAlerts = new SoundAlertService();
