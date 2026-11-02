import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as loadPen } from "@remotion/google-fonts/NanumPenScript";
import { loadFont as loadSans } from "@remotion/google-fonts/NotoSansKR";
import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  type CalculateMetadataFunction,
} from "remotion";
import { FPS } from "./Short";

const { fontFamily: sans } = loadSans("normal", { weights: ["700", "900"], subsets: ["korean", "latin"] });
const { fontFamily: pen } = loadPen("normal", { weights: ["400"], subsets: ["korean", "latin"] });
const { fontFamily: latin } = loadMontserrat("normal", { weights: ["600"], subsets: ["latin"] });

// A vertical clip cut from a widescreen sermon recording: a title bar on top,
// a 9:16 window that follows the speaker, and subtitles. Props come from
// tools/build_clip.py.
export type SermonClipProps = {
  video: string; // source.mp4: the sermon section, with its own audio
  srcW: number;
  srcH: number;
  // Source ranges to keep, played back to back. zoom 1 shows the full height.
  segments: { fromMs: number; toMs: number; zoom: number }[];
  // Where the window is centred (0-1 of the source width), sampled every 100 ms of source time.
  track: number[];
  title: [string, string]; // second line is the big gold one
  credit: string;
  bar: string; // title bar colour
  subtitles: { startMs: number; endMs: number; text: string; en?: string | null; hand?: boolean }[];
};

const W = 1080;
const H = 1920;
const BAR_H = 400;
const GOLD = "#f4c45a";
const AUDIO_FADE = 2; // frames, softens the click at each cut
const msToFrame = (ms: number) => Math.round((ms / 1000) * FPS);

export const calculateSermonMetadata: CalculateMetadataFunction<SermonClipProps> = ({ props }) => ({
  durationInFrames: Math.max(
    1,
    props.segments.reduce((n, s) => n + msToFrame(s.toMs) - msToFrame(s.fromMs), 0),
  ),
});

// *word* → gold
const Marked: React.FC<{ text: string }> = ({ text }) => (
  <>
    {text.split(/(\*[^*]+\*)/).map((part, k) =>
      part.startsWith("*") ? (
        <span key={k} style={{ color: GOLD }}>
          {part.slice(1, -1)}
        </span>
      ) : (
        <span key={k}>{part}</span>
      ),
    )}
  </>
);

const Footage: React.FC<{
  props: SermonClipProps;
  seg: SermonClipProps["segments"][number];
  frames: number;
  fadeIn: boolean;
  fadeOut: boolean;
}> = ({ props, seg, frames, fadeIn, fadeOut }) => {
  const frame = useCurrentFrame();
  const sourceMs = seg.fromMs + (frame / FPS) * 1000;
  const i = Math.min(props.track.length - 1, Math.max(0, sourceMs / 100));
  const lo = Math.floor(i);
  const hi = Math.min(props.track.length - 1, lo + 1);
  const cx = props.track[lo] + (props.track[hi] - props.track[lo]) * (i - lo);
  // Scale the source so its height fills the frame (times zoom), then slide it.
  const h = H * seg.zoom;
  const w = (h * props.srcW) / props.srcH;
  const left = Math.min(0, Math.max(W - w, W / 2 - cx * w));
  const top = Math.min(0, Math.max(H - h, H * 0.52 - 0.42 * h)); // zoomed: keep the upper body
  return (
    <div style={{ position: "absolute", left, top, width: w, height: h }}>
      <Video
        src={staticFile(props.video)}
        trimBefore={msToFrame(seg.fromMs)}
        trimAfter={msToFrame(seg.toMs)}
        volume={(f) =>
          interpolate(f, [0, AUDIO_FADE, frames - AUDIO_FADE, frames], [fadeIn ? 0 : 1, 1, 1, fadeOut ? 0 : 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        }
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
};

const TitleBar: React.FC<{ title: [string, string]; credit: string; bar: string }> = ({ title, credit, bar }) => (
  <div
    style={{
      position: "absolute",
      top: 0,
      left: 0,
      width: W,
      height: BAR_H,
      backgroundColor: bar,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "flex-end",
      paddingBottom: 44,
      fontFamily: sans,
      boxShadow: "0 8px 40px rgba(0,0,0,0.45)",
    }}
  >
    <div style={{ color: "#f6efe3", fontSize: 64, fontWeight: 700, letterSpacing: -1 }}>{title[0]}</div>
    <div style={{ width: 120, height: 3, backgroundColor: GOLD, opacity: 0.8, margin: "18px 0 14px" }} />
    <div style={{ color: GOLD, fontSize: 104, fontWeight: 900, letterSpacing: -2, lineHeight: 1.05 }}>
      {title[1]}
    </div>
    <div
      style={{
        position: "absolute",
        bottom: -44,
        right: 36,
        color: "rgba(255,255,255,0.85)",
        fontSize: 26,
        fontWeight: 700,
        textShadow: "0 2px 8px rgba(0,0,0,0.9)",
      }}
    >
      {credit}
    </div>
  </div>
);

const Subtitles: React.FC<{ subs: SermonClipProps["subtitles"] }> = ({ subs }) => {
  const frame = useCurrentFrame();
  const ms = (frame / FPS) * 1000;
  const sub = subs.find((s) => ms >= s.startMs && ms < s.endMs);
  if (!sub) return null;
  const pop = interpolate(ms - sub.startMs, [0, 120], [0.94, 1], { extrapolateRight: "clamp" });
  const outline = "0 0 3px #000, 0 0 3px #000, 0 4px 14px rgba(0,0,0,0.9)";
  return (
    <div
      style={{
        position: "absolute",
        top: 1130,
        left: 50,
        width: W - 100,
        textAlign: "center",
        transform: `scale(${pop})`,
      }}
    >
      <div
        style={{
          fontFamily: sub.hand ? pen : sans,
          fontWeight: sub.hand ? 400 : 900,
          fontSize: sub.hand ? 92 : 70,
          lineHeight: 1.25,
          color: "#ffffff",
          textShadow: outline,
          wordBreak: "keep-all",
          whiteSpace: "pre-line",
        }}
      >
        <Marked text={sub.text} />
      </div>
      {sub.en && (
        <div
          style={{ fontFamily: latin, fontWeight: 600, fontSize: 34, color: "#f1f1f1", marginTop: 10, textShadow: outline }}
        >
          {sub.en}
        </div>
      )}
    </div>
  );
};

export const SermonClip: React.FC<SermonClipProps> = (props) => {
  let at = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {props.segments.map((seg, k, all) => {
        const frames = msToFrame(seg.toMs) - msToFrame(seg.fromMs);
        const from = at;
        at += frames;
        // Fade the audio only at real cuts; a zoom change mid-sentence must stay seamless.
        const fadeIn = k === 0 || all[k - 1].toMs !== seg.fromMs;
        const fadeOut = k === all.length - 1 || all[k + 1].fromMs !== seg.toMs;
        return (
          <Sequence key={k} from={from} durationInFrames={frames} name={`Cut ${k + 1}`}>
            <Footage props={props} seg={seg} frames={frames} fadeIn={fadeIn} fadeOut={fadeOut} />
          </Sequence>
        );
      })}
      <AbsoluteFill
        style={{ background: "linear-gradient(180deg, rgba(0,0,0,0) 50%, rgba(0,0,0,0.35) 62%, rgba(0,0,0,0) 80%)" }}
      />
      <TitleBar title={props.title} credit={props.credit} bar={props.bar} />
      <Subtitles subs={props.subtitles} />
    </AbsoluteFill>
  );
};
