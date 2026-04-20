# BURNLIST

Paste a Spotify URL, get numbered 320kbps MP3s with full ID3 metadata, and burn them straight to an Audio CD that plays in any CD player ever made.

Runs locally on your Mac. No cloud, no API keys, no Spotify account.

![burnlist](https://img.shields.io/badge/platform-macOS-black) ![license](https://img.shields.io/badge/license-MIT-green)

---

## What it does

1. You paste a public Spotify track, album, or playlist URL
2. It scrapes the public Spotify embed page to pull the tracklist and artwork
3. For each track, it searches YouTube and downloads the best audio match via `yt-dlp`
4. Converts to 320kbps MP3, embeds full ID3 tags (track number, artist, title, album, artwork)
5. Offers you a ZIP, a folder you can burn as a Data CD from Finder, or a one-click Audio CD burn via `drutil`

---

## Requirements

- macOS (only tested on Apple Silicon, should work on Intel)
- Python 3.10+
- Homebrew

```bash
brew install ffmpeg
pip3 install yt-dlp mutagen
```

(If `pip3` complains about "externally-managed environment", add `--break-system-packages` or use a virtualenv.)

For the Audio CD burn step: an attached optical drive (internal SuperDrive or USB CD burner) and blank **CD-R** media.

---

## Run

```bash
git clone https://github.com/eightclip/burnlist.git
cd burnlist
python3 server.py
```

Open `http://localhost:7474` in your browser.

---

## Usage

1. Paste any public Spotify URL:
   - `https://open.spotify.com/track/...`
   - `https://open.spotify.com/album/...`
   - `https://open.spotify.com/playlist/...`
2. Hit **Burn This**
3. Watch tracks resolve live in the queue
4. When the green **Download ZIP** button appears, choose:
   - **Download ZIP** – grab a ZIP of numbered MP3s
   - **Reveal Folder** – open the folder in Finder (right-click the folder → *Burn to Disc* for a Data/MP3 CD)
   - **Burn Audio CD** – pop in a blank CD-R, click, and you get an Audio CD playable in any CD player

---

## Output

Files go to `~/burnlist_output/`:

```
~/burnlist_output/
  Album Name.zip
  <job-id>/
    01 - Artist - Title.mp3
    02 - Artist - Title.mp3
    ...
    aiff/                    (only if you burned a CD)
      01 - Artist - Title.aiff
      ...
```

---

## Troubleshooting

**`yt-dlp` / `ffmpeg` not found**
Make sure they're on your `PATH`. You can override detection:
```bash
YTDLP_BIN=/path/to/yt-dlp FFMPEG_BIN=/path/to/ffmpeg python3 server.py
```

**Track failed to download**
`yt-dlp` couldn't find a clean YouTube match. The ZIP still includes everything else. Sometimes a retry works.

**Burn failed: drive selection**
Your Mac has an "Unsupported" optical drive according to `drutil`. BURNLIST already passes `-drive 1`. If you have multiple drives, adjust the code in `_burn_job`.

**Burn failed: wrong media**
You need a blank **CD-R**. DVD-R, CD-RW, and already-burned discs won't work.

**Spotify page scrape returns nothing**
Spotify occasionally redesigns their embed page. Open an issue, it's usually a 10-line fix.

---

## How the scrape works

BURNLIST fetches `https://open.spotify.com/embed/<type>/<id>`, pulls the `<script id="__NEXT_DATA__">` JSON blob, and walks it for `trackList`. No Spotify API, no auth, no Premium. Artwork comes from the same blob.

This is public page data. If Spotify changes their markup, the scraper will need updating.

---

## Project structure

```
burnlist/
  server.py       Python HTTP server + job runner
  index.html      Single-page UI (vanilla JS, no framework)
  README.md       You are here
  LICENSE         MIT
  DISCLAIMER.md   Legal stuff
```

---

## Disclaimer

This tool is for personal use only. See [DISCLAIMER.md](DISCLAIMER.md). By using BURNLIST you accept full responsibility for how you use it.

---

## License

MIT. See [LICENSE](LICENSE).
