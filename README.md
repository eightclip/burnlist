# BURNLIST

Paste a Spotify URL, get a ZIP of numbered 320kbps MP3s ready to burn to CD.

Runs locally at `http://localhost:7474`. No cloud, no accounts beyond Spotify itself.

---

## Prerequisites

```bash
# ffmpeg
brew install ffmpeg

# spotdl
pip3 install spotdl
```

Python 3 is built into macOS.

---

## Run

```bash
cd ~/Documents/Claude/burnlist
python3 server.py
```

Open `http://localhost:7474` in your browser.

---

## How it works

1. Paste any Spotify URL (track, album, or playlist)
2. Hit **Burn This**
3. spotdl fetches the tracklist from Spotify, finds audio on YouTube, downloads and converts to 320kbps MP3 with full ID3 tags
4. Download the ZIP when complete

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
```

Each MP3 includes: track number, artist, title, album name, album artwork.

---

## Troubleshooting

**spotdl not found** - run `pip3 install spotdl`

**ffmpeg not found** - run `brew install ffmpeg`

**Track failed to download** - spotdl couldn't find a YouTube match. The ZIP still includes all other tracks.

**Spotify rate limiting** - wait a few minutes and retry.
