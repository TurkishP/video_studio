import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as loadPen } from "@remotion/google-fonts/NanumPenScript";
import { loadFont as loadSans } from "@remotion/google-fonts/NotoSansKR";
import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  Freeze,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  type CalculateMetadataFunction,
} from "remotion";
import { FPS } from "./Short";

const { fontFamily: sans } = loadSans("normal", {
  weights: ["700", "900"],
  subsets: ["korean", "latin"],
});
const { fontFamily: pen } = loadPen("normal", {
  weights: ["400"],
  subsets: ["korean", "latin"],
});
const { fontFamily: latin } = loadMontserrat("normal", {
  weights: ["600"],
  subsets: ["latin"],
});

// A vertical clip cut from a widescreen sermon recording: a title bar on top,
// a 9:16 window that follows the speaker, and subtitles. Props come from
// tools/build_clip.py.
export type SermonClipProps = {
  video: string; // source.mp4: the sermon section, with its own audio
  plate?: string; // the empty stage, mirrored and blurred where the window runs past the frame edge
  srcW: number;
  srcH: number;
  // Source ranges to keep, played back to back. zoom 1 shows the full height.
  segments: { fromMs: number; toMs: number; zoom: number }[];
  // Where the window is centred (0-1 of the source width), sampled every 100 ms of source time.
  track: number[];
  title: [string, string]; // second line is the big gold one
  credit: string;
  bar: string; // title bar colour
  subtitles: {
    startMs: number;
    endMs: number;
    text: string;
    en?: string | null;
    hand?: boolean;
  }[];
  // Ending card with the church logo, after the last word:
  // card = cream card, blur = frozen last frame blurred, bar = title bar grows to fill the screen.
  outro?: {
    style: "card" | "blur" | "bar";
    logo: string;
    logoLight: string;
    lines: [string, string];
    sermon?: [string, string]; // source sermon title and series, above lines
  } | null;
};
type Outro = NonNullable<SermonClipProps["outro"]>;

const W = 1080;
const H = 1920;
const BAR_H = 400;
const GOLD = "#f4c45a";
const AUDIO_FADE = 2; // frames, softens the click at each cut
const OUTRO_FRAMES = 105;
const FILL_MAX = W * 0.32; // how far past the frame edge the picture may slide, over the plate
const msToFrame = (ms: number) => Math.round((ms / 1000) * FPS);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = { ...clamp, easing: Easing.inOut(Easing.cubic) };

const speechFrames = (props: SermonClipProps) =>
  props.segments.reduce(
    (n, s) => n + msToFrame(s.toMs) - msToFrame(s.fromMs),
    0,
  );

export const calculateSermonMetadata: CalculateMetadataFunction<
  SermonClipProps
> = ({ props }) => ({
  durationInFrames: Math.max(
    1,
    speechFrames(props) + (props.outro ? OUTRO_FRAMES : 0),
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
  muted?: boolean;
}> = ({ props, seg, frames, fadeIn, fadeOut, muted }) => {
  const frame = useCurrentFrame();
  const sourceMs = seg.fromMs + (frame / FPS) * 1000;
  const i = Math.min(props.track.length - 1, Math.max(0, sourceMs / 100));
  const lo = Math.floor(i);
  const hi = Math.min(props.track.length - 1, lo + 1);
  const cx = props.track[lo] + (props.track[hi] - props.track[lo]) * (i - lo);
  // Scale the source so its height fills the frame (times zoom), then slide it.
  const h = H * seg.zoom;
  const w = (h * props.srcW) / props.srcH;
  const reach = props.plate ? FILL_MAX : 0;
  const left = Math.min(reach, Math.max(W - w - reach, W / 2 - cx * w));
  const top = Math.min(0, Math.max(H - h, H * 0.52 - 0.42 * h)); // zoomed: keep the upper body
  // The speaker at the frame edge: the window runs past it, and the stage,
  // mirrored at the edge and blurred as one layer so the seam stays soft, fills in.
  const fill = props.plate && (left > 0 || left + w < W);
  return (
    <>
      {fill && (
        <AbsoluteFill style={{ filter: "blur(26px) brightness(0.72)" }}>
          {[-1, 0, 1].map((side) => (
            <Img
              key={side}
              src={staticFile(props.plate!)}
              style={{
                position: "absolute",
                left: left + side * w,
                top,
                width: w,
                height: h,
                transform: side ? "scaleX(-1)" : undefined,
              }}
            />
          ))}
        </AbsoluteFill>
      )}
      <div style={{ position: "absolute", left, top, width: w, height: h }}>
        <Video
          src={staticFile(props.video)}
          trimBefore={msToFrame(seg.fromMs)}
          trimAfter={msToFrame(seg.toMs)}
          muted={muted}
          volume={(f) =>
            interpolate(
              f,
              [0, AUDIO_FADE, frames - AUDIO_FADE, frames],
              [fadeIn ? 0 : 1, 1, 1, fadeOut ? 0 : 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              },
            )
          }
          style={{ width: "100%", height: "100%" }}
        />
      </div>
    </>
  );
};

// During the outro (t = frames since it began) the bar slides away for "card"
// and grows to fill the screen for "bar".
const TitleBar: React.FC<{
  title: [string, string];
  credit: string;
  bar: string;
  outro?: Outro | null;
  t: number;
}> = ({ title, credit, bar, outro, t }) => {
  const slide =
    outro?.style === "card"
      ? interpolate(t, [0, 10], [0, -BAR_H - 60], ease)
      : 0;
  const grow =
    outro?.style === "bar" ? interpolate(t, [0, 14], [0, H - BAR_H], ease) : 0;
  const words =
    outro?.style === "bar" ? interpolate(t, [0, 6], [1, 0], clamp) : 1;
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: W,
        height: BAR_H + grow,
        transform: `translateY(${slide}px)`,
        backgroundColor: bar,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-end",
        paddingBottom: 44 + grow,
        fontFamily: sans,
        boxShadow: "0 8px 40px rgba(0,0,0,0.45)",
      }}
    >
      <div
        style={{
          opacity: words,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <div
          style={{
            color: "#f6efe3",
            fontSize: 64,
            fontWeight: 700,
            letterSpacing: -1,
          }}
        >
          {title[0]}
        </div>
        <div
          style={{
            width: 120,
            height: 3,
            backgroundColor: GOLD,
            opacity: 0.8,
            margin: "18px 0 14px",
          }}
        />
        <div
          style={{
            color: GOLD,
            fontSize: 104,
            fontWeight: 900,
            letterSpacing: -2,
            lineHeight: 1.05,
          }}
        >
          {title[1]}
        </div>
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
          opacity: outro ? interpolate(t, [0, 6], [1, 0], clamp) : 1,
        }}
      >
        {credit}
      </div>
    </div>
  );
};

// The logo, a gold rule and two lines, rising in after the background settles.
const OutroCard: React.FC<{ outro: Outro }> = ({ outro }) => {
  const t = useCurrentFrame();
  const { fps } = useVideoConfig();
  const onLight = outro.style === "card";
  const start = outro.style === "bar" ? 12 : 8;
  const rise = spring({ frame: t - start, fps, config: { damping: 200 } });
  const rule = interpolate(t, [start + 10, start + 22], [0, 160], ease);
  const later = outro.sermon ? 10 : 0;
  const sermon = interpolate(t, [start + 14, start + 24], [0, 1], clamp);
  const line1 = interpolate(t, [start + 14 + later, start + 24 + later], [0, 1], clamp);
  const line2 = interpolate(t, [start + 20 + later, start + 30 + later], [0, 1], clamp);
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        paddingBottom: 260,
        fontFamily: sans,
      }}
    >
      <Img
        src={staticFile(onLight ? outro.logo : outro.logoLight)}
        style={{
          width: 720,
          opacity: rise,
          transform: `translateY(${(1 - rise) * 40}px) scale(${0.92 + 0.08 * rise})`,
        }}
      />
      <div
        style={{
          width: rule,
          height: 3,
          backgroundColor: onLight ? "#c79a3a" : GOLD,
          margin: "56px 0 40px",
        }}
      />
      {outro.sermon && (
        <div
          style={{
            opacity: sermon,
            transform: `translateY(${(1 - sermon) * 16}px)`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            marginBottom: 52,
          }}
        >
          <div
            style={{
              maxWidth: 900,
              textAlign: "center",
              fontSize: 50,
              fontWeight: 900,
              lineHeight: 1.3,
              letterSpacing: -1,
              wordBreak: "keep-all",
              color: onLight ? "#2f2b2a" : "#f6efe3",
            }}
          >
            {outro.sermon[0]}
          </div>
          <div
            style={{
              fontFamily: latin,
              fontSize: 34,
              fontWeight: 600,
              letterSpacing: 2,
              marginTop: 14,
              color: onLight ? "#c79a3a" : GOLD,
            }}
          >
            {outro.sermon[1]}
          </div>
        </div>
      )}
      <div
        style={{
          fontSize: 52,
          fontWeight: 700,
          color: onLight ? "#2f2b2a" : "#f6efe3",
          opacity: line1,
          transform: `translateY(${(1 - line1) * 16}px)`,
        }}
      >
        {outro.lines[0]}
      </div>
      <div
        style={{
          fontSize: 36,
          fontWeight: 700,
          marginTop: 18,
          color: onLight ? "#7a716b" : "rgba(246,239,227,0.72)",
          opacity: line2,
        }}
      >
        {outro.lines[1]}
      </div>
    </AbsoluteFill>
  );
};

const Subtitles: React.FC<{ subs: SermonClipProps["subtitles"] }> = ({
  subs,
}) => {
  const frame = useCurrentFrame();
  const ms = (frame / FPS) * 1000;
  const sub = subs.find((s) => ms >= s.startMs && ms < s.endMs);
  if (!sub) return null;
  const pop = interpolate(ms - sub.startMs, [0, 120], [0.94, 1], {
    extrapolateRight: "clamp",
  });
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
          style={{
            fontFamily: latin,
            fontWeight: 600,
            fontSize: 34,
            color: "#f1f1f1",
            marginTop: 10,
            textShadow: outline,
          }}
        >
          {sub.en}
        </div>
      )}
    </div>
  );
};

export const SermonClip: React.FC<SermonClipProps> = (props) => {
  const frame = useCurrentFrame();
  const end = speechFrames(props);
  const { outro } = props;
  const last = props.segments[props.segments.length - 1];
  const lastFrames = msToFrame(last.toMs) - msToFrame(last.fromMs);
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
          <Sequence
            key={k}
            from={from}
            durationInFrames={frames}
            name={`Cut ${k + 1}`}
          >
            <Footage
              props={props}
              seg={seg}
              frames={frames}
              fadeIn={fadeIn}
              fadeOut={fadeOut}
            />
          </Sequence>
        );
      })}
      {outro && (
        <Sequence
          from={end}
          durationInFrames={OUTRO_FRAMES}
          name="Outro background"
        >
          <OutroBackground
            props={props}
            outro={outro}
            last={last}
            lastFrames={lastFrames}
          />
        </Sequence>
      )}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0) 50%, rgba(0,0,0,0.35) 62%, rgba(0,0,0,0) 80%)",
          opacity: outro ? interpolate(frame - end, [0, 8], [1, 0], clamp) : 1, // subtitle shade, gone for the outro
        }}
      />
      <TitleBar
        title={props.title}
        credit={props.credit}
        bar={props.bar}
        outro={outro}
        t={frame - end}
      />
      <Subtitles subs={props.subtitles} />
      {outro && (
        <Sequence from={end} durationInFrames={OUTRO_FRAMES} name="Outro">
          <OutroCard outro={outro} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};

// The last frame holds still behind the outro: blurred and darkened for
// "blur", covered by a cream card for "card", by the growing bar for "bar".
const OutroBackground: React.FC<{
  props: SermonClipProps;
  outro: Outro;
  last: SermonClipProps["segments"][number];
  lastFrames: number;
}> = ({ props, outro, last, lastFrames }) => {
  const t = useCurrentFrame();
  const blur =
    outro.style === "blur" ? interpolate(t, [0, 12], [0, 22], ease) : 0;
  const dim =
    outro.style === "blur" ? interpolate(t, [0, 12], [1, 0.42], ease) : 1;
  return (
    <AbsoluteFill>
      <AbsoluteFill
        style={{
          filter: `blur(${blur}px) brightness(${dim})`,
          transform: `scale(${1 + blur / 400})`,
        }}
      >
        <Freeze frame={lastFrames - 1}>
          <Footage
            props={props}
            seg={last}
            frames={lastFrames}
            fadeIn={false}
            fadeOut={false}
            muted
          />
        </Freeze>
      </AbsoluteFill>
      {outro.style === "card" && (
        <AbsoluteFill
          style={{
            backgroundColor: "#f6f1e8",
            opacity: interpolate(t, [0, 10], [0, 1], ease),
          }}
        />
      )}
    </AbsoluteFill>
  );
};
