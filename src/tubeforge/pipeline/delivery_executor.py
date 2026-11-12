"""Execute one fenced destination claim through an account-scoped adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import time
from typing import Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.pipeline.delivery_queue import DeliveryClaim, DeliveryQueue
from tubeforge.pipeline.youtube_quota import YouTubeQuotaExhausted, YouTubeQuotaLedger
from tubeforge.pipeline.provider_backoff import retry_delay
from tubeforge.security.account_credentials import AccountCredentialManager, CredentialBusy, CredentialReconnectRequired, CredentialRefreshTemporary, GoogleCredentialRefresher
from tubeforge.security.secrets import TokenCipher


@dataclass(frozen=True, slots=True)
class UploadReceipt:
    remote_id: str
    remote_url: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteSession:
    """Persisted upload/container session; expiry must be timezone-aware."""
    session_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ContainerReceipt:
    """Upload completed into a container, but no public post exists yet."""
    container_id: str


@dataclass(frozen=True, slots=True)
class ContainerObservation:
    state: str  # processing, ready, published, expired, failed
    remote_id: str | None = None
    remote_url: str | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class RemoteObservation:
    state: str  # published, processing, missing
    external_account_id: str | None = None
    title: str | None = None
    caption: str | None = None
    remote_url: str | None = None
    privacy: str | None = None
    publish_at: str | None = None


class DestinationAdapter(Protocol):
    """An adapter must create a resumable remote session before upload bytes."""

    def open_session(self, *, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object]) -> str | RemoteSession: ...
    def upload(self, *, session_id: str, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object], heartbeat: Callable[[], bool]) -> UploadReceipt | ContainerReceipt: ...
    def inspect(self, *, remote_id: str, external_account_id: str, credential: dict[str, object]) -> RemoteObservation: ...
    def inspect_session(self, *, session_id: str, credential: dict[str, object], asset_size: int) -> UploadReceipt | ContainerReceipt | None: ...
    def resume_session(self, *, session_id: str, credential: dict[str, object], asset_path: Path, heartbeat: Callable[[], bool]) -> UploadReceipt | ContainerReceipt: ...


class ContainerDestinationAdapter(DestinationAdapter, Protocol):
    """Separate processing inspection and an externally visible publish mutation."""

    def inspect_container(self, *, container_id: str, external_account_id: str, credential: dict[str, object]) -> ContainerObservation: ...
    def publish_container(self, *, container_id: str, external_account_id: str, credential: dict[str, object], heartbeat: Callable[[], bool]) -> UploadReceipt: ...


class ProviderRateLimitHint(RuntimeError):
    """Read-only/pre-mutation rate limit with a provider-supplied delay."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("destination rate limit")
        self.retry_after_seconds = retry_after_seconds


class ProviderQuotaError(RuntimeError):
    """Provider reports a quota limit; operator action is required."""


class ProviderAuthError(RuntimeError):
    """Provider requires the account to be reconnected."""


class SafePreflightError(RuntimeError):
    """Adapter proved no remote upload session or media mutation began."""

    def __init__(self, reason: str, *, category: str = "invalid", retry_after_seconds: int | None = None) -> None:
        super().__init__(reason)
        self.category = category
        self.retry_after_seconds = retry_after_seconds


class DeliveryExecutor:
    def __init__(
        self, session_factory: sessionmaker[Session], queue: DeliveryQueue,
        cipher: TokenCipher, stage_root: Path, adapters: dict[str, DestinationAdapter],
        credential_manager: AccountCredentialManager | None = None,
        youtube_quota: YouTubeQuotaLedger | None = None,
    ) -> None:
        self.session_factory, self.queue, self.cipher = session_factory, queue, cipher
        self.stage_root, self.adapters = stage_root, adapters
        self.credential_manager = credential_manager or AccountCredentialManager(session_factory, cipher, {"youtube": GoogleCredentialRefresher()})
        self.youtube_quota = youtube_quota or YouTubeQuotaLedger(session_factory)

    def run_once(self, worker_id: str) -> str | None:
        claim = self.queue.claim_next(worker_id, platforms=set(self.adapters))
        if claim is None:
            return None
        adapter = self.adapters.get(claim.platform)
        if adapter is None:
            self._reject_before_remote(claim, "destination adapter is not configured")
            return claim.delivery_id
        if claim.platform == "instagram" and claim.kind == "upload" and not all(callable(getattr(adapter, method, None)) for method in ("inspect_container", "publish_container")):
            self._reject_before_remote(claim, "Instagram adapter must support separate container processing and publication")
            return claim.delivery_id
        try:
            asset, metadata = self._inputs(claim)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._reject_before_remote(claim, "destination credential or canonical video is unavailable")
            return claim.delivery_id
        # Credential refresh may contact the provider. Check the local file first.
        if claim.kind == "upload" and callable(getattr(adapter, "preflight", None)):
            try:
                adapter.preflight(asset_path=asset, metadata=metadata)
            except SafePreflightError as error:
                self._reject_before_remote(claim, str(error))
                return claim.delivery_id
        if claim.kind == "upload" and claim.platform == "youtube":
            try:
                self.youtube_quota.reserve(claim)
            except YouTubeQuotaExhausted as error:
                self.queue.quota_pause(claim, str(error))
                return claim.delivery_id
        try:
            credential = self.credential_manager.resolve(claim.account_id, claim.owner)
        except CredentialBusy:
            self._wait_before_remote(claim, seconds=retry_delay(None, attempt=claim.attempt_number), reason="account credential refresh is in progress")
            return claim.delivery_id
        except CredentialRefreshTemporary as error:
            self._wait_before_remote(claim, seconds=retry_delay(error.retry_after_seconds, attempt=claim.attempt_number), reason="account credential refresh is temporarily unavailable")
            return claim.delivery_id
        except (CredentialReconnectRequired, ValueError):
            self.queue.auth_required(claim, "destination account needs reconnection")
            return claim.delivery_id
        credential_ciphertext = self._credential_version(claim, credential)
        if claim.kind == "verify":
            try:
                observation = adapter.inspect(remote_id=claim.remote_id or "", external_account_id=claim.external_account_id, credential=credential)
            except ProviderRateLimitHint as error:
                self.queue.verification_pending(claim, retry_at=datetime.now(UTC) + timedelta(seconds=retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)))
                return claim.delivery_id
            except ProviderQuotaError:
                self.queue.quota_pause(claim, "destination quota exhausted; resume after quota is available")
                return claim.delivery_id
            except ProviderAuthError:
                self.queue.auth_required(claim, "destination account needs reconnection", credential_ciphertext=credential_ciphertext)
                return claim.delivery_id
            except Exception:
                self.queue.verification_pending(claim, retry_at=datetime.now(UTC) + timedelta(seconds=retry_delay(None, attempt=claim.attempt_number)))
                return claim.delivery_id
            if observation.state == "processing":
                self.queue.verification_pending(claim, retry_at=datetime.now(UTC) + timedelta(minutes=2))
            elif observation.state == "missing":
                self.queue.remote_missing(claim)
            elif observation.state == "published" and self._matches(claim, metadata, observation):
                self.queue.verified_published(claim, remote_url=observation.remote_url)
            else:
                self.queue.verification_attention(claim, "remote publication does not match the reviewed destination or metadata")
            return claim.delivery_id
        if claim.kind in {"container_check", "container_publish"}:
            if claim.remote_session_expires_at is None or _as_utc(claim.remote_session_expires_at) <= datetime.now(UTC):
                self.queue.container_defer(claim, "remote container expired before publication", fail=True)
                return claim.delivery_id
            if claim.kind == "container_check":
                try:
                    observation = adapter.inspect_container(container_id=claim.remote_container_id or "", external_account_id=claim.external_account_id, credential=credential)
                    delay = retry_delay(observation.retry_after_seconds, attempt=claim.attempt_number)
                    self.queue.container_observed(claim, observation.state, retry_at=datetime.now(UTC) + timedelta(seconds=delay), remote_id=observation.remote_id, remote_url=observation.remote_url)
                except ProviderRateLimitHint as error:
                    delay = retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)
                    self.queue.container_defer(claim, "destination rate limit", retry_at=datetime.now(UTC) + timedelta(seconds=delay))
                except ProviderQuotaError:
                    self.queue.quota_pause(claim, "destination quota exhausted; resume after quota is available")
                except ProviderAuthError:
                    self.queue.auth_required(claim, "destination account needs reconnection", credential_ciphertext=credential_ciphertext)
                except Exception:
                    self.queue.container_defer(claim, "container status is temporarily unavailable", retry_at=datetime.now(UTC) + timedelta(minutes=2))
                return claim.delivery_id
            if not self.queue.heartbeat(claim):
                return claim.delivery_id
            if claim.scheduled_for and _as_utc(claim.scheduled_for) + timedelta(minutes=30) < datetime.now(UTC):
                self.queue.mark_missed(claim)
                return claim.delivery_id
            if _as_utc(claim.remote_session_expires_at) <= datetime.now(UTC):
                self.queue.container_defer(claim, "remote container expired before publication", fail=True)
                return claim.delivery_id
            try:
                receipt = adapter.publish_container(container_id=claim.remote_container_id or "", external_account_id=claim.external_account_id, credential=credential, heartbeat=lambda: self.queue.heartbeat(claim))
                if not isinstance(receipt, UploadReceipt) or not receipt.remote_id:
                    raise ValueError("published media identity is missing")
            except ProviderRateLimitHint as error:
                delay = retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)
                self.queue.uncertain(claim, "remote container publication outcome is unknown; rate limit applies", retry_at=datetime.now(UTC) + timedelta(seconds=delay))
                return claim.delivery_id
            except Exception:
                self.queue.uncertain(claim, "remote container publication outcome is unknown")
                return claim.delivery_id
            self.queue.container_published(claim, receipt.remote_id, remote_url=receipt.remote_url)
            return claim.delivery_id
        # Refresh may cross Pacific midnight; reserve against the current day too.
        if claim.platform == "youtube":
            try:
                self.youtube_quota.reserve(claim)
            except YouTubeQuotaExhausted as error:
                self.queue.quota_pause(claim, str(error))
                return claim.delivery_id
        if not self.queue.heartbeat(claim):
            return claim.delivery_id
        if claim.scheduled_for and _as_utc(claim.scheduled_for) + timedelta(minutes=30) < datetime.now(UTC):
            self.queue.mark_missed(claim)
            return claim.delivery_id
        try:
            session_id = adapter.open_session(external_account_id=claim.external_account_id, credential=credential, asset_path=asset, metadata=metadata)
        except SafePreflightError as error:
            if error.category == "retry":
                self._wait_before_remote(claim, seconds=retry_delay(error.retry_after_seconds, attempt=claim.attempt_number), reason=str(error))
            elif error.category == "quota":
                self.queue.quota_pause(claim, str(error))
            elif error.category == "auth":
                self.queue.auth_required(claim, str(error), credential_ciphertext=credential_ciphertext)
            else:
                self.queue.preflight_failed(claim, str(error))
            return claim.delivery_id
        except Exception:
            self.queue.uncertain(claim, "remote session creation outcome is unknown")
            return claim.delivery_id
        if claim.platform == "instagram" and not isinstance(session_id, RemoteSession):
            self.queue.uncertain(claim, "Instagram adapter did not provide a durable container expiry")
            return claim.delivery_id
        expiry = session_id.expires_at if isinstance(session_id, RemoteSession) else None
        session_id = session_id.session_id if isinstance(session_id, RemoteSession) else session_id
        try:
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("remote session identity is invalid")
            self.queue.record_session(claim, self.cipher.encrypt({"session_id": session_id}), expires_at=expiry)
        except (ValueError, TypeError):
            self.queue.uncertain(claim, "remote session could not be recorded safely")
            return claim.delivery_id
        try:
            receipt = adapter.upload(
                session_id=session_id, external_account_id=claim.external_account_id,
                credential=credential, asset_path=asset, metadata=metadata,
                heartbeat=lambda: self.queue.heartbeat(claim),
            )
        except ProviderRateLimitHint as error:
            delay = retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)
            self.queue.uncertain(claim, "remote upload outcome is unknown; rate limit applies", retry_at=datetime.now(UTC) + timedelta(seconds=delay))
            return claim.delivery_id
        except ProviderQuotaError:
            self.queue.quota_pause(claim, "destination quota exhausted; resume and inspect the saved session")
            return claim.delivery_id
        except ProviderAuthError:
            self.queue.auth_required(claim, "destination account needs reconnection", credential_ciphertext=credential_ciphertext)
            return claim.delivery_id
        except Exception:
            self.queue.uncertain(claim, "remote upload outcome is unknown")
            return claim.delivery_id
        if claim.platform == "instagram" and not isinstance(receipt, ContainerReceipt):
            self.queue.uncertain(claim, "Instagram adapter did not return an unpublished container")
            return claim.delivery_id
        if isinstance(receipt, ContainerReceipt):
            try:
                self.queue.container_staged(claim, receipt.container_id)
            except ValueError:
                self.queue.uncertain(claim, "remote container outcome could not be recorded safely")
        else:
            self.queue.upload_accepted(claim, receipt.remote_id, remote_url=receipt.remote_url)
        return claim.delivery_id

    def run_requested_action(self, worker_id: str) -> str | None:
        requested = self.queue.next_requested_action(platforms=set(self.adapters))
        if requested is None:
            return None
        delivery_id, action = requested
        if action == "inspect":
            return self.reconcile_once(delivery_id, worker_id)
        return self.resume_once(delivery_id, worker_id)

    def reconcile_once(self, delivery_id: str, worker_id: str) -> str | None:
        """Read the saved upload session; never initiate a replacement upload."""
        claim = self.queue.claim_reconciliation(delivery_id, worker_id)
        if claim is None:
            return None
        adapter = self.adapters.get(claim.platform)
        if adapter is None:
            self.queue.reconciliation_unresolved(claim, "destination reconciliation adapter is unavailable")
            return claim.delivery_id
        try:
            asset, _ = self._inputs(claim)
            credential = self.credential_manager.resolve(claim.account_id, claim.owner)
            envelope = self.cipher.decrypt(claim.remote_session_id or "")
            session_id = envelope.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("saved upload session is invalid")
        except (OSError, ValueError, CredentialBusy, CredentialReconnectRequired, CredentialRefreshTemporary):
            self.queue.reconciliation_unresolved(claim, "saved session or account credential is unavailable")
            return claim.delivery_id
        if claim.remote_container_id:
            try:
                observation = adapter.inspect_container(container_id=claim.remote_container_id, external_account_id=claim.external_account_id, credential=credential)
                delay = max(1, min(3600, int(observation.retry_after_seconds or 120)))
                self.queue.container_observed(claim, observation.state, retry_at=datetime.now(UTC) + timedelta(seconds=delay), remote_id=observation.remote_id, remote_url=observation.remote_url)
            except ProviderRateLimitHint as error:
                delay = retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)
                self.queue.reconciliation_unresolved(claim, "remote container inspection rate limited", retry_at=datetime.now(UTC) + timedelta(seconds=delay))
            except ProviderAuthError:
                self.queue.reconciliation_unresolved(claim, "reconnect the destination account before inspecting the container")
            except ProviderQuotaError:
                self.queue.reconciliation_unresolved(claim, "destination quota exhausted; inspect the container after quota is available")
            except Exception:
                self.queue.reconciliation_unresolved(claim, "remote container publication could not be proven")
            return claim.delivery_id
        try:
            receipt = adapter.inspect_session(session_id=session_id, credential=credential, asset_size=asset.stat().st_size)
        except ProviderRateLimitHint as error:
            delay = retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)
            self.queue.reconciliation_unresolved(claim, "remote session rate limited; inspect again after the delay", retry_at=datetime.now(UTC) + timedelta(seconds=delay))
            return claim.delivery_id
        except ProviderAuthError:
            self.queue.reconciliation_unresolved(claim, "reconnect the destination account before inspecting the saved session")
            return claim.delivery_id
        except ProviderQuotaError:
            self.queue.reconciliation_unresolved(claim, "destination quota exhausted; inspect the saved session after quota is available")
            return claim.delivery_id
        except Exception:
            self.queue.reconciliation_unresolved(claim, "remote session status could not be proven")
            return claim.delivery_id
        if receipt is None:
            self.queue.reconciliation_unresolved(claim, "remote upload is incomplete; resume the saved session before any new upload")
        elif isinstance(receipt, ContainerReceipt):
            self.queue.container_staged(claim, receipt.container_id)
        else:
            self.queue.reconciled_uploaded(claim, receipt.remote_id, remote_url=receipt.remote_url)
        return claim.delivery_id

    def resume_once(self, delivery_id: str, worker_id: str) -> str | None:
        """Explicitly continue the saved session; never open a replacement."""
        claim = self.queue.claim_reconciliation(delivery_id, worker_id, resume=True)
        if claim is None:
            return None
        adapter = self.adapters.get(claim.platform)
        if adapter is None:
            self.queue.reconciliation_unresolved(claim, "destination resume adapter is unavailable")
            return claim.delivery_id
        try:
            asset, _ = self._inputs(claim)
            credential = self.credential_manager.resolve(claim.account_id, claim.owner)
            envelope = self.cipher.decrypt(claim.remote_session_id or "")
            session_id = envelope.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("saved upload session is invalid")
        except (OSError, ValueError, CredentialBusy, CredentialReconnectRequired, CredentialRefreshTemporary):
            self.queue.reconciliation_unresolved(claim, "saved session or account credential is unavailable")
            return claim.delivery_id
        try:
            receipt = adapter.resume_session(session_id=session_id, credential=credential, asset_path=asset, heartbeat=lambda: self.queue.heartbeat(claim))
        except ProviderRateLimitHint as error:
            delay = retry_delay(error.retry_after_seconds, attempt=claim.attempt_number)
            self.queue.reconciliation_unresolved(claim, "saved session rate limited; inspect again after the delay", retry_at=datetime.now(UTC) + timedelta(seconds=delay))
            return claim.delivery_id
        except Exception:
            self.queue.reconciliation_unresolved(claim, "same-session upload continuation could not be proven")
            return claim.delivery_id
        if isinstance(receipt, ContainerReceipt):
            self.queue.container_staged(claim, receipt.container_id)
        else:
            self.queue.reconciled_uploaded(claim, receipt.remote_id, remote_url=receipt.remote_url)
        return claim.delivery_id

    def _credential_version(self, claim: DeliveryClaim, credential: dict[str, object]) -> str | None:
        """Fence a later auth failure against a concurrently reconnected account."""
        try:
            with self.session_factory() as session:
                account = session.get(SocialAccountRecord, claim.account_id)
                ciphertext = account.credential_ciphertext if account else None
            return ciphertext if ciphertext and self.cipher.decrypt(ciphertext) == credential else None
        except (ValueError, TypeError):
            return None

    def _inputs(self, claim: DeliveryClaim) -> tuple[Path, dict[str, object]]:
        with self.session_factory() as session:
            delivery = session.get(DestinationDeliveryRecord, claim.delivery_id)
            account = session.get(SocialAccountRecord, claim.account_id)
            asset = session.get(PublishingAssetRecord, delivery.asset_id) if delivery else None
            if delivery is None or account is None or asset is None or account.disabled or account.status != "connected" or account.external_account_id != claim.external_account_id or not account.credential_ciphertext:
                raise ValueError("destination identity is unavailable")
            post = session.get(PublishJobRecord, delivery.publish_job_id)
            siblings = list(session.scalars(select(DestinationDeliveryRecord).where(DestinationDeliveryRecord.publish_job_id == delivery.publish_job_id)))
            from tubeforge.pipeline.manual_publish import ManualPublishService
            if post is None or post.asset_id != asset.id or any(item.asset_id != asset.id for item in siblings) or not post.reviewed_identity or post.reviewed_identity != ManualPublishService._review_identity(asset, siblings):
                raise ValueError("reviewed destination identity changed")
            metadata = json.loads(delivery.metadata_json)
            if not isinstance(metadata, dict):
                raise ValueError("destination metadata is invalid")
            if claim.platform == "instagram":
                confirmation = json.loads(post.metadata_json).get("public_confirmation") or {}
                if (not isinstance(confirmation, dict) or not confirmation.get("actor")
                        or confirmation.get("reviewed_identity") != post.reviewed_identity
                        or not isinstance(confirmation.get("account_ids"), list)
                        or claim.account_id not in confirmation["account_ids"]):
                    raise ValueError("exact-post public confirmation is unavailable")
                metadata["confirm_public"] = True
            if claim.platform == "youtube" and delivery.scheduled_for is not None:
                metadata["scheduled_for"] = _as_utc(delivery.scheduled_for).isoformat().replace("+00:00", "Z")
                metadata["schedule_audit_allowed"] = bool(delivery.youtube_schedule_audited)
                metadata["expect_publish_at"] = bool(delivery.youtube_schedule_audited and getattr(self.adapters.get("youtube"), "youtube_api_audited", False))
            stage_root = self.stage_root.resolve(strict=True)
            path = Path(asset.staged_path)
            if path.is_symlink() or path.parent.resolve(strict=True) != stage_root or path.name != f"{asset.sha256}.mp4":
                raise ValueError("canonical video path is invalid")
            size = 0
            digest = hashlib.sha256()
            last_heartbeat = time.monotonic()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
                    if time.monotonic() - last_heartbeat >= 20:
                        if not self.queue.heartbeat(claim):
                            raise ValueError("delivery lease was lost while checking the canonical video")
                        last_heartbeat = time.monotonic()
            if size != asset.size_bytes or digest.hexdigest() != asset.sha256:
                raise ValueError("canonical video fingerprint changed")
            return path, metadata

    def _wait_before_remote(self, claim: DeliveryClaim, *, seconds: int, reason: str) -> None:
        retry_at = datetime.now(UTC) + timedelta(seconds=seconds)
        if claim.kind == "upload":
            self.queue.preflight_retry(claim, reason, retry_at=retry_at)
        elif claim.kind in {"container_check", "container_publish"}:
            self.queue.container_defer(claim, reason, retry_at=retry_at)
        else:
            self.queue.verification_pending(claim, retry_at=retry_at)

    def _reject_before_remote(self, claim: DeliveryClaim, reason: str) -> None:
        if claim.kind == "upload":
            self.queue.preflight_failed(claim, reason)
        elif claim.kind in {"container_check", "container_publish"}:
            self.queue.container_defer(claim, reason, fail=True)
        else:
            self.queue.verification_attention(claim, reason)

    @staticmethod
    def _matches(claim: DeliveryClaim, metadata: dict[str, object], observation: RemoteObservation) -> bool:
        if observation.external_account_id != claim.external_account_id:
            return False
        if claim.platform == "youtube":
            if not (observation.title == metadata.get("title") and observation.caption == metadata.get("caption") and observation.privacy == metadata.get("visibility", "private")):
                return False
            scheduled = metadata.get("scheduled_for")
            if scheduled and metadata.get("expect_publish_at"):
                if not observation.publish_at:
                    return False
                try:
                    return datetime.fromisoformat(str(scheduled).replace("Z", "+00:00")) == datetime.fromisoformat(observation.publish_at.replace("Z", "+00:00"))
                except ValueError:
                    return False
            return not observation.publish_at
        if claim.platform == "instagram":
            return observation.caption == metadata.get("caption")
        return False


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
