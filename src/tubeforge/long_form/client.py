"""Typed LF2 transport, with no hidden generation cache, retry or fallback."""
from tubeforge.core.errors import ProviderValidationError,RetryableProviderError
from tubeforge.providers.content.host_runner import _request
from tubeforge.providers.content.host_runner_protocol import HostRunnerResponse,encode_request
from tubeforge.long_form.receipts import fingerprint


class LongFormHostRefusal(ProviderValidationError):
    def __init__(self,message,*,invocation_started=False):super().__init__(message);self.invocation_started=invocation_started


class LongFormHostClient:
    def __init__(self,codex,claude,*,transport=None):self.configs={'codex':codex,'claude':claude};self.transport=transport or _request

    def call(self,message,operation):
        owner=message.request.script_owner;config=self.configs[owner]
        if owner=='claude' and not config.enabled:raise ProviderValidationError('Claude is disabled; choose an enabled owner explicitly')
        payload=encode_request(message.model_copy(update={'operation':operation}))
        wire=self.transport(str(config.socket_path),payload,config.socket_timeout_seconds)
        try:response=HostRunnerResponse.model_validate_json(wire)
        except ValueError as error:raise RetryableProviderError('Host response was incomplete or invalid; inspect the existing receipt') from error
        if not response.ok or response.result is None:
            raise LongFormHostRefusal('Long-form host rejected the request: '+(response.failure.message if response.failure else 'invalid response'),
                invocation_started=response.failure.invocation_started if response.failure else True)
        return response.result

    def preflight(self,message,admission):
        result=self.call(message,'PreflightLongFormV1')
        required={'PrepareLongFormCallV1','LongFormStageV1','InspectLongFormCallV1'}
        if not required<=set(result.provenance.get('operations',[])) or result.package.get('admission')!=admission:
            raise ProviderValidationError('Host long-form prompt/resources/admission differ; deploy the reviewed matching wheel before launch')
        model=result.provenance.get('model')
        if not isinstance(model,str) or not model.strip():raise ProviderValidationError('Host must report the exact model before dispatch')
        if message.request.script_owner=='codex' and model!=self.configs['codex'].model:
            raise ProviderValidationError('Codex host model differs from configured model; review the change before launch')
        return model

    def receipt(self,message,operation):
        value=self.call(message,operation).package
        if value.get('call_id')!=message.call_id or value.get('payload_sha256')!=fingerprint(message):
            raise ProviderValidationError('Host receipt does not match the exact reserved call')
        return value
