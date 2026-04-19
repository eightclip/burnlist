#!/usr/bin/env python3
# BURNLIST server - Spotify to CD-ready MP3 downloader
# Run: python3 server.py

import http.server
import json
import os
import re
import subprocess
import threading
import uuid
import zipfile
from pathlib import Path
import urllib.parse

PORT = 7474
OUTPUT_DIR = Path.home() / "burnlist_output"
OUTPUT_DIR.mkdir(exist_ok=True)

jobs = {}

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFABCDJsr]')


def _clean(line):
    return ANSI_RE.sub('', line).strip()


def _sanitize(name):
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()


def _url_type(url):
    if '/playlist/' in url:
        return 'playlist'
    if '/album/' in url:
        return 'album'
    return 'track'


def _run_job(job_id, spotify_url):
    job = jobs[job_id]
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(exist_ok=True)
    save_file = out_dir / 'tracks.spotdl'

    # Phase: fetch tracklist metadata
    job['phase'] = 'fetching'

    try:
        r = subprocess.run(
            ['spotdl', 'save', spotify_url, '--save-file', str(save_file)],
            capture_output=True, text=True, timeout=90
        )
    except FileNotFoundError:
        job['phase'] = 'error'
        job['error'] = 'spotdl not found - run: pip3 install spotdl'
        return
    except subprocess.TimeoutExpired:
        job['phase'] = 'error'
        job['error'] = 'Timed out fetching tracklist from Spotify'
        return

    if not save_file.exists() or save_file.stat().st_size == 0:
        err = (r.stderr or r.stdout or '').strip()
        job['phase'] = 'error'
        job['error'] = err[-400:] if err else 'Failed to fetch tracklist'
        return

    try:
        tracks_data = json.loads(save_file.read_text())
    except Exception as e:
        job['phase'] = 'error'
        job['error'] = f'Could not parse tracklist: {e}'
        return

    if not tracks_data:
        job['phase'] = 'error'
        job['error'] = 'No tracks found for this URL'
        return

    # Populate job from Spotify metadata
    first = tracks_data[0]
    list_name = first.get('list_name') or first.get('album_name') or 'Unknown'
    artwork_url = first.get('cover_url') or ''

    job['album_name'] = list_name
    job['artwork_url'] = artwork_url
    job['total'] = len(tracks_data)
    job['tracks'] = {}
    lookup = {}  # "artist - title" lowercased -> str(i)

    for i, t in enumerate(tracks_data, 1):
        raw_artists = t.get('artists') or []
        if raw_artists and isinstance(raw_artists[0], dict):
            artist = raw_artists[0].get('name', 'Unknown')
        elif raw_artists:
            artist = str(raw_artists[0])
        else:
            artist = t.get('artist', 'Unknown')
        title = t.get('name', 'Unknown')

        job['tracks'][str(i)] = {
            'title': title,
            'artist': artist,
            'status': 'queued',
        }
        key = f"{artist} - {title}".lower()
        lookup[key] = str(i)

    job['_lookup'] = lookup
    job['phase'] = 'downloading'

    # Choose numbering field: playlists use list position, albums/tracks use track number
    url_type = _url_type(spotify_url)
    num_field = '{list-position}' if url_type == 'playlist' else '{track-number}'
    output_tpl = f'{num_field} - {{artist}} - {{title}}.{{output-ext}}'

    cmd = [
        'spotdl', 'download', str(save_file),
        '--output', output_tpl,
        '--format', 'mp3',
        '--bitrate', '320k',
        '--threads', '4',
    ]

    env = {**os.environ, 'PYTHONUNBUFFERED': '1'}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(out_dir),
            env=env,
            bufsize=1,
        )
    except FileNotFoundError:
        job['phase'] = 'error'
        job['error'] = 'spotdl not found - run: pip3 install spotdl'
        return

    for raw in proc.stdout:
        line = _clean(raw)
        if line:
            _process_line(job, line)

    proc.wait()

    # Any track still queued or in-progress after spotdl exits failed
    for t in job['tracks'].values():
        if t['status'] in ('queued', 'downloading'):
            t['status'] = 'error'

    # Zip everything that downloaded
    job['phase'] = 'zipping'
    mp3s = sorted(out_dir.glob('*.mp3'))

    if not mp3s:
        job['phase'] = 'error'
        job['error'] = 'No MP3 files were downloaded'
        return

    safe_name = _sanitize(job['album_name']) or f'burnlist_{job_id}'
    zip_path = OUTPUT_DIR / f'{safe_name}.zip'

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for mp3 in mp3s:
            zf.write(mp3, mp3.name)

    job['phase'] = 'ready'
    job['zip'] = str(zip_path)
    job['zip_name'] = zip_path.name


def _process_line(job, line):
    lower = line.lower()
    m = re.search(r'"([^"]+)"', line)
    name = m.group(1) if m else None
    if not name:
        return

    if lower.startswith('downloaded') or lower.startswith('skipping'):
        _set_track(job, name, 'done')
    elif 'failed' in lower or "couldn't" in lower:
        _set_track(job, name, 'error')
    elif lower.startswith('downloading'):
        _set_track(job, name, 'downloading')


def _set_track(job, name, status):
    key = name.lower().strip()
    lookup = job.get('_lookup', {})
    idx = lookup.get(key)

    if idx is None:
        for k, i in lookup.items():
            if key in k or k in key:
                idx = i
                break

    if idx and idx in job['tracks']:
        job['tracks'][idx]['status'] = status


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
        if self.path != '/start':
            self._json({'error': 'not found'}, 404)
            return

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
        }

        threading.Thread(target=_run_job, args=(job_id, url), daemon=True).start()
        self._json({'job_id': job_id})

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


if __name__ == '__main__':
    print(f'BURNLIST running at http://localhost:{PORT}')
    print(f'Output: {OUTPUT_DIR}')
    server = http.server.ThreadingHTTPServer(('', PORT), Handler)
    server.serve_forever()
