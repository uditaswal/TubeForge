"""One durable LF2 stage per existing-worker tick; never a renderer or publisher."""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from uuid import uuid4
from tubeforge.core.errors import InsufficientSourcesError,ProviderCancellation,RetryableProviderError
from tubeforge.domain.contracts import ContentRequest,SourceReference
from tubeforge.domain.reference_video import ReferenceSnapshot
from tubeforge.domain.long_form_writing import LongFormDraftResult,LongFormReviewResult,LongFormHostRequest,LongFormTokenPolicy,PROFILE
from tubeforge.db.long_form_writing import WritingConflict,WritingBudgetExhausted,sha,json_text
from tubeforge.db.repositories import HeavyWorkLeaseRepository
from tubeforge.long_form.admission import measure,output_text_tokens
from tubeforge.long_form.evidence import reference_excerpts,capture_primary_packet,full_reference_comparison
from tubeforge.long_form.prompts import bind_draft
from tubeforge.long_form.validation import validate_draft,validate_review
from tubeforge.long_form.usage import observed_usage
from tubeforge.long_form.client import LongFormHostRefusal
from tubeforge.pipeline.long_form_reference import reference_content_identity
from tubeforge.providers.content.research import ResearchResult,ResearchSource
from tubeforge.providers.content.youtube_skills import voice_for


class LongFormWritingService:
    def __init__(self,repository,intakes,client,settings,*,source_capture=None,heavy_work=None):
        self.repository=repository;self.intakes=intakes;self.client=client;self.settings=settings;self.source_capture=source_capture or capture_primary_packet
        self.heavy_work=heavy_work or HeavyWorkLeaseRepository(repository.sessions)

    def create(self,*,intake_id,intake_revision,topic,angle,audience,owner='codex',model=None,actor='local-operator',token_policy=None,primary_urls=()):
        intake=self.intakes.get(intake_id,intake_revision)['intake']
        if intake['state']!='ready' or intake['snapshot'] is None:raise ValueError('Capture a usable reference transcript before preparing a script')
        reference=ReferenceSnapshot.model_validate(intake['snapshot']);request=intake['request']
        identity,voice=voice_for(self.settings.pipeline.codex,request['channel_identity'])
        if owner not in {'codex','claude'} or (owner=='claude' and not self.settings.pipeline.claude.enabled):raise ValueError('Choose an enabled script owner')
        if owner=='codex' and model is not None:raise ValueError('Codex uses its reviewed host model; Claude choices cannot select it')
        sources=(SourceReference(source_id='brief-context',url='https://local.invalid/long-form-brief',title='Unverified brief context; research required'),)
        if primary_urls:
            if not 2<=len(primary_urls)<=3:raise ValueError('Supply two or three distinct primary HTTPS pages')
            supplied=[]
            for url in primary_urls:
                lead=ResearchSource(source_id='lead',url=url,title='Operator-supplied source')
                if urlsplit(lead.url).fragment:raise ValueError('Supply the primary page URL without a fragment')
                supplied.append(str(SourceReference(source_id='lead',url=lead.url,title=lead.title).url))
            if len(set(supplied))!=len(supplied):raise ValueError('Supply distinct primary HTTPS pages')
            sources=tuple(SourceReference(source_id=f'primary-{index}',url=url,title=f'Supplied primary page {index}')
                          for index,url in enumerate(sorted(supplied),1))
        brief=ContentRequest(topic=topic or reference.title,angle=angle,audience=audience,language=request['language'],channel_identity=identity,channel_voice_profile=voice,
            target_duration_seconds=request['target_duration_seconds'],aspect_ratio='16:9',prompt_version=PROFILE,production_mode='generated',review_mode='manual',
            preset_name='long-form-script-v1',script_owner=owner,script_model=model,
            sources=sources)
        policy=token_policy or LongFormTokenPolicy()
        config=self.settings.pipeline.claude if owner=='claude' else self.settings.pipeline.codex
        policy=policy.model_copy(update={'maximum_narration_attempts':min(policy.maximum_narration_attempts,config.invocation_limit)})
        return self.repository.create(brief,reference,intake_id=intake_id,intake_revision=intake_revision,actor=actor,token_policy=policy,research_required=not primary_urls)

    @staticmethod
    def _result(call):
        response=call['response'] or {}
        return response.get('result',response)

    def _message(self,run):
        stage=run['next_stage'];request=ContentRequest.model_validate(run['request']);reference=ReferenceSnapshot.model_validate(run['reference'])
        packet=run['source_packet'];raw=dict(operation='LongFormStageV1',stage=stage,call_id=f"lf2-{run['id']}-call-{len(run['ledger']['calls'])+1}",brief_sha256=run['brief_sha256'],
            resolved_model=run['expected_model'],
            request=request,reference_snapshot_sha256=run['reference_snapshot_sha256'],reference_content_sha256=reference_content_identity(reference),
            reference_excerpts=reference_excerpts(reference),source_packet_sha256=sha(json_text(packet)) if packet else None,
            research_assessment=packet.get('research_assessment','') if packet else '',token_policy=LongFormTokenPolicy.model_validate(run['token_policy']))
        if stage=='review':
            draft=LongFormDraftResult.model_validate(run['draft']);raw['draft']=draft;raw['originality_context']=json_text(full_reference_comparison(draft,reference))
        elif stage=='repair':
            if run['review'] is not None:
                raw['draft']=LongFormDraftResult.model_validate(run['draft']);raw['review']=LongFormReviewResult.model_validate(run['review'])
            else:
                rejected=self.repository.stage_call(run['id'],'draft');result=self._result(rejected)
                original=result.get('raw_output') if isinstance(result.get('raw_output'),str) else json_text(result.get('output'))
                if result.get('truncated'):raise ValueError('Rejected output was truncated; inspect it before revising the brief')
                raw['rejected_output']=original;raw['local_rejection']=(run['message'] or 'Draft failed local validation.',)
        return LongFormHostRequest.model_validate(raw)

    def _transport(self,claim,call,*,cancelled=lambda:False):
        message=call['message'];state=call['state']
        if state=='reserved':
            receipt=self.client.receipt(message,'PrepareLongFormCallV1')
            if receipt.get('admission')!=call['admission']:raise ValueError('Prepared host receipt differs from the durable reservation')
            self.repository.mark_transport(claim,call['call_id'],'prepared')
            state='prepared'
        else:receipt=self.client.receipt(message,'InspectLongFormCallV1')
        remote=receipt.get('state')
        if remote=='prepared':
            if cancelled():return False
            if state=='prepared':self.repository.mark_transport(claim,call['call_id'],'dispatching')
            # Inspect proved this existing receipt has not launched. Execute is
            # idempotent on the host; a running or completed receipt never reruns.
            if cancelled():return False
            receipt=self.client.receipt(message,'LongFormStageV1');remote=receipt.get('state')
        if remote=='running':
            self.repository.mark_transport(claim,call['call_id'],'unknown')
            self.repository.release(claim,state='reconciling',message='Existing host call is still running; only its saved receipt will be checked.',delay_seconds=5)
            return False
        if remote in {'not_found','unknown'}:
            self.repository.mark_transport(claim,call['call_id'],'unknown')
            self.repository.release(claim,state='blocked',message='Host invocation outcome is unknown or its receipt is missing. No invocation will be replayed; inspect the saved call.')
            return False
        if remote not in {'succeeded','failed'}:raise ValueError('Host returned an invalid receipt state')
        result=receipt.get('result')
        if not isinstance(result,dict):raise ValueError('Completed receipt omitted invocation evidence')
        started=result.get('invocation_started');usage=observed_usage(result.get('usage'),provider=call['provider'])
        prompt_matches=not started or result.get('provenance',{}).get('prompt_sha256')==call['admission']['prompt_sha256']
        model_matches=call['model'] is None or result.get('provenance',{}).get('model')==call['model']
        success=remote=='succeeded' and prompt_matches and model_matches
        self.repository.finish_call(claim,call['call_id'],receipt,succeeded=success,invocation_started=started,usage=usage,
            error='Host model changed after reservation' if not model_matches else result.get('error') if prompt_matches else 'Host used a different prompt than the reserved input')
        return True

    def _process_result(self,claim,run,call,*,cancelled):
        result=self._result(call)
        if call['state']!='succeeded':
            self.repository.release(claim,state='blocked',message=call['failure_message'] or 'Provider invocation failed; inspect its immutable receipt. No automatic retry or provider switch occurred.')
            return
        usage=observed_usage(result.get('usage'),provider=call['provider'])
        if call['invocation_started'] is not True or usage is None or usage.input_tokens is None or usage.output_tokens is None:
            self.repository.release(claim,state='blocked',message='Essential launch/input/output usage is unknown. Reservations remain charged; reconcile before another invocation.')
            return
        if run['reserved_tokens']>run['token_policy']['total_reserved_tokens']:
            self.repository.release(claim,state='exhausted',message='Observed usage exceeded the available token budget. Output is retained; no further invocation is allowed.')
            return
        visible=result.get('output') if result.get('output') is not None else result.get('raw_output') or ''
        output_tokens=output_text_tokens(visible)
        if output_tokens>call['admission']['output_reservation']:
            self.repository.audit(claim,'stage_output_budget_exceeded',dict(call_id=call['call_id'],local_text_tokens=output_tokens,output_reservation=call['admission']['output_reservation']))
            self.repository.release(claim,state='exhausted',message='Per-call structured-output budget exceeded. The result and observed usage are retained; no automatic retry is allowed.')
            return
        stage=call['stage'];request=ContentRequest.model_validate(run['request']);reference=ReferenceSnapshot.model_validate(run['reference'])
        if stage=='research':
            research=ResearchResult.model_validate(result.get('output'))
            request,packet=self.source_capture(request,research,cancelled=cancelled)
            if cancelled():raise ProviderCancellation('Preparation stopped after source capture')
            self.repository.store_sources(claim,request,packet);self.repository.release(claim,next_stage='draft')
        elif stage in {'draft','repair'}:
            try:
                draft=bind_draft(result.get('output'),request)
                if draft.status=='insufficient_sources':raise InsufficientSourcesError(draft.reason)
                validate_draft(draft,call['message'],reference,source_packet_bytes=json_text(run['source_packet']).encode())
                if cancelled():raise ProviderCancellation('Preparation stopped after draft validation')
                self.repository.store_draft(claim,draft)
                metadata = result['output']['package']['metadata']
                if metadata.get('engagement_comment') is not None and draft.package.metadata.engagement_comment is None:
                    self.repository.audit(claim, 'optional_engagement_comment_omitted', {'call_id': call['call_id']})
            except InsufficientSourcesError:raise
            except (ValueError,TypeError) as error:
                attempts=run['usage']['narration_attempts']
                self.repository.audit(claim,'draft_rejected',dict(call_id=call['call_id'],stage=stage,reason=str(error)[:1000]))
                if stage=='draft' and attempts<run['token_policy']['maximum_narration_attempts']:
                    self.repository.release(claim,next_stage='repair',message=str(error)[:1000])
                else:self.repository.release(claim,state='exhausted',message='Narration allowance exhausted: '+str(error)[:850])
                return
            if stage=='repair' and run['review'] is not None:
                self.repository.release(claim,state='awaiting_review',message='Revised script needs exact human grounding/originality review. The independent model report applies to the earlier draft; no extra model review was called.')
            else:self.repository.release(claim,next_stage='review')
        elif stage=='review':
            draft=LongFormDraftResult.model_validate(run['draft']);review=LongFormReviewResult.model_validate(result.get('output'))
            validate_review(review,draft)
            if cancelled():raise ProviderCancellation('Preparation stopped after review validation')
            self.repository.store_review(claim,review)
            if review.decision=='pass':self.repository.release(claim,state='awaiting_review',message='Grounded script context is ready for exact operator review. Model findings do not grant approval.')
            elif review.decision=='insufficient_sources':self.repository.release(claim,state='blocked',message='Independent review found insufficient source support. Inspect findings and revise the brief/evidence explicitly.')
            elif run['usage']['narration_attempts']<run['token_policy']['maximum_narration_attempts']:self.repository.release(claim,next_stage='repair',message='Independent review requested the final narration repair.')
            else:self.repository.release(claim,state='exhausted',message='Two narration attempts are exhausted; retained drafts/findings require an explicit operator decision.')

    def run_once(self,owner,*,cancelled=lambda:False):
        if cancelled() or not self.repository.has_eligible():return None
        claim=self.repository.claim(owner)
        if claim is None:return None
        prefix='lf2-'+claim['run_id']+'-';global_owner=prefix+uuid4().hex
        if not self.heavy_work.acquire(global_owner,now=self.repository.clock(),lease_seconds=1200,reclaim_prefix=prefix):
            self.repository.release(claim,state='pending' if claim['previous_state']=='pending' else 'reconciling')
            return None
        try:return self._run_once(claim,cancelled=lambda:cancelled() or not self.heavy_work.owns(global_owner,now=self.repository.clock()))
        finally:
            run=self.repository.get(claim['run_id'])
            # A disconnect/cancellation does not terminate a host process. Keep
            # global exclusion until the exact run reconciles a terminal receipt,
            # or the lease outlives the bounded host subprocess lifetime. A fresh
            # run claim can transfer this lease; other runs/media cannot.
            if not any(c['state'] in {'dispatching','unknown'} for c in run['calls']):
                self.heavy_work.release(global_owner)

    def _run_once(self,claim,*,cancelled):
        if cancelled():return None
        stopped=lambda:cancelled() or not self.repository.owns(claim)
        try:
            run=self.repository.get(claim['run_id']);stage=run['next_stage'];call=self.repository.stage_call(run['id'],stage)
            if stage=='capture_sources':
                request=ContentRequest.model_validate(run['request'])
                leads=ResearchResult(status='ready',assessment='Operator-supplied primary URLs. Review claims against locally captured excerpts.',
                    sources=[ResearchSource(source_id=s.source_id,url=str(s.url),title=s.title) for s in request.sources])
                sourced,packet=self.source_capture(request,leads,cancelled=stopped)
                if stopped():return None
                self.repository.store_sources(claim,sourced,{**packet,'retrieval_mode':'lf2_operator_primary_capture'})
                self.repository.release(claim,next_stage='draft')
                return self.repository.get(run['id'])
            if call is None:
                message=self._message(run);admission=measure(message)
                model=self.client.preflight(message,admission)
                if message.resolved_model is None:
                    message=message.model_copy(update={'resolved_model':model});admission=measure(message)
                    if self.client.preflight(message,admission)!=model:raise ValueError('Host model changed during preflight')
                if stopped():return None
                self.repository.reserve(claim,message,admission,model=model)
                call=self.repository.stage_call(run['id'],stage)
            if call['state'] not in {'succeeded','failed'}:
                if stopped():return None
                if not self._transport(claim,call,cancelled=stopped):return self.repository.get(run['id'])
                call=self.repository.stage_call(run['id'],stage)
            if stopped():return None
            self._process_result(claim,self.repository.get(run['id']),call,cancelled=stopped)
        except ProviderCancellation:return None
        except InsufficientSourcesError as error:
            if cancelled():return None
            if self.repository.owns(claim):
                evidence=getattr(error,'evidence',None)
                if evidence is not None:self.repository.audit(claim,'source_capture_failed',evidence)
                self.repository.release(claim,state='blocked',message=str(error))
        except LongFormHostRefusal as error:
            if self.repository.owns(claim):self.repository.release(claim,state='reconciling' if error.invocation_started else 'blocked',message=str(error),delay_seconds=5 if error.invocation_started else 0)
        except WritingConflict:
            if not self.repository.owns(claim):return self.repository.get(claim['run_id'])
            self.repository.release(claim,state='blocked',message='Preparation or budget identity changed; inspect the exact stored call before continuing.')
        except WritingBudgetExhausted as error:
            if self.repository.owns(claim):self.repository.release(claim,state='exhausted',message=str(error))
        except (TimeoutError,ConnectionError,OSError,RetryableProviderError):
            if self.repository.owns(claim):
                call=self.repository.stage_call(claim['run_id'],self.repository.get(claim['run_id'])['next_stage'])
                self.repository.release(claim,state='reconciling' if call else 'blocked',message='Host transport interrupted. Existing receipts will be inspected without another model launch.',delay_seconds=5 if call else 0)
        except Exception:
            if cancelled():return None
            if self.repository.owns(claim):self.repository.release(claim,state='blocked',message='Preparation failed validation or source capture. Inspect the saved call, source access and exact input; no allowance was reset.')
        return self.repository.get(claim['run_id'])
