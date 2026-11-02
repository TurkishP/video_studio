---
name: make-short
description: Turn an idea into a researched, captioned video with local free tools, either a 9:16 short (30-60 s) or a 16:9 long video with chapters and a thumbnail. Run only when the user types /make-short <idea>.
disable-model-invocation: true
---

# /make-short

Turn the idea in the arguments into a finished vertical short. Work from the
`shorts-studio` project root. Each step writes its file before the next starts,
so a half-finished short can be resumed. Worked examples:
`shorts/octopus-three-hearts/` (bold look, photos) and `shorts/christian-love/`
(museum look, paintings with 3D motion).

```
PY="tools/.venv/Scripts/python.exe -I -X utf8"            # -X utf8: the console is cp949
DF="tools/.venv-depthflow/Scripts/python.exe -I -X utf8"
S=shorts/<slug>          # short kebab-case slug for the idea
```

Pick the look in `beats.json` → `"theme"`:
- `bold`: heavy yellow captions, for science/facts with photos or stock clips.
- `museum`: serif cream/gold captions, warm grade, film grain, for philosophy,
  faith and classic literature told through public-domain paintings.

Pick the format → `"format"` (ask the user if the idea doesn't say):
- `short` (default): 1080x1920, 45-55 s, captions mid-screen.
- `long`: 1920x1080 essay, captions as a lower third (`"captions": false` turns
  them off), chapter cards and a thumbnail. Long videos are where the income is
  (Shorts pay ~3-14% as much per view), so for a series make one long video per
  topic and cut 3-5 Shorts from it. Worked example: `shorts/christian-love-long/`.

For a series, set `"voice_clone": "narrator"` so every video has the same voice
(`tools/voices/narrator.wav` + `.txt`, cut from the Christian love pilot).

## 1. Brief → `$S/brief.md` (stop for approval)

Angle, one-sentence thesis, audience, and what this adds beyond the Shorts that
already exist on the topic. Show it to the user and wait for a yes or changes.

## 2. Research → `$S/research.md`

Use the Firecrawl connector. Table of claim → source URL. Prefer primary or
reputable sources (journals, museums, agencies, major outlets); note anything
you left out because it was weakly sourced. Every claim in the script must be
in this table.

## 3. Script → `$S/beats.json`

Rules (YouTube demonetizes templated content and narration of text the creator
didn't write):
- Original wording and a clear thesis. Never paste or lightly reword source sentences.
- 600-750 characters of narration total (~45-55 s). Hook in the first beat (1-3 s):
  contrarian or surprising ("The New Testament never uses...").
- 6-10 beats, one or two sentences each. End with a line that loops back to the hook.
- Talk like a person, not a textbook: "you", contrasts, one relatable image per
  idea ("your ride-or-die friend", "the 'did you eat?' text from mom").
- Never let the picture sit still: 2-3 shots per image beat (wide, then close-ups
  on faces/hands via `shots`), a `statement` card for each punchline, and
  varied `transition`s. Change picture every ~2-3 s.
- Wrap 1-2 key words per beat in `*asterisks*`: they render gold/italic and
  give the picture a small punch.

Long videos, in addition:
- 12-20 min for income (roughly 1,800-2,800 words), 3-6 chapters. Mark the beat
  that opens each chapter with `"chapter": "<title>"`; open every chapter with a
  question. YouTube shows chapters only with 3+ chapters of 10 s or more.
- Original analysis throughout. YouTube won't monetize "readings of other
  materials you did not originally create": never narrate the novel itself, and
  quote at most a line or two.
- Add `"thumbnail": {"src": "assets/x.jpg", "focus": [x, y], "zoom": 1.5,
  "text": "2-5 *big* words", "label": "Author · Title"}`.

```json
{
  "title": "Why an octopus has three hearts",
  "theme": "bold",
  "voice": "af_heart",
  "speed": 1.05,
  "music": null,
  "beats": [
    { "text": "...", "visual": { "type": "image", "src": "assets/01.jpg" }, "kicker": "3 hearts" },
    { "text": "...", "visual": { "type": "stat", "value": "2", "label": "gill hearts" } },
    { "text": "...", "visual": { "type": "video", "src": "assets/02.mp4" } },
    { "text": "... *agapē*.", "say": "... ahgahpay.",
      "visual": { "type": "image", "src": "assets/03.jpg", "parallax": true,
                  "shots": [{}, { "focus": [0.52, 0.3], "zoom": 2.2 }] },
      "headline": "The *missing* word", "cite": "Luke 15", "transition": "zoom" },
    { "text": "Romance asks: what do *I* feel?", "visual": { "type": "statement", "bg": "assets/03.jpg" },
      "transition": "flash" }
  ],
  "sources": ["Smithsonian Magazine", "Natural History Museum"]
}
```

- `kicker` (optional): 1-3 word label shown at the top of that beat. Avoid
  macrons/accents in kickers and stat labels (they are uppercased; Ē renders badly).
- `say` (optional): respelling for the voice only; captions keep `text`. Check
  unusual words (foreign terms, names) before voicing:
  `$PY -c "from kokoro_onnx.tokenizer import Tokenizer; print(Tokenizer().phonemize('agape', 'en-us'))"`
  e.g. agape → `ahgahpay`, storge → `storgay`.
- `parallax` (optional, images): the beat opens on a slow 3D camera move of the
  painting (step 5); `visual.focus` nudges that clip's crop.
- `shots` (optional, images): the beat cuts between shots, on word onsets.
  `{}` = whole image (or the 3D clip if `parallax`); `{"focus": [x, y], "zoom": z}`
  = close-up centred on that point (0-1 image coordinates). Find points by
  overlaying a grid: `ffmpeg -i img.jpg -vf "scale=-2:620,drawgrid=w=iw/10:h=ih/10:t=1:c=white@0.45" grid.jpg`.
  Keep zoom ≤ 1.5 for images under ~2000 px tall.
- `blender` visual: a real 3D shot rendered from a scene script,
  `{"type": "blender", "scene": "scenes/desk.py"}` (optional `"engine": "cycles"`
  for realistic light, ~5x slower). Use it where the camera should travel
  through a space or show how something works; see step 4.
- `statement` visual: full-screen punchline; the beat's words appear as spoken
  over a blurred `bg` image. Captions hide during it.
- `headline` (optional): big serif text at the top (hooks, or `*ἀγάπη*`).
- `cite` (optional): small italic source line above the captions (scripture refs).
- `transition` (optional): `cut`, `fade` (default), `zoom` (punch-in, with
  whoosh), `flash` (white flash, with whoosh). Mix them.
- `stat` values: up to 5 characters render huge; longer ones (e.g. `I → you`)
  shrink to fit. Greek works (the museum font has it): `ἀγάπη`.
- `music` (optional): file in `$S`, e.g. `music.mp3`; `musicVolume` defaults to
  0.12 (0.14 sits ~18 dB under the voice). Public-domain classical recordings
  on Wikimedia Commons work (search with `filetype:audio`, keep only "Public
  domain"/"CC0"); trim with `ffmpeg -t 75 -af "afade=t=in:d=1.5,loudnorm=I=-20"`
  and log it in provenance.csv.
- Voice: `voice_clone` (a name in `tools/voices/`, the same narrator every time;
  best for a series and required for long videos), or `voice_design`
  (plain-English description) + `seed` for a one-off Qwen3-TTS voice, or
  `voice`/`speed` for Kokoro (`af_heart`, `am_michael`, `bf_emma`, ...).
  `"language": "Korean"` voices Korean with Qwen.

## 4. Visuals → `$S/assets/` + `$S/provenance.csv`

- Paintings (museum look): public-domain works from the Art Institute of
  Chicago, The Met and Wikimedia Commons. `get` logs the credit for you.
  ```
  $PY tools/art.py search "Rembrandt prodigal son" --source commons -n 4 --sheet $S/qa/cands.jpg
  $PY tools/art.py get "<key from search>" $S/assets/prodigal.jpg
  ```
  Read the sheet before choosing. Prefer portrait-shaped works; landscape ones
  are cropped to the middle. Check size with ffprobe and replace anything under
  ~1300 px tall (Web Gallery of Art "WGA" copies are often small; "Google Art
  Project" copies are large). Commons rate-limits bursts; the script retries.
- Bible quotes: World English Bible (public domain), e.g.
  `curl -s "https://bible-api.com/romans%205:8?translation=web"`; KJV also works.
  Avoid ESV/NIV. Korean: 개역한글 (public domain since 2012), not 개역개정.
- Photos: Unsplash connector. `search_photos` (orientation portrait, plus none),
  then `download_asset` for each pick (records the download, as Unsplash's terms
  require), then `curl -sSLf -o $S/assets/NN-name.jpg "<url>&w=1440"`.
- Video clips: Pexels, only if `PEXELS_API_KEY` is set:
  `curl -s -H "Authorization: $PEXELS_API_KEY" "https://api.pexels.com/videos/search?query=<q>&orientation=portrait&per_page=5"`,
  pick a `video_files` entry about 1080 wide, download it to `assets/`.
- 3D scenes (Blender 5.2, portable in `tools/blender-5.2/`): CC0 models and HDRIs
  from Poly Haven, shared by every video in `tools/blender-assets/`.
  ```
  $PY tools/polyhaven.py search "oil lamp" -n 6 --sheet $S/qa/models.jpg   # --type hdris for lighting
  $PY tools/polyhaven.py get vintage_oil_lamp --log $S
  ```
  Write `$S/scenes/<name>.py` with `build(scene)` using `tools/blender/lib.py`
  (model, hdri, light, flicker, haze, camera, key). Worked example:
  `shorts/blender-test/scenes/desk.py`. Keep the camera moving the whole shot.
  Check a shot as stills before rendering the clip (first frame takes ~35 s while
  shaders compile, later ones ~5 s):
  `$PY tools/blender_render.py $S/scenes/desk.py $S/qa/f1.png --format long --still 1`
- Look at every asset before using it (tile thumbnails with ffmpeg and read the
  image). Reject anything off-topic, misleading, gory or showing identifiable people.
- Log every asset in `provenance.csv`: `file,source_url,creator,license,retrieved`.

## 5. Voice, captions, props

```
TTS="tools/.venv-tts/Scripts/python.exe -I -X utf8"
$TTS tools/tts_qwen.py $S    # -> voice.wav (Qwen3-TTS on the GPU, ~3 s per 1 s of audio)
#   or: $PY tools/tts.py $S  # -> voice.wav + timings.json (Kokoro, seconds; flatter voice)
$PY tools/captions.py $S     # -> captions.json (+ timings.json after Qwen)
$DF tools/parallax.py $S     # -> assets/parallax-NN.mp4 for "parallax" beats (GPU, ~8 s each)
$PY tools/blender_render.py $S  # -> assets/blender-NN.mp4 for "blender" beats (GPU)
$PY tools/build_props.py $S  # -> props.json (+ chapters.txt, thumb.json for long videos)
```

Rerun `parallax.py` and `blender_render.py` whenever the voice timing changes (they size each clip to its beat).

Shorts: aim for 45-55 s; if it runs long, cut words from `beats.json` and rerun.
`captions.py` prints how many words it had to interpolate; more than a few means
the voice mispronounced something, so rephrase that beat.

## 6. Render

```
npx remotion render Short $S/out/raw.mp4 --props=$S/props.json --public-dir=$S --log=error
ffmpeg -v error -y -i $S/out/raw.mp4 -af loudnorm=I=-14:TP=-1.5:LRA=11 -c:v copy -c:a aac -b:a 192k $S/out/short.mp4
# long videos: the size follows props.format; also render the thumbnail
npx remotion still Thumbnail $S/out/thumbnail.png --props=$S/thumb.json --public-dir=$S --log=error
```

The template is `src/Short.tsx` (30 fps; 1080x1920 or 1920x1080 from `format`)
and `src/Thumbnail.tsx` (1280x720). For a live preview while changing it:
`npx remotion studio --props=$S/props.json --public-dir=$S`.

## 7. QA → `$S/qa/`

- Extract frames at ~0, 25, 50, 75, 100% and one per scene with
  `ffmpeg -ss <t> -i $S/out/short.mp4 -frames:v 1 -vf scale=270:-1 $S/qa/tN.png`,
  tile them with `hstack`, and read the sheet: captions legible and spelled right,
  labels clear of the top 200 px / bottom 25% / right edge, no bad crops.
- `ffprobe` the output: 1080x1920 (or 1920x1080), 30 fps, audio present, duration as planned.
- Long videos: also read each chapter card frame and `out/thumbnail.png`.
- Re-check each claim in the script against `research.md`.
- Fix and re-render until clean.

## 8. Hand-off (stop; never publish without the user's explicit yes)

Show the user `$S/out/short.mp4` and give them:
- Title (under 60 characters) and description with the source URLs and photo credits from `provenance.csv`;
  for long videos, paste `chapters.txt` into the description and attach `out/thumbnail.png`.
- AI-disclosure call: YouTube's "altered or synthetic content" flag is needed only
  for realistic synthetic footage, people or AI music. Photos, stat cards and a TTS
  narrator over them usually don't need it; say which applies and why.
- Upload is manual for now (YouTube Studio, TikTok and Instagram apps).
