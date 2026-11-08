"""Bounded public HTTPS metadata/caption acquisition, with no video download."""
from __future__ import annotations

from datetime import UTC, datetime
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import threading
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.reference_video import ReferenceIntakeRequest, ReferenceSnapshot, TranscriptCue, canonical_reference_url
from tubeforge.providers.content.prompts import reject_instruction_spoofing

EXTRACTOR_VERSION = 'youtube-page-captions-v1'
HOSTS = frozenset({'www.youtube.com', 'youtube.com', 'm.youtube.com'})
_DNS_SLOTS = threading.BoundedSemaphore(2)


class IntakeFailure(ValueError):
    def __init__(self, code: str, message: str, snapshot=None):
        super().__init__(message)
        self.code, self.snapshot = code, snapshot


class PublicHTTPS:
    """Pin a resolved public IP while retaining TLS hostname verification.

    Never use process proxy/cookie configuration or follow redirects implicitly.
    Every redirect revalidates host, scheme, credentials, port and public DNS.
    """
    def __init__(self, timeout_seconds=25, resolver=socket.getaddrinfo, *, allowed_hosts=None, allowed_content_types=None):
        self.timeout_seconds, self.resolver = timeout_seconds, resolver
        self.allowed_hosts=HOSTS if allowed_hosts is None else frozenset(h.casefold() for h in allowed_hosts)
        self.allowed_content_types=allowed_content_types

    def _resolve(self, host, deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0 or not _DNS_SLOTS.acquire(timeout=max(0,remaining)):raise TimeoutError()
        result=[];done=threading.Event()
        def lookup():
            try:result.append(self.resolver(host,443,type=socket.SOCK_STREAM))
            except Exception as error:result.append(error)
            finally:_DNS_SLOTS.release();done.set()
        threading.Thread(target=lookup,name='reference-dns',daemon=True).start()
        if not done.wait(max(0,deadline-time.monotonic())):raise TimeoutError()
        if isinstance(result[0],Exception):raise OSError('Reference DNS lookup failed')
        return result[0]

    def fetch(self, url: str, maximum_bytes: int) -> bytes:
        deadline = time.monotonic() + self.timeout_seconds
        for _ in range(4):
            target = urlsplit(url)
            if target.scheme != 'https' or target.hostname not in self.allowed_hosts or target.username or target.password or target.port not in {None,443}:
                raise IntakeFailure('retrieval_failed','Reference redirects or caption hosts are not permitted.')
            try:
                addresses = list(dict.fromkeys(item[4][0] for item in self._resolve(target.hostname,deadline)))
                if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
                    raise IntakeFailure('retrieval_failed','Reference resolved to a private or reserved network address.')
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise TimeoutError()
                connection = http.client.HTTPSConnection(target.hostname,timeout=remaining,context=ssl.create_default_context())
                # Connect only to the IP already checked, with the original TLS name.
                transport = socket.create_connection((addresses[0],443),timeout=remaining)
                def expire(active_connection=connection,raw_transport=transport):
                    # Socket timeouts alone reset on every received byte. Close
                    # the transport at the absolute deadline, including headers
                    # or a body arriving a few bytes at a time.
                    active=active_connection.sock or raw_transport
                    try: active.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                    active.close()
                watchdog=threading.Timer(max(0,deadline-time.monotonic()),expire)
                watchdog.daemon=True;watchdog.start()
                try:
                    transport.settimeout(max(.001,deadline-time.monotonic()))
                    tls = connection._context.wrap_socket(transport,server_hostname=target.hostname)
                    connection.sock = tls
                except BaseException:
                    watchdog.cancel();transport.close(); raise
                try:
                    path = urlunsplit(('', '', target.path or '/',target.query,''))
                    connection.request('GET',path,headers={'User-Agent':'Mozilla/5.0 (compatible; TubeForge reference intake)', 'Accept-Encoding':'identity'})
                    response = connection.getresponse()
                    if response.status in {301,302,303,307,308}:
                        location = response.getheader('Location')
                        if not location: raise IntakeFailure('retrieval_failed','Reference redirect had no destination.')
                        url=urljoin(url,location); continue
                    if response.status in {401,403,404,410}:
                        raise IntakeFailure('unavailable','This public reference is unavailable or access restricted.')
                    if response.status != 200:
                        raise IntakeFailure('retrieval_failed',f'Reference server returned HTTP {response.status}; retry later or supply a transcript.')
                    if response.getheader('Content-Encoding','identity') != 'identity':
                        raise IntakeFailure('retrieval_failed','Reference response used an unsupported content encoding.')
                    content_type=response.getheader('Content-Type','').split(';',1)[0].strip().lower()
                    if self.allowed_content_types is not None and content_type not in self.allowed_content_types:
                        raise IntakeFailure('retrieval_failed','Source response must be HTML or plain text.')
                    length=response.getheader('Content-Length')
                    if length and int(length)>maximum_bytes: raise IntakeFailure('oversized','Reference response exceeds the byte limit.')
                    chunks=[]; total=0
                    while True:
                        remaining=deadline-time.monotonic()
                        if remaining<=0: raise TimeoutError()
                        tls.settimeout(remaining)
                        chunk=response.read(min(16384,maximum_bytes+1-total))
                        if not chunk: return b''.join(chunks)
                        total+=len(chunk)
                        if total>maximum_bytes: raise IntakeFailure('oversized','Reference response exceeds the byte limit.')
                        chunks.append(chunk)
                finally:
                    watchdog.cancel()
                    connection.close()
            except IntakeFailure: raise
            except (OSError,ValueError,http.client.HTTPException) as error:
                raise IntakeFailure('retrieval_failed','Public reference retrieval failed or timed out; retry later or supply a transcript.') from error
        raise IntakeFailure('retrieval_failed','Reference exceeded the redirect limit.')


def parse_player_response(payload: bytes) -> dict:
    try: page=payload.decode('utf-8')
    except UnicodeDecodeError as error: raise IntakeFailure('retrieval_failed','Reference page was not readable UTF-8.') from error
    decoder=json.JSONDecoder()
    for match in re.finditer(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*',page):
        try:
            value,_=decoder.raw_decode(page[match.end():])
            if isinstance(value,dict): return value
        except ValueError: continue
    raise IntakeFailure('unavailable','Public video metadata was not available; check that the link is public and accessible.')


def parse_caption_payload(payload: bytes) -> tuple[TranscriptCue,...]:
    if len(payload)>1_500_000: raise IntakeFailure('oversized','Caption response exceeds the byte limit.')
    try:
        text=payload.decode('utf-8')
        if text.lstrip().startswith('{'):
            raw=json.loads(text); rows=[]
            for event in raw.get('events',[]):
                content=''.join(s.get('utf8','') for s in event.get('segs',[])).strip()
                if not content or not event.get('dDurationMs'): continue
                start=float(event['tStartMs'])/1000
                rows.append(TranscriptCue(start_seconds=start,end_seconds=start+float(event['dDurationMs'])/1000,text=content))
        else:
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper(): raise ValueError('entities forbidden')
            tree=ET.fromstring(text);rows=[]
            for node in tree.iter():
                if node.tag not in {'text','p'}: continue
                if 'start' in node.attrib:
                    start=float(node.attrib['start']);duration=float(node.attrib['dur'])
                else:
                    start=float(node.attrib['t'])/1000;duration=float(node.attrib['d'])/1000
                content=''.join(node.itertext()).strip()
                if content: rows.append(TranscriptCue(start_seconds=start,end_seconds=start+duration,text=content))
        if not rows: raise ValueError('no timed speech')
        return tuple(rows)
    except (ValueError,KeyError,TypeError,AttributeError,ET.ParseError) as error:
        raise IntakeFailure('captions_unavailable','Caption response was empty or malformed; supply a transcript or retry when public access is available.') from error


def check_reference_text(title, creator, cues):
    try:
        reject_instruction_spoofing([title,creator,*[c.text for c in cues]],field='reference')
    except ProviderValidationError as error:
        raise IntakeFailure('unsafe_content','Reference contains instruction-control text; choose another reference or supply clean captions.') from error


class YoutubeReferenceExtractor:
    version=EXTRACTOR_VERSION
    def __init__(self,http=None): self.http=http or PublicHTTPS()

    def capture(self, request: ReferenceIntakeRequest, *, cancelled=lambda:False) -> ReferenceSnapshot:
        url=canonical_reference_url(request.reference_url)
        if cancelled(): raise IntakeFailure('cancelled','Reference intake was cancelled.')
        player=parse_player_response(self.http.fetch(url,3_000_000))
        if player.get('playabilityStatus',{}).get('status') not in {None,'OK'}:
            raise IntakeFailure('unavailable','This reference is unavailable or access restricted.')
        details=player.get('videoDetails',{})
        if details.get('videoId') != urlsplit(url).query.removeprefix('v='):
            raise IntakeFailure('unavailable','Reference metadata did not match the requested video.')
        try:
            duration=float(details['lengthSeconds']);title=details['title'];creator=details['author']
            base=dict(extractor_version=self.version,reference_url=url,video_id=details['videoId'],title=title,
                      creator=creator,duration_seconds=duration,captured_at=datetime.now(UTC),language=request.language)
            check_reference_text(title,creator,())
            limitations=['Metadata and transcript only; video and audio were not watched or listened to.','Reference context is not verified factual evidence or permission to reuse footage.']
            if request.supplied_cues:
                cues=request.supplied_cues;origin='supplied'
                limitations.append('Transcript supplied by the operator; it was not verified against the source audio.')
            else:
                tracks=player.get('captions',{}).get('playerCaptionsTracklistRenderer',{}).get('captionTracks',[])
                matches=[t for t in tracks if t.get('languageCode','').casefold()==request.language.casefold()]
                if not matches:
                    languages=sorted({str(t.get('languageCode','')) for t in tracks})
                    reason=('Requested caption language is unavailable. Available: '+', '.join(languages)) if languages else 'No public captions were available; supply a timestamped transcript.'
                    snapshot=ReferenceSnapshot(**base,transcript_origin='unavailable',cues=(),limitations=(*limitations,reason[:500]))
                    if languages: raise IntakeFailure('language_mismatch',reason[:500],snapshot=snapshot)
                    return snapshot
                track=next((t for t in matches if t.get('kind')!='asr'),matches[0])
                target=urlsplit(track['baseUrl'])
                video_ids=[v for k,v in parse_qsl(target.query,keep_blank_values=True) if k=='v']
                if video_ids != [details['videoId']]:
                    raise IntakeFailure('captions_unavailable','Caption track identity does not match the reference.')
                query=[(k,v) for k,v in parse_qsl(target.query,keep_blank_values=True) if k!='fmt']+[('fmt','json3')]
                if cancelled(): raise IntakeFailure('cancelled','Reference intake was cancelled.')
                try:
                    cues=parse_caption_payload(self.http.fetch(urlunsplit(target._replace(query=urlencode(query))),1_500_000))
                except IntakeFailure as error:
                    error.snapshot=ReferenceSnapshot(**base,transcript_origin='unavailable',cues=(),limitations=(*limitations,str(error)[:500]))
                    raise
                origin='captions'
                if track.get('kind')=='asr': limitations.append('Automatically generated captions may contain transcription errors.')
            check_reference_text(title,creator,cues)
            return ReferenceSnapshot(**base,transcript_origin=origin,cues=cues,limitations=tuple(limitations))
        except IntakeFailure: raise
        except (ValueError,KeyError,TypeError) as error:
            raise IntakeFailure('retrieval_failed','Reference metadata or transcript is invalid or outside supported bounds.') from error
