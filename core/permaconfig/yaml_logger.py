
"""Create a Yaml logger for Experiments."""

import yaml
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

## AI Generated -- computed once, not per format() call -- a LogRecord's own standard
## attribute names, so format() only needs to diff against this fixed set
## to find whatever extra fields a caller attached via logging's `extra=`.
_STANDARD_LOGRECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class YAMLStreamFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            #"msg": record.getMessage(), -> because RichHandler sets "message" internally.
        }

        for k, v in record.__dict__.items():
            if k not in _STANDARD_LOGRECORD_ATTRS:
                entry[k] = v

        return "---\n" + yaml.safe_dump(entry, sort_keys=False)
def create_yaml_logger(
    path: str,
    max_mb: int = 5,
    backups: int = 5,
    logger: logging.Logger = None,
):
    """AI Generated -- `logger` parameter added by Claude (Anthropic).
    Attach a rotating, YAML-per-record file handler to `logger`
    (defaults to the root logger, unchanged from before this parameter
    existed -- Experiment's own logs.yaml relies on that default). Pass a
    dedicated logger (e.g. logging.getLogger("repl_history")) to keep a
    stream's records from mixing into the root logger's other handlers
    (error_collector included)."""
    target_logger = logger if logger is not None else logging.getLogger()

    target = Path(path).resolve()

    # --- remove existing YAML file handlers for this path ---
    for h in list(target_logger.handlers):
        if isinstance(h, RotatingFileHandler):
            try:
                if Path(h.baseFilename).resolve() == target:
                    target_logger.removeHandler(h)
                    h.close()
            except Exception:
                pass  # defensive: never break logging

    # --- create fresh handler ---
    handler = RotatingFileHandler(
        target,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backups,
        encoding="utf-8",
    )
    handler.setFormatter(YAMLStreamFormatter())

    target_logger.addHandler(handler)
    return target_logger
def close_yaml_logger(filename, logger):
    target_file = Path(filename).resolve()
    for h in logger.handlers[:]:
        if isinstance(h, logging.FileHandler):
            if Path(getattr(h, "baseFilename", "")).resolve() == target_file:
                logger.removeHandler(h)
                h.close()

