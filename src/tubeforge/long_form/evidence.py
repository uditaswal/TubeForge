"""Locally captured primary-source excerpts and full-reference comparison signals."""
from __future__ import annotations

from datetime import UTC,datetime
import hashlib
import html
import json
import re
from urllib.parse import urlsplit

from tubeforge.core.errors import InsufficientSourcesError,ProviderCancellation
from tubeforge.domain.contracts import ContentRequest,SourceReference
from tubeforge.pipeline.sources import _TextExtractor
from tubeforge.providers.content.prompts import reject_instruction_spoofing
from tubeforge.reference.extractor import PublicHTTPS,IntakeFailure


def capture_primary_packet(request,result,*,http_factory=PublicHTTPS,cancelled=lambda:False):
    if result.status!='ready':raise InsufficientSourcesError(result.assessment)
    sources=[];excluded=[];limit=12000//len(result.sources)
    for item in result.sources:
        if cancelled():raise ProviderCancellation('Script preparation stopped before source capture')
        host=(urlsplit(item.url).hostname or '').casefold()
        if host in {'www.youtube.com','youtube.com','m.youtube.com','youtu.be'}:
            excluded.append(dict(source_id=item.source_id,url=item.url,reason='Video reference URLs are context, not independent primary documents.'));continue
        try:
            payload=http_factory(timeout_seconds=20,allowed_hosts={host},allowed_content_types={'text/html','text/plain'}).fetch(item.url,2_000_000)
            raw=payload.decode('utf-8')
            if raw.lstrip('\ufeff \n\t').startswith('<'):
                parser=_TextExtractor();parser.feed(raw);raw=' '.join(parser.article_parts or parser.parts)
            text=re.sub(r'\s+',' ',html.unescape(raw)).strip()
            excerpt=text[:limit]
            if len(text)>limit and ' ' in excerpt:excerpt=excerpt.rsplit(' ',1)[0]
            if len(excerpt)<200:raise ValueError('Fewer than 200 substantive readable characters')
            reject_instruction_spoofing([item.title,excerpt],field='primary_source')
            captured=datetime.now(UTC).isoformat()
            excerpt_hash=hashlib.sha256(excerpt.encode()).hexdigest();response_hash=hashlib.sha256(payload).hexdigest()
            if any(s['content_sha256']==excerpt_hash or s['original_content_sha256']==response_hash for s in sources):
                excluded.append(dict(source_id=item.source_id,url=item.url,reason='Duplicate captured response/excerpt does not count as independent evidence.'));continue
            sources.append(dict(source_id=item.source_id,url=item.url,title=item.title,author=None,retrieved_at=captured,
                excerpt=excerpt,content_sha256=excerpt_hash,
                original_content_sha256=response_hash,captured_at=captured,
                snapshot_kind='captured_primary_excerpt',untrusted=True))
        except (ValueError,IntakeFailure) as error:
            excluded.append(dict(source_id=item.source_id,url=item.url,reason='Source could not be captured as bounded public text: '+type(error).__name__))
    if cancelled():raise ProviderCancellation('Script preparation stopped during source capture')
    if len(sources)<2:
        error=InsufficientSourcesError('Research did not yield two accessible substantive primary-source documents; no narration was launched.')
        error.evidence=dict(captured_sources=sources,excluded_sources=excluded,research_assessment=result.assessment)
        raise error
    packet=dict(schema_version='1.1',sources=sources,retrieval_mode='lf2_public_primary_capture',research_assessment=result.assessment,
        excerpt_selection='Bounded article/plain-text prefix; reference observations and research assessment remain unverified context.',excluded_sources=excluded)
    allowed=set(SourceReference.model_fields)
    canonical=ContentRequest.model_validate({**request.model_dump(mode='json'),'sources':[{k:v for k,v in s.items() if k in allowed} for s in sources]})
    return canonical,packet


def reference_excerpts(reference,maximum=12):
    if not reference.cues:raise ValueError('A usable reference transcript is required')
    indexes=sorted({round(i*(len(reference.cues)-1)/(maximum-1)) for i in range(maximum)})
    return [dict(cue_index=i,start_seconds=reference.cues[i].start_seconds,text=reference.cues[i].text[:500]) for i in indexes]


def full_reference_comparison(draft,reference):
    """Compare all transcript words; a heuristic signal, never originality approval."""
    def words(text):return re.findall(r"[\w']+",text.casefold())
    reference_words=[];locations=[]
    for index,cue in enumerate(reference.cues):
        tokens=words(cue.text);reference_words.extend(tokens);locations.extend([index]*len(tokens))
    size=7;index={}
    for i in range(max(0,len(reference_words)-size+1)):
        key=tuple(reference_words[i:i+size]);index.setdefault(key,i)
    script_words=[];script_sections=[]
    for section in draft.package.script_sections:
        tokens=words(section.narration);script_words.extend(tokens);script_sections.extend([section.section_id]*len(tokens))
    matched=0;total=max(0,len(script_words)-size+1);examples=[];seen=set()
    for position in range(total):
        key=tuple(script_words[position:position+size])
        if key not in index:continue
        matched+=1
        if len(examples)<10 and key not in seen:
            seen.add(key);cue_index=locations[index[key]]
            examples.append(dict(section_id=script_sections[position],reference_cue_index=cue_index,start_seconds=reference.cues[cue_index].start_seconds,matching_words=' '.join(key)))
    report=dict(schema_version='full-reference-comparison-v1',reference_word_count=len(reference_words),script_shingle_count=total,
        matched_shingles=matched,matched_fraction=round(matched/total,4) if total else 0,examples=examples,
        notice='All reference cue words were compared with seven-word script shingles. Matches are review signals; necessary factual terms may overlap. This does not prove originality or inspect visual/audio similarity. Independently review distinctive hook, examples and explanation order.')
    # Avoid allowing a repeated source phrase to fill the review's context budget.
    while len(json.dumps(report,ensure_ascii=False).encode())>5800 and report['examples']:report['examples'].pop()
    return report
