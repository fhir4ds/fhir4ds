"""Hub-backed publish store (optional ``[hf]`` extra).

``HfDatasetStore`` is a :class:`~fhir4ds.serve.store.TreeStore` that keeps the
dataset tree in a local cache directory and publishes changed files with one
``create_commit`` per flush. The tree mechanics (part naming, ``meta/state.json``,
append-only parts) are inherited, so the Hub-backed and local stores cannot
drift on layout.

Conflict handling: ``create_commit`` takes the revision it was built on as
``parent_commit``; a concurrent commit makes the Hub reject it with ``409``, at
which point the store re-reads the branch head and retries **once** on top of
it. Rows keep their writer-assigned ``_seq`` across the retry, so a conflict can
never renumber a version or duplicate one.

Nothing in this module imports ``huggingface_hub`` at module import time: a
``[serve]``-only install must never need the extra.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .store import TreeStore

logger = logging.getLogger(__name__)

#: Commit message used for every flush.
COMMIT_MESSAGE = "fhir4ds serve flush"


class HfDatasetStore(TreeStore):
    """Publish the append-only dataset to a Hugging Face dataset repository."""

    def __init__(
        self,
        repo_id: str,
        cache_dir: Path | str,
        *,
        token: str | None = None,
        branch: str = "main",
        commit_message: str = COMMIT_MESSAGE,
        max_retries: int = 1,
    ) -> None:
        super().__init__(cache_dir)
        if not repo_id or "/" not in repo_id:
            raise ValueError(f"repo_id must look like 'owner/name'; got {repo_id!r}")
        self._repo_id = repo_id
        self._token = token
        self._branch = branch
        self._commit_message = commit_message
        self._max_retries = max(0, int(max_retries))
        self._downloaded = False
        self._revision = ""

    @property
    def repo_id(self) -> str:
        return self._repo_id

    # -- protocol --------------------------------------------------------

    def snapshot(self) -> Path:
        self._ensure_downloaded()
        return super().snapshot()

    def current_seq(self) -> int:
        self._ensure_downloaded()
        return super().current_seq()

    def revision(self) -> str:
        if self._downloaded and self._revision:
            return self._revision
        return super().revision()

    def commit(self) -> str:
        self._ensure_downloaded()
        revision = super().commit()
        self._publish_dirty()
        return revision

    def pending_files(self) -> int:
        self._ensure_downloaded()
        return len(self.dirty_paths())

    def retry_publish(self) -> str:
        """Upload files a failed flush committed locally but could not push."""
        self._ensure_downloaded()
        self._publish_dirty()
        return self.revision()

    # -- Hub I/O ---------------------------------------------------------

    def _ensure_downloaded(self) -> None:
        if self._downloaded:
            return
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=self._repo_id,
            repo_type="dataset",
            revision=self._branch,
            local_dir=str(self.root),
            token=self._token,
        )
        self._downloaded = True
        self._revision = self._head_revision()

    def _head_revision(self) -> str:
        from huggingface_hub import HfApi

        info = HfApi(token=self._token).repo_info(
            self._repo_id, repo_type="dataset", revision=self._branch
        )
        return str(getattr(info, "sha", "") or "")

    def _publish_dirty(self) -> None:
        dirty = sorted(self.dirty_paths())
        if not dirty:
            return

        from huggingface_hub import CommitOperationAdd, create_commit

        operations = [
            CommitOperationAdd(
                path_in_repo=relative_path,
                path_or_fileobj=str(self.root / relative_path),
            )
            for relative_path in dirty
        ]

        attempt = 0
        while True:
            try:
                result = create_commit(
                    self._repo_id,
                    operations=operations,
                    commit_message=self._commit_message,
                    repo_type="dataset",
                    token=self._token,
                    revision=self._branch,
                    parent_commit=self._revision or None,
                )
            except Exception as exc:  # noqa: BLE001 - classified immediately below
                if attempt >= self._max_retries or not _is_parent_conflict(exc):
                    raise
                attempt += 1
                self._revision = self._head_revision()
                logger.warning(
                    "publish conflict on %s; retrying on %s", self._repo_id, self._revision
                )
                continue

            self._revision = str(getattr(result, "oid", "") or self._head_revision())
            self.clear_dirty()
            return


def _is_parent_conflict(exc: Exception) -> bool:
    """Whether ``exc`` is a concurrent-commit rejection (branch head moved).

    Classified on the HTTP status the Hub returned, not on message text; the
    ``parent_commit`` phrasing is a fallback for client-side validation.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status == 409:
        return True
    return "parent_commit" in str(exc)


__all__ = ["HfDatasetStore", "COMMIT_MESSAGE"]
