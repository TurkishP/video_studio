---
name: sermon-clip
description: Cut a recorded sermon on YouTube into 30 s - 2 min vertical clips with a title bar, a crop that follows the preacher and Korean subtitles. Run only when the user types /sermon-clip <YouTube URL>.
disable-model-invocation: true
---

# /sermon-clip

Turn the sermon in the arguments into a handful of vertical clips. Work from
the `shorts-studio` project root. Worked example: `sermons/gospel-again-01/`
(그사랑교회, 고상섭 목사, Gospel Again 1).

```
PY="tools/.venv/Scripts/python.exe -I -X utf8"     # -X utf8: the console is cp949
S=sermons/<slug>                                   # e.g. gospel-again-02
```

Only clip sermons the user has the church's permission to use. Every clip's
description credits the preacher and church and links the full sermon.

## 1. Download → `$S/audio.mp4`, `$S/video.mp4`

```
YT="$PY -m yt_dlp --js-runtimes node -N 4 --fragment-retries 20 --no-playlist --no-progress"
$YT -F "<url>"                                       # list formats
$YT -f "<ko audio id>" -o "$S/audio.%(ext)s" "<url>"
$YT -f "<720p video id>" -o "$S/video.%(ext)s" "<url>"   # run both in the background
```

- Pick the audio track marked `[ko] ... original`: uploads now often carry an
  auto-dubbed English track, and it can be the default.
- Use the m3u8 (HLS) formats (audio 234/233, video 232). The direct https
  ones download as a 302 page on this machine. HLS fragments sometimes 403;
  the retries get through.
- yt-dlp needs `yt-dlp-ejs` (installed) and node to solve YouTube's challenge.

## 2. Transcribe → `$S/words.json`, `$S/transcript.txt`

```
$PY tools/transcribe.py $S ko "고상섭 그사랑교회 팀 켈러 ..."   # names and terms to spell right
```

large-v3-turbo on the GPU, a few minutes per hour of audio. It first writes
`audio.wav`: YouTube's HLS audio carries timestamps that run ~0.09% ahead of
its samples (2.7 s by minute 50), so anything that seeks `audio.mp4` lands
early. Cut and time everything from `audio.wav` (build_clip.py does).

## 3. Pick clips → `$S/clips.json` (stop for approval)

Read `transcript.txt` and choose 3-8 passages. A good clip:
- makes one complete point and can be understood with no context;
- opens on a hook in the first sentence (a question, a surprising claim, a
  story's first line); start mid-paragraph if that's where the hook is;
- ends on the punchline, not on "그래서 오늘...";
- runs 30-90 s (up to 2 min for a story that earns it).
Stories, everyday examples and memorable lines beat exposition.

Find exact times in `words.json` (start a clip at the first word's start
minus ~0.15 s, end at the last word's end plus ~0.3 s). `cut` removes
asides, repeated phrases and long pauses inside a clip. Titles: two lines,
the second short and strong (it renders big and gold), 4-12 characters each.

```json
{"credit": "고상섭 목사 · 그사랑교회", "bar": "#2b1418",
 "clips": [{"id": "love-freedom", "start": 1063.2, "end": 1190.4,
            "cut": [[1101.0, 1104.5]], "title": ["사랑하면", "자유를 잃는다"]}]}
```

Add the 3 s ending card with the church logo (`sermons/brand/logo.png`, and
`logo-light.png` with cream text for dark backgrounds) at the top level of
`clips.json`; a clip can override it with its own `"outro"`:

```json
"outro": {"style": "bar", "logo": "../brand/logo.png", "logoLight": "../brand/logo-light.png",
          "lines": ["주일설교 · 고상섭 목사", "전체 설교는 그사랑교회 유튜브에서"]}
```

Styles: `bar` (the title bar grows to fill the screen), `card` (cream card),
`blur` (last frame frozen, blurred and darkened, title bar kept).

Show the user the list (title, time range, length, one line on why) and wait.

## 4. Build each clip → `$S/clips/<id>/`

```
$PY tools/build_clip.py $S <id>
```

First run: snaps start, end and cut edges to the quietest moment nearby
(whisper's word edges touch), cuts `source.mp4` (upscaled to 1440p), tracks
the preacher (`track.json`) and drafts `subs.json` with machine line breaks.
Replace the draft with your own lines, in spoken order and without times;
the script matches them to the spoken words for timing:

```json
[{"text": "누군가를 사랑하면\n*자유*를 잃어버립니다", "en": "When you love someone, you lose your freedom."},
 {"text": "\"나는 내 인생이고\n너는 네 인생인데", "en": "\"My life is mine, your life is yours,", "hand": true}]
```

- fix transcription errors (names, Bible books, English words), but keep the
  spoken words: lines that don't match the audio get no timing;
- one phrase per entry, `\n` between its two lines, at most ~12 syllables a line;
- mark 1-2 key words with `*stars*` (gold); `"hand": true` for quoted
  sayings and punchlines (handwritten font); `"en"` is optional.
Rerun to write `props.json`. After changing a clip's start, end or cuts,
delete `source.mp4` and `track.json` first.

## 5. Render

```
C=$S/clips/<id>
npx remotion render SermonClip $C/raw.mp4 --props=$C/props.json --public-dir=$C --timeout=90000 --log=error
$PY tools/loudnorm.py $C/raw.mp4 $C/clip.mp4    # two-pass; one-pass lands at -15 to -17 LUFS on sermons
```

About 2.5 s of render time per second of clip.

Template: `src/SermonClip.tsx` (1080x1920, 30 fps). The window follows the
preacher and alternates zoom 1.0 / 1.18 about every 9 s and at every cut.

## 6. QA

Tile frames (`ffmpeg -ss <t> -i $C/clip.mp4 -frames:v 1 -vf scale=270:-1 ...`,
`hstack`) at the start, each cut, and the end, and read the sheet: the
preacher in frame (not cut off at the edge), subtitles readable and in sync,
title clear. Check `track.json` found the speaker in most samples.

Then check subtitle sync against the actual audio:

```
$PY tools/check_sync.py $S/clips/<id>      # median offset should be about -0.15 s, few lines beyond ±0.3 s
```

## 7. Hand-off (stop; never publish without the user's explicit yes)

For each clip give: title (under 40 characters, Korean), description with
`원본 설교: <title> | <preacher> | <church>`, the sermon link with `&t=<seconds>`,
and 3-5 hashtags. Upload is manual.
