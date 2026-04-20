#!/usr/bin/env python3
# BURNLIST server - Spotify to CD-ready MP3 downloader
# Scrapes public Spotify embed pages for tracklist, uses yt-dlp for audio
# Run: python3 server.py

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PORT = 7474
OUTPUT_DIR = Path.home() / "burnlist_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def _find_bin(name, env_var, fallbacks):
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return override
    found = shutil.which(name)
    if found:
        return found
    for p in fallbacks:
        if Path(p).exists():
            return p
    return name


YTDLP = _find_bin(
    'yt-dlp', 'YTDLP_BIN',
    ['/opt/homebrew/bin/yt-dlp', '/usr/local/bin/yt-dlp']
)
FFMPEG = _find_bin(
    'ffmpeg', 'FFMPEG_BIN',
    ['/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg']
)
DRUTIL = '/usr/bin/drutil'
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
CD_CAPACITY_SEC = 80 * 60

jobs = {}


def _sanitize(name):
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()


def _url_type(url):
    if '/playlist/' in url:
        return 'playlist'
    if '/album/' in url:
        return 'album'
    return 'track'


def _extract_id(url):
    m = re.search(r'spotify\.com/(?:embed/)?(?:album|playlist|track)/([A-Za-z0-9]+)', url)
    return m.group(1) if m else None


def _fetch_spotify_metadata(url):
    spot_id = _extract_id(url)
    if not spot_id:
        raise ValueError("Invalid Spotify URL")

    kind = _url_type(url)
    embed_url = f"https://open.spotify.com/embed/{kind}/{spot_id}"
    req = urllib.request.Request(embed_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode('utf-8', errors='ignore')

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        raise RuntimeError("Could not parse Spotify page")

    data = json.loads(m.group(1))
    entity = data['props']['pageProps']['state']['data']['entity']

    name = entity.get('title', 'Unknown')
    cover_url = ''
    for img in entity.get('visualIdentity', {}).get('image', []):
        if img.get('url'):
            cover_url = img['url']

    tracks = []
    if kind == 'track':
        tracks.append({
            'title': entity.get('title', 'Unknown'),
            'artist': entity.get('subtitle', 'Unknown'),
        })
    else:
        for t in entity.get('trackList', []):
            tracks.append({
                'title': t.get('title', 'Unknown'),
                'artist': t.get('subtitle', 'Unknown'),
            })

    return {'name': name, 'cover_url': cover_url, 'tracks': tracks, 'kind': kind}


def _download_cover(url):
    if not url:
        return b''
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return b''


def _tag_mp3(path, track_num, total, artist, title, album, cover_bytes):
    from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TRCK, APIC
    from mutagen.mp3 import MP3

    audio = MP3(str(path), ID3=ID3)
    try:
        audio.add_tags()
    except Exception:
        pass
    if audio.tags is None:
        audio.tags = ID3()

    audio.tags.delall('TIT2')
    audio.tags.delall('TPE1')
    audio.tags.delall('TALB')
    audio.tags.delall('TRCK')
    audio.tags.delall('APIC')

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    audio.tags.add(TRCK(encoding=3, text=f"{track_num}/{total}"))
    if cover_bytes:
        audio.tags.add(APIC(
            encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_bytes
        ))
    audio.save(v2_version=3)


def _download_track(job_id, track_num, total, artist, title, album, cover_bytes, out_dir):
    job = jobs[job_id]
    tk = job['tracks'][str(track_num)]
    tk['status'] = 'downloading'

    label = f"{track_num:02d} - {_sanitize(artist)} - {_sanitize(title)}"
    out_path = out_dir / f"{label}.mp3"
    out_template = str(out_dir / f"{label}.%(ext)s")
    query = f"ytsearch1:{artist} {title} audio"

    cmd = [
        YTDLP,
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-warnings",
        "--quiet",
        "--output", out_template,
        query,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        tk['status'] = 'error'
        return
    except FileNotFoundError:
        tk['status'] = 'error'
        return

    if result.returncode != 0 or not out_path.exists():
        tk['status'] = 'error'
        return

    try:
        _tag_mp3(out_path, track_num, total, artist, title, album, cover_bytes)
    except Exception:
        pass

    tk['status'] = 'done'


def _run_job(job_id, spotify_url):
    job = jobs[job_id]
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(exist_ok=True)

    job['phase'] = 'fetching'

    try:
        data = _fetch_spotify_metadata(spotify_url)
    except Exception as e:
        job['phase'] = 'error'
        job['error'] = f'Could not read Spotify page: {e}'
        return

    if not data['tracks']:
        job['phase'] = 'error'
        job['error'] = 'No tracks found for this URL'
        return

    cover_bytes = _download_cover(data['cover_url'])

    job['album_name'] = data['name']
    job['artwork_url'] = data['cover_url']
    job['total'] = len(data['tracks'])
    job['tracks'] = {}
    for i, t in enumerate(data['tracks'], 1):
        job['tracks'][str(i)] = {
            'title': t['title'],
            'artist': t['artist'],
            'status': 'queued',
        }

    job['phase'] = 'downloading'
    total = len(data['tracks'])

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [
            ex.submit(
                _download_track,
                job_id, i, total, t['artist'], t['title'],
                data['name'], cover_bytes, out_dir,
            )
            for i, t in enumerate(data['tracks'], 1)
        ]
        for f in futures:
            f.result()

    for t in job['tracks'].values():
        if t['status'] in ('queued', 'downloading'):
            t['status'] = 'error'

    job['phase'] = 'zipping'
    mp3s = sorted(out_dir.glob('*.mp3'))
    if not mp3s:
        job['phase'] = 'error'
        job['error'] = 'No MP3 files were downloaded'
        return

    safe_name = _sanitize(data['name']) or f'burnlist_{job_id}'
    zip_path = OUTPUT_DIR / f'{safe_name}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for mp3 in mp3s:
            zf.write(mp3, mp3.name)

    job['phase'] = 'ready'
    job['zip'] = str(zip_path)
    job['zip_name'] = zip_path.name
    job['out_dir'] = str(out_dir)

    try:
        job['duration_sec'] = _mp3_duration_total(mp3s)
    except Exception:
        job['duration_sec'] = 0


def _mp3_duration_total(mp3_paths):
    from mutagen.mp3 import MP3
    total = 0.0
    for p in mp3_paths:
        try:
            total += MP3(str(p)).info.length
        except Exception:
            pass
    return int(total)


def _check_burn_media():
    try:
        result = subprocess.run(
            [DRUTIL, '-drive', '1', 'status'],
            capture_output=True, text=True, timeout=10
        )
    except Exception as e:
        return f'Could not read drive status: {e}'

    out = result.stdout + result.stderr
    if 'no media' in out.lower() or 'empty' in out.lower() and 'blank' not in out.lower():
        return 'No disc inserted. Insert a blank CD-R and try again.'

    type_match = re.search(r'Type:\s*(\S+)', out)
    disc_type = type_match.group(1) if type_match else ''

    if disc_type and 'CD' not in disc_type.upper():
        return f'Wrong media type ({disc_type}). Audio CD requires a blank CD-R.'

    if 'blank' not in out.lower() and 'appendable' not in out.lower():
        return 'Disc is not blank or writable.'

    return None


def _mp3_to_aiff(mp3_path, aiff_path):
    subprocess.run(
        [FFMPEG, '-y', '-i', str(mp3_path),
         '-map_metadata', '-1',
         '-ar', '44100', '-ac', '2', '-sample_fmt', 's16',
         str(aiff_path)],
        capture_output=True, check=True, timeout=120
    )


def _burn_job(job_id):
    job = jobs[job_id]
    out_dir = Path(job['out_dir'])
    mp3s = sorted(out_dir.glob('*.mp3'))

    if not mp3s:
        job['burn_phase'] = 'error'
        job['burn_error'] = 'No MP3s to burn'
        return

    aiff_dir = out_dir / 'aiff'
    aiff_dir.mkdir(exist_ok=True)
    aiff_paths = []

    job['burn_phase'] = 'converting'
    job['burn_converted'] = 0
    job['burn_total'] = len(mp3s)

    for i, mp3 in enumerate(mp3s, 1):
        aiff = aiff_dir / f"{mp3.stem}.aiff"
        try:
            _mp3_to_aiff(mp3, aiff)
            aiff_paths.append(aiff)
        except subprocess.CalledProcessError:
            continue
        job['burn_converted'] = i

    if not aiff_paths:
        job['burn_phase'] = 'error'
        job['burn_error'] = 'Audio conversion failed'
        return

    drive_check = _check_burn_media()
    if drive_check:
        job['burn_phase'] = 'error'
        job['burn_error'] = drive_check
        return

    job['burn_phase'] = 'burning'
    job['burn_progress'] = 0

    cmd = [DRUTIL, '-drive', '1', 'burn', '-noverify', '-audio', str(aiff_dir)]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
    except FileNotFoundError:
        job['burn_phase'] = 'error'
        job['burn_error'] = 'drutil not found'
        return

    percent_re = re.compile(r'(\d{1,3})\s*%')

    for raw in proc.stdout:
        line = raw.strip()
        m = percent_re.search(line)
        if m:
            try:
                job['burn_progress'] = int(m.group(1))
            except ValueError:
                pass
        if line:
            job['burn_status'] = line[-200:]

    proc.wait()

    if proc.returncode == 0:
        job['burn_phase'] = 'done'
        job['burn_progress'] = 100
    else:
        job['burn_phase'] = 'error'
        job['burn_error'] = job.get('burn_status') or f'drutil exit {proc.returncode}'


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/':
            self._file('index.html', 'text/html')

        elif parsed.path == '/status':
            job_id = params.get('job', [None])[0]
            if job_id and job_id in jobs:
                data = {k: v for k, v in jobs[job_id].items() if not k.startswith('_')}
                self._json(data)
            else:
                self._json({'error': 'not found'}, 404)

        elif parsed.path == '/download':
            job_id = params.get('job', [None])[0]
            if job_id and job_id in jobs and jobs[job_id].get('zip'):
                zip_path = jobs[job_id]['zip']
                zip_name = jobs[job_id]['zip_name']
                try:
                    data = Path(zip_path).read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/zip')
                    self.send_header('Content-Disposition', f'attachment; filename="{zip_name}"')
                    self.send_header('Content-Length', len(data))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception:
                    self._json({'error': 'zip unavailable'}, 500)
            else:
                self._json({'error': 'not ready'}, 404)

        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/start':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length))
            except Exception:
                self._json({'error': 'bad request'}, 400)
                return

            url = (body.get('url') or '').strip()
            if not url or 'open.spotify.com' not in url:
                self._json({'error': 'invalid Spotify URL'}, 400)
                return

            job_id = uuid.uuid4().hex[:8]
            jobs[job_id] = {
                'phase': 'queued',
                'album_name': None,
                'artwork_url': None,
                'total': 0,
                'tracks': {},
                'error': None,
                'zip': None,
                'zip_name': None,
                'duration_sec': 0,
                'burn_phase': 'idle',
            }

            threading.Thread(target=_run_job, args=(job_id, url), daemon=True).start()
            self._json({'job_id': job_id})

        elif parsed.path == '/burn':
            job_id = params.get('job', [None])[0]
            if not job_id or job_id not in jobs:
                self._json({'error': 'job not found'}, 404)
                return
            job = jobs[job_id]
            if job.get('phase') != 'ready':
                self._json({'error': 'job not ready'}, 400)
                return
            if job.get('burn_phase') in ('converting', 'burning'):
                self._json({'error': 'burn already in progress'}, 400)
                return

            job['burn_phase'] = 'starting'
            job['burn_error'] = None
            job['burn_progress'] = 0
            job['burn_status'] = ''
            threading.Thread(target=_burn_job, args=(job_id,), daemon=True).start()
            self._json({'ok': True})

        elif parsed.path == '/reveal':
            job_id = params.get('job', [None])[0]
            if not job_id or job_id not in jobs:
                self._json({'error': 'job not found'}, 404)
                return
            out_dir = jobs[job_id].get('out_dir')
            if out_dir and Path(out_dir).exists():
                subprocess.Popen(['open', out_dir])
                self._json({'ok': True})
            else:
                self._json({'error': 'folder missing'}, 404)

        else:
            self._json({'error': 'not found'}, 404)

    def _file(self, name, mime):
        path = Path(__file__).parent / name
        if path.exists():
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json({'error': 'not found'}, 404)


def _preflight():
    missing = []
    if not shutil.which(YTDLP) and not Path(YTDLP).exists():
        missing.append('yt-dlp  (install: pip3 install yt-dlp)')
    if not shutil.which(FFMPEG) and not Path(FFMPEG).exists():
        missing.append('ffmpeg  (install: brew install ffmpeg)')
    try:
        import mutagen  # noqa: F401
    except ImportError:
        missing.append('mutagen (install: pip3 install mutagen)')
    return missing


if __name__ == '__main__':
    missing = _preflight()
    if missing:
        print('Missing required tools:')
        for m in missing:
            print(f'  - {m}')
        sys.exit(1)
    print(f'BURNLIST running at http://localhost:{PORT}')
    print(f'Output: {OUTPUT_DIR}')
    server = http.server.ThreadingHTTPServer(('', PORT), Handler)
    server.serve_forever()
