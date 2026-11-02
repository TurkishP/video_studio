import { createTikTokStyleCaptions, type Caption } from "@remotion/captions";
import { loadFont as loadSerif } from "@remotion/google-fonts/EBGaramond";
import { loadFont } from "@remotion/google-fonts/Montserrat";
import { Audio, Video } from "@remotion/media";
import { useMemo } from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  type CalculateMetadataFunction,
} from "remotion";

const { fontFamily: sans } = loadFont("normal", {
  weights: ["800", "900"],
  subsets: ["latin"],
});
const { fontFamily: serif } = loadSerif("normal", {
  weights: ["600", "800"],
  subsets: ["latin", "greek", "greek-ext"],
});
loadSerif("italic", { weights: ["700"], subsets: ["latin", "greek", "greek-ext"] });

export const FPS = 30;
const FADE = 8; // crossfade frames between scenes
const CHAPTER_CARD_FRAMES = 84;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

// Where things sit in each format. Shorts keep text clear of the platform UI
// (roughly the top 200px, the bottom 25% and a strip on the right).
const LAYOUTS = {
  short: {
    width: 1080,
    height: 1920,
    kickerTop: 240,
    headlineTop: 230,
    headlineSize: 104,
    sourcesTop: 1020,
    citeTop: 1060,
    captionsTop: 1160,
    captionWidth: 860,
    captionScale: 1,
    statTop: 420,
    statSize: 340,
    statementPad: "0 90px 260px",
    chapterSize: 96,
  },
  // Long videos: captions as a lower third, text kept inside a 1600px column.
  long: {
    width: 1920,
    height: 1080,
    kickerTop: 70,
    headlineTop: 80,
    headlineSize: 96,
    sourcesTop: 1000,
    citeTop: 800,
    captionsTop: 860,
    captionWidth: 1500,
    captionScale: 0.8,
    statTop: 200,
    statSize: 300,
    statementPad: "0 380px 80px", // a 1160px column keeps the reveal centred
    chapterSize: 120,
  },
};
type Layout = (typeof LAYOUTS)["short"];

export type Theme = {
  captionFont: string;
  captionWeight: number;
  uppercase: boolean;
  captionSize: number;
  displayFont: string; // headlines, statements, stats, labels
  displayWeight: number;
  accent: string;
  text: string;
  stroke: string;
  strokeWidth: number;
  emphasisFont: string; // *starred* words in the script
  emphasisStyle: "normal" | "italic";
  emphasisColor: string;
  highlightActive: boolean; // colour the word being spoken
  kicker: "pill" | "rule";
  statBackground: string;
  grade?: string; // CSS filter applied to footage
  grain: boolean;
};

export const THEMES = {
  // Bright TikTok look: heavy sans, yellow highlight.
  bold: {
    captionFont: sans,
    captionWeight: 900,
    uppercase: true,
    captionSize: 86,
    displayFont: sans,
    displayWeight: 900,
    accent: "#FFD60A",
    text: "white",
    stroke: "black",
    strokeWidth: 16,
    emphasisFont: sans,
    emphasisStyle: "normal",
    emphasisColor: "#FFD60A",
    highlightActive: true,
    kicker: "pill",
    statBackground: "radial-gradient(circle at 50% 30%, #1d2f55, #05070d 70%)",
    grain: false,
  },
  // Gallery look for paintings: clean sans captions, gold italic serif emphasis,
  // warm grade, film grain.
  museum: {
    captionFont: sans,
    captionWeight: 800,
    uppercase: false,
    captionSize: 76,
    displayFont: serif,
    displayWeight: 800,
    accent: "#F2C14E",
    text: "#FFF8EC",
    stroke: "#120a04",
    strokeWidth: 10,
    emphasisFont: serif,
    emphasisStyle: "italic",
    emphasisColor: "#F2C14E",
    highlightActive: false,
    kicker: "rule",
    statBackground: "radial-gradient(circle at 50% 30%, #3b2a18, #0c0805 70%)",
    grade: "sepia(0.15) saturate(0.95) contrast(1.06)",
    grain: true,
  },
} satisfies Record<string, Theme>;

type Shot = { startMs: number; focus?: [number, number]; zoom?: number; clip?: string };
type ImageVisual = { type: "image"; src: string; w?: number; h?: number; shots?: Shot[] };
type Visual =
  | ImageVisual
  | { type: "video"; src: string }
  | { type: "stat"; value: string; label: string }
  | { type: "statement"; bg?: string };
type Transition = "cut" | "fade" | "zoom" | "flash";

type Scene = {
  startMs: number;
  endMs: number;
  visual: Visual;
  kicker?: string | null;
  headline?: string | null;
  cite?: string | null;
  transition?: Transition | null;
  chapter?: { index: number; title: string } | null;
};

export type ShortProps = {
  format?: keyof typeof LAYOUTS;
  theme: keyof typeof THEMES;
  durationMs: number;
  voice: string | null;
  music?: string | null;
  musicVolume: number;
  sfx?: string | null;
  captionsOn?: boolean;
  scenes: Scene[];
  captions: Caption[];
  sources: string[];
};

export const calculateShortMetadata: CalculateMetadataFunction<ShortProps> = ({
  props,
}) => {
  const l = LAYOUTS[props.format ?? "short"];
  return {
    durationInFrames: Math.ceil((props.durationMs / 1000) * FPS),
    width: l.width,
    height: l.height,
  };
};

const msToFrame = (ms: number) => Math.round((ms / 1000) * FPS);
const isEmphasis = (text: string) => text.includes("*");
const clean = (text: string) => text.trim().replace(/\*/g, "");
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];

// Words wrapped in *asterisks* get the theme's emphasis style.
export const Emphasized: React.FC<{ text: string; t: Theme }> = ({ text, t }) => (
  <>
    {text.split(" ").map((word, i) => (
      <span
        key={i}
        style={
          isEmphasis(word)
            ? { fontFamily: t.emphasisFont, fontStyle: t.emphasisStyle, color: t.emphasisColor }
            : undefined
        }
      >
        {i > 0 && " "}
        {clean(word)}
      </span>
    ))}
  </>
);

// Fills the frame (or a box of boxW x boxH) with the part of a still around
// `focus` (0-1 image coordinates), magnified by `zoom`, with a slow push and drift.
export const Pan: React.FC<{
  src: string;
  w: number;
  h: number;
  focus: [number, number];
  zoom: number;
  frames: number;
  index: number;
  boxW?: number;
  boxH?: number;
}> = ({ src, w, h, focus, zoom, frames, index, boxW, boxH }) => {
  const frame = useCurrentFrame();
  const video = useVideoConfig();
  const W = boxW ?? video.width;
  const H = boxH ?? video.height;
  const progress = frames > 0 ? frame / frames : 0;
  const s = Math.max(W / w, H / h) * zoom * interpolate(progress, [0, 1], [1, 1.07]);
  const dw = w * s;
  const dh = h * s;
  const drift = interpolate(progress, [0, 1], index % 2 ? [-0.012, 0.012] : [0.012, -0.012]);
  const left = Math.min(0, Math.max(W - dw, W / 2 - (focus[0] + drift) * dw));
  const top = Math.min(0, Math.max(H - dh, H / 2 - focus[1] * dh));
  return (
    <Img src={staticFile(src)} style={{ position: "absolute", left, top, width: dw, height: dh }} />
  );
};

// A beat on one image: the opening shot (often a 3D DepthFlow clip), then hard
// cuts to punch-ins on details.
const ImageScene: React.FC<{
  visual: ImageVisual;
  sceneStartMs: number;
  frames: number;
  index: number;
}> = ({ visual, sceneStartMs, frames, index }) => {
  const shots = visual.shots?.length ? visual.shots : [{ startMs: sceneStartMs }];
  return (
    <>
      {shots.map((shot, k) => {
        const from = msToFrame(shot.startMs - sceneStartMs);
        const until = k + 1 < shots.length ? msToFrame(shots[k + 1].startMs - sceneStartMs) : frames;
        return (
          <Sequence key={k} from={from} durationInFrames={Math.max(1, until - from)} name={`Shot ${k + 1}`}>
            {shot.clip ? (
              <Video
                src={staticFile(shot.clip)}
                muted
                loop
                objectFit="cover"
                style={{ width: "100%", height: "100%" }}
              />
            ) : visual.w && visual.h ? (
              <Pan
                src={visual.src}
                w={visual.w}
                h={visual.h}
                focus={shot.focus ?? [0.5, 0.5]}
                zoom={shot.zoom ?? 1}
                frames={until - from}
                index={index + k}
              />
            ) : (
              <Img
                src={staticFile(visual.src)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            )}
          </Sequence>
        );
      })}
    </>
  );
};

const Stat: React.FC<{ value: string; label: string; t: Theme; l: Layout }> = ({
  value,
  label,
  t,
  l,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12 } });
  return (
    <AbsoluteFill
      style={{
        background: t.statBackground,
        alignItems: "center",
        paddingTop: l.statTop,
        fontFamily: t.displayFont,
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontWeight: t.displayWeight,
          fontSize: value.length > 5 ? l.statSize * 0.65 : l.statSize, // keep longer values on one line
          lineHeight: 1,
          color: t.accent,
          transform: `scale(${pop})`,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontWeight: 800,
          fontSize: 64,
          color: t.text,
          textTransform: "uppercase",
          letterSpacing: 3,
          marginTop: 24,
          padding: "0 110px",
          opacity: pop,
        }}
      >
        {label}
      </div>
    </AbsoluteFill>
  );
};

// Full-screen punchline: the beat's words appear one by one as they are spoken.
const Statement: React.FC<{
  scene: Scene;
  captions: Caption[];
  t: Theme;
  l: Layout;
  bg?: string;
}> = ({ scene, captions, t, l, bg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const nowMs = scene.startMs + (frame / fps) * 1000;
  const words = captions.filter((c) => c.startMs >= scene.startMs && c.startMs < scene.endMs);
  const size = words.length > 14 ? 84 : words.length > 9 ? 98 : 112;
  return (
    <AbsoluteFill style={{ background: t.statBackground }}>
      {bg && (
        <Img
          src={staticFile(bg)}
          style={{
            position: "absolute",
            width: "100%",
            height: "100%",
            objectFit: "cover",
            filter: "blur(28px) brightness(0.3) saturate(0.9)",
            transform: "scale(1.15)",
          }}
        />
      )}
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", padding: l.statementPad }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            columnGap: "0.28em",
            fontFamily: t.displayFont,
            fontWeight: t.displayWeight,
            fontSize: size,
            lineHeight: 1.15,
            color: t.text,
          }}
        >
          {words.map((c) => {
            const enter = spring({
              frame: frame - msToFrame(c.startMs - scene.startMs),
              fps,
              config: { damping: 16, stiffness: 180 },
              durationInFrames: 10,
            });
            const emph = isEmphasis(c.text);
            return (
              <span
                key={c.startMs}
                style={{
                  display: "inline-block",
                  opacity: c.startMs <= nowMs ? enter : 0,
                  transform: `translateY(${(1 - enter) * 30}px)`,
                  fontStyle: emph ? "italic" : "normal",
                  color: emph ? t.emphasisColor : t.text,
                }}
              >
                {clean(c.text)}
              </span>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const Headline: React.FC<{ text: string; t: Theme; l: Layout }> = ({ text, t, l }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 2, fps, config: { damping: 13 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: l.headlineTop }}>
      <div
        style={{
          maxWidth: l.captionWidth + 60,
          textAlign: "center",
          fontFamily: t.displayFont,
          fontWeight: t.displayWeight,
          fontSize: l.headlineSize,
          lineHeight: 1.05,
          color: t.text,
          textShadow: "0 4px 30px rgba(0,0,0,0.85), 0 2px 6px rgba(0,0,0,0.9)",
          opacity: enter,
          transform: `scale(${interpolate(enter, [0, 1], [1.25, 1])})`,
        }}
      >
        <Emphasized text={text} t={t} />
      </div>
    </AbsoluteFill>
  );
};

// Small source line for scripture and quotes, just above the captions.
const Cite: React.FC<{ text: string; t: Theme; l: Layout }> = ({ text, t, l }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: l.citeTop }}>
      <div
        style={{
          fontFamily: t.displayFont,
          fontStyle: "italic",
          fontWeight: 700,
          fontSize: 42,
          color: t.emphasisColor,
          textShadow: "0 2px 10px rgba(0,0,0,0.95)",
          opacity: interpolate(frame, [4, 14], [0, 0.95], clamp),
        }}
      >
        — {text}
      </div>
    </AbsoluteFill>
  );
};

// Opens a chapter for its first ~3 s: number and title over a dimmed picture.
const ChapterCard: React.FC<{ index: number; title: string; t: Theme; l: Layout }> = ({
  index,
  title,
  t,
  l,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = interpolate(frame, [0, 8, CHAPTER_CARD_FRAMES - 14, CHAPTER_CARD_FRAMES], [0, 1, 1, 0], clamp);
  const rise = spring({ frame, fps, config: { damping: 15 } });
  return (
    <AbsoluteFill
      style={{
        background: "rgba(8,5,2,0.55)",
        justifyContent: "center",
        alignItems: "center",
        textAlign: "center",
        fontFamily: t.displayFont,
        opacity: fade,
      }}
    >
      <div
        style={{
          color: t.accent,
          fontWeight: 600,
          fontSize: l.chapterSize * 0.36,
          letterSpacing: 10,
          textTransform: "uppercase",
          textShadow: "0 2px 10px rgba(0,0,0,0.9)",
        }}
      >
        Chapter {ROMAN[index - 1] ?? index}
      </div>
      <div
        style={{
          color: t.text,
          fontWeight: t.displayWeight,
          fontSize: l.chapterSize,
          lineHeight: 1.05,
          maxWidth: l.captionWidth,
          marginTop: 12,
          textShadow: "0 4px 30px rgba(0,0,0,0.85)",
          transform: `translateY(${interpolate(rise, [0, 1], [24, 0])}px)`,
        }}
      >
        <Emphasized text={title} t={t} />
      </div>
    </AbsoluteFill>
  );
};

const Kicker: React.FC<{ text: string; t: Theme; l: Layout }> = ({ text, t, l }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - 3, fps, config: { damping: 14 } });
  const motion = {
    opacity: enter,
    transform: `translateY(${interpolate(enter, [0, 1], [-40, 0])}px)`,
  };
  if (t.kicker === "rule") {
    const rule = { width: 70, height: 3, background: t.accent };
    return (
      <AbsoluteFill style={{ alignItems: "center", paddingTop: l.kickerTop }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 26,
            maxWidth: 900,
            color: t.accent,
            fontFamily: t.displayFont,
            fontWeight: 600,
            fontSize: 50,
            letterSpacing: 7,
            textTransform: "uppercase",
            textShadow: "0 2px 6px rgba(0,0,0,0.9)",
            // Soft dark backing so gold stays readable on pale drawings.
            background: "rgba(12,8,4,0.55)",
            padding: "12px 30px",
            borderRadius: 999,
            ...motion,
          }}
        >
          <div style={rule} />
          {text}
          <div style={rule} />
        </div>
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: l.kickerTop }}>
      <div
        style={{
          maxWidth: 860,
          background: t.accent,
          color: "#0a0a0a",
          fontFamily: t.displayFont,
          fontWeight: 900,
          fontSize: 58,
          lineHeight: 1.15,
          textTransform: "uppercase",
          textAlign: "center",
          padding: "18px 34px",
          borderRadius: 18,
          boxShadow: "0 10px 30px rgba(0,0,0,0.45)",
          ...motion,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

const SceneView: React.FC<{
  scene: Scene;
  index: number;
  frames: number;
  t: Theme;
  l: Layout;
  captions: Caption[];
}> = ({ scene, index, frames, t, l, captions }) => {
  const frame = useCurrentFrame();
  const kind = index === 0 ? "cut" : (scene.transition ?? "fade");
  let entrance: React.CSSProperties = {};
  if (kind === "fade") {
    entrance = { opacity: interpolate(frame, [0, FADE], [0, 1], clamp) };
  } else if (kind === "zoom") {
    // Punch in from a blurred close-up.
    const p = interpolate(frame, [0, 9], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
    entrance = {
      opacity: interpolate(frame, [0, 3], [0, 1], clamp),
      transform: `scale(${interpolate(p, [0, 1], [1.35, 1])})`,
      filter: `blur(${interpolate(p, [0, 1], [14, 0])}px)`,
    };
  }
  const { visual } = scene;
  const isFootage = visual.type === "image" || visual.type === "video";
  return (
    <AbsoluteFill style={{ backgroundColor: "#05070d", ...entrance }}>
      <AbsoluteFill style={{ filter: t.grade }}>
        {visual.type === "image" && (
          <ImageScene visual={visual} sceneStartMs={scene.startMs} frames={frames} index={index} />
        )}
        {visual.type === "video" && (
          <Video
            src={staticFile(visual.src)}
            muted
            loop
            objectFit="cover"
            style={{ width: "100%", height: "100%" }}
          />
        )}
      </AbsoluteFill>
      {visual.type === "stat" && <Stat value={visual.value} label={visual.label} t={t} l={l} />}
      {visual.type === "statement" && (
        <Statement scene={scene} captions={captions} t={t} l={l} bg={visual.bg} />
      )}
      {isFootage && (
        <AbsoluteFill
          style={{
            background:
              "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0) 30%, rgba(0,0,0,0) 45%, rgba(0,0,0,0.65) 100%)",
          }}
        />
      )}
      {scene.kicker && <Kicker text={scene.kicker} t={t} l={l} />}
      {scene.headline && !scene.chapter && <Headline text={scene.headline} t={t} l={l} />}
      {scene.headline && scene.chapter && (
        <Sequence from={CHAPTER_CARD_FRAMES} name="Headline">
          <Headline text={scene.headline} t={t} l={l} />
        </Sequence>
      )}
      {scene.cite && (
        <Sequence from={scene.chapter ? CHAPTER_CARD_FRAMES : 0} name="Cite">
          <Cite text={scene.cite} t={t} l={l} />
        </Sequence>
      )}
      {scene.chapter && (
        <Sequence durationInFrames={CHAPTER_CARD_FRAMES} name="Chapter card">
          <ChapterCard index={scene.chapter.index} title={scene.chapter.title} t={t} l={l} />
        </Sequence>
      )}
      {kind === "flash" && (
        <AbsoluteFill
          style={{ backgroundColor: "white", opacity: interpolate(frame, [0, 7], [0.85, 0], clamp) }}
        />
      )}
    </AbsoluteFill>
  );
};

const Captions: React.FC<{
  captions: Caption[];
  t: Theme;
  l: Layout;
  hidden: [number, number][];
}> = ({ captions, t, l, hidden }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pages = useMemo(() => {
    // Start a new page at each sentence so a page never straddles a full stop.
    const sentences: Caption[][] = [[]];
    for (const c of captions) {
      sentences[sentences.length - 1].push(c);
      if (/[.!?]\**$/.test(c.text)) sentences.push([]);
    }
    return sentences
      .filter((s) => s.length > 0)
      .flatMap(
        (s) => createTikTokStyleCaptions({ captions: s, combineTokensWithinMilliseconds: 650 }).pages,
      );
  }, [captions]);
  const nowMs = (frame / fps) * 1000;
  const page = pages.find((p) => p.startMs <= nowMs && nowMs < p.startMs + p.durationMs);
  if (!page || hidden.some(([a, b]) => a <= nowMs && nowMs < b)) return null;

  const size = t.captionSize * l.captionScale;
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: l.captionsTop }}>
      <div
        style={{
          width: l.captionWidth,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "baseline",
          columnGap: "0.26em",
          fontFamily: t.captionFont,
          fontWeight: t.captionWeight,
          fontSize: size,
          lineHeight: 1.15,
          textTransform: t.uppercase ? "uppercase" : "none",
          WebkitTextStroke: `${t.strokeWidth * l.captionScale}px ${t.stroke}`,
          paintOrder: "stroke fill",
          textShadow: "0 6px 24px rgba(0,0,0,0.6)",
        }}
      >
        {page.tokens.map((tok) => {
          // Words pop in as they are spoken; unspoken ones keep their space.
          const shown = tok.fromMs <= nowMs;
          const enter = spring({
            frame: frame - msToFrame(tok.fromMs),
            fps,
            config: { damping: 14, stiffness: 260 },
            durationInFrames: 7,
          });
          const style: React.CSSProperties = isEmphasis(tok.text)
            ? {
                fontFamily: t.emphasisFont,
                fontStyle: t.emphasisStyle,
                fontSize: size * 1.22,
                color: t.emphasisColor,
              }
            : { color: t.highlightActive && shown && nowMs < tok.toMs ? t.accent : t.text };
          return (
            <span
              key={tok.fromMs}
              style={{
                display: "inline-block",
                opacity: shown ? 1 : 0,
                transform: `translateY(${(1 - enter) * 22}px) scale(${0.8 + 0.2 * enter})`,
                ...style,
              }}
            >
              {clean(tok.text)}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Sources: React.FC<{ sources: string[]; t: Theme; l: Layout }> = ({ sources, t, l }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 10], [0, 0.9], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: l.sourcesTop }}>
      <div
        style={{
          maxWidth: l.captionWidth,
          color: t.text,
          fontFamily: t.displayFont,
          fontWeight: 800,
          fontSize: 34,
          textAlign: "center",
          textShadow: "0 2px 10px rgba(0,0,0,0.9)",
          opacity,
        }}
      >
        Sources: {sources.join(" · ")}
      </div>
    </AbsoluteFill>
  );
};

// Animated film grain; a new noise seed every frame.
const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ opacity: 0.1, mixBlendMode: "overlay" }}>
      <svg width="100%" height="100%">
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={frame} />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};

export const Short: React.FC<ShortProps> = ({
  format,
  theme,
  durationMs,
  voice,
  music,
  musicVolume,
  sfx,
  captionsOn,
  scenes,
  captions,
  sources,
}) => {
  const frame = useCurrentFrame();
  const t: Theme = THEMES[theme] ?? THEMES.bold;
  const l: Layout = LAYOUTS[format ?? "short"];
  const totalFrames = msToFrame(durationMs);
  const sourcesFrames = Math.min(3.5 * FPS, totalFrames);
  const statements = scenes
    .filter((s) => s.visual.type === "statement")
    .map((s): [number, number] => [s.startMs, s.endMs]);
  const emphasisFrames = useMemo(
    () => captions.filter((c) => isEmphasis(c.text)).map((c) => msToFrame(c.startMs)),
    [captions],
  );
  // A small punch on the picture each time an emphasized word lands.
  let pulse = 0;
  for (const f of emphasisFrames) {
    const d = frame - f;
    if (d >= 0 && d < 14) pulse = Math.max(pulse, Math.exp(-d / 4));
  }
  return (
    <AbsoluteFill style={{ backgroundColor: "#05070d" }}>
      <AbsoluteFill style={{ transform: `scale(${1 + 0.03 * pulse})` }}>
        {scenes.map((scene, i) => {
          const from = msToFrame(scene.startMs);
          const isLast = i === scenes.length - 1;
          const frames = (isLast ? totalFrames : msToFrame(scene.endMs) + FADE) - from;
          return (
            <Sequence key={i} from={from} durationInFrames={frames} name={`Scene ${i + 1}`}>
              <SceneView scene={scene} index={i} frames={frames} t={t} l={l} captions={captions} />
            </Sequence>
          );
        })}
      </AbsoluteFill>
      {t.grain && <Grain />}
      {captionsOn !== false && <Captions captions={captions} t={t} l={l} hidden={statements} />}
      {sources.length > 0 && (
        <Sequence from={totalFrames - sourcesFrames} name="Sources">
          <Sources sources={sources} t={t} l={l} />
        </Sequence>
      )}
      {sfx &&
        scenes.map((scene, i) =>
          i > 0 && (scene.transition === "zoom" || scene.transition === "flash") ? (
            <Sequence key={`sfx${i}`} from={Math.max(0, msToFrame(scene.startMs) - 4)} name="Whoosh">
              <Audio src={staticFile(sfx)} volume={0.45} />
            </Sequence>
          ) : null,
        )}
      {voice && <Audio src={staticFile(voice)} />}
      {music && <Audio src={staticFile(music)} volume={musicVolume} loop />}
    </AbsoluteFill>
  );
};
