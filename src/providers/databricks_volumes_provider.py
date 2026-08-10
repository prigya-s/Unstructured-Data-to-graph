"""
DatabricksVolumesProvider: StorageProvider backed by a Unity Catalog Volume.

A Unity Catalog Volume is mounted inside a Databricks cluster/App/job at an
ordinary POSIX path (/Volumes/<catalog>/<schema>/<volume>/...) - reads and
writes against it are exactly the file operations LocalStorageProvider
already performs (Path.mkdir/write_text/read_text). There is nothing
Volumes-specific to implement: this class *is* LocalStorageProvider,
pointed at config.storage.root when that root happens to be a Volume path
instead of a local directory. Selecting this provider is therefore
configuration only - set storage.provider: databricks_volumes and
storage.root: /Volumes/<catalog>/<schema>/<volume>/lakehouse in config.yaml.

(The one real prerequisite - that the Volume is actually mounted and
writable from wherever this process runs - is a Databricks workspace/compute
setup step, not something any StorageProvider implementation can express.)
"""

from __future__ import annotations

from config.app_config import AppConfig

from .local_storage_provider import LocalStorageProvider


class DatabricksVolumesProvider(LocalStorageProvider):
    def __init__(self, config: AppConfig) -> None:
        super().__init__(config.storage_root)
