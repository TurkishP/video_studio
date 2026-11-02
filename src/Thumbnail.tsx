import { AbsoluteFill, Img, staticFile } from "remotion";
import { Emphasized, Pan, THEMES, type Theme } from "./Short";

// A 1280x720 YouTube thumbnail: the painting's subject on the right, a few big
// words on the left. Render with `npx remotion still Thumbnail`.
export type ThumbnailProps = {
  theme: keyof typeof THEMES;
  src: string;
  w: number;
  h: number;
  focus?: [number, number];
  zoom?: number;
  text: string; // 2 to 5 words; *starred* words take the emphasis colour
  label?: string | null;
};

const PICTURE_LEFT = 440; // the subject is centred in the right 840px

export const Thumbnail: React.FC<ThumbnailProps> = ({ theme, src, w, h, focus, zoom, text, label }) => {
  const t: Theme = THEMES[theme] ?? THEMES.museum;
  return (
    <AbsoluteFill style={{ backgroundColor: "#05070d" }}>
      <AbsoluteFill style={{ filter: t.grade }}>
        <Img
          src={staticFile(src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            filter: "blur(24px) brightness(0.45)",
            transform: "scale(1.1)",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: PICTURE_LEFT,
            top: 0,
            width: 1280 - PICTURE_LEFT,
            height: 720,
            overflow: "hidden",
            // Feather the left edge into the blurred background.
            maskImage: "linear-gradient(90deg, transparent 0, black 180px)",
          }}
        >
          <Pan
            src={src}
            w={w}
            h={h}
            focus={focus ?? [0.5, 0.5]}
            zoom={zoom ?? 1}
            frames={1}
            index={0}
            boxW={1280 - PICTURE_LEFT}
            boxH={720}
          />
        </div>
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.7) 34%, rgba(0,0,0,0.15) 52%, rgba(0,0,0,0) 70%)",
        }}
      />
      <AbsoluteFill style={{ justifyContent: "center", padding: "0 0 0 64px" }}>
        <div style={{ width: 640, fontFamily: t.displayFont }}>
          {label && (
            <div
              style={{
                color: t.accent,
                fontWeight: 600,
                fontSize: 30,
                letterSpacing: 5,
                textTransform: "uppercase",
                marginBottom: 14,
              }}
            >
              {label}
            </div>
          )}
          <div
            style={{
              color: t.text,
              fontWeight: t.displayWeight,
              fontSize: 108,
              lineHeight: 1.0,
              textShadow: "0 6px 30px rgba(0,0,0,0.8)",
            }}
          >
            <Emphasized text={text} t={t} />
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
