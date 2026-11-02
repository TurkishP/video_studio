import { Composition, Still } from "remotion";
import { SermonClip, calculateSermonMetadata, type SermonClipProps } from "./SermonClip";
import { FPS, Short, calculateShortMetadata, type ShortProps } from "./Short";
import { Thumbnail, type ThumbnailProps } from "./Thumbnail";

// Placeholder shown when the studio opens without --props.
const defaultProps: ShortProps = {
  format: "short",
  theme: "bold",
  durationMs: 3000,
  voice: null,
  music: null,
  musicVolume: 0.12,
  scenes: [
    {
      startMs: 0,
      endMs: 3000,
      visual: { type: "stat", value: "9:16", label: "Run /make-short" },
    },
  ],
  captions: [],
  sources: [],
};

const thumbnailDefaults: ThumbnailProps = {
  theme: "museum",
  src: "thumbnail.jpg",
  w: 1280,
  h: 720,
  text: "Run *build_props*",
};

const sermonDefaults: SermonClipProps = {
  video: "source.mp4",
  srcW: 1280,
  srcH: 720,
  segments: [{ fromMs: 0, toMs: 3000, zoom: 1 }],
  track: [0.5],
  title: ["Run", "build_clip.py"],
  credit: "",
  bar: "#2b1418",
  subtitles: [],
};

// One template for both formats: props.format picks 1080x1920 or 1920x1080.
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Short"
        component={Short}
        width={1080}
        height={1920}
        fps={FPS}
        durationInFrames={90}
        defaultProps={defaultProps}
        calculateMetadata={calculateShortMetadata}
      />
      <Composition
        id="Long"
        component={Short}
        width={1920}
        height={1080}
        fps={FPS}
        durationInFrames={90}
        defaultProps={{ ...defaultProps, format: "long" }}
        calculateMetadata={calculateShortMetadata}
      />
      <Still id="Thumbnail" component={Thumbnail} width={1280} height={720} defaultProps={thumbnailDefaults} />
      <Composition
        id="SermonClip"
        component={SermonClip}
        width={1080}
        height={1920}
        fps={FPS}
        durationInFrames={90}
        defaultProps={sermonDefaults}
        calculateMetadata={calculateSermonMetadata}
      />
    </>
  );
};
