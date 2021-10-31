# =========================================================================== #

import logging, datetime
def _fmtTime(self:   logging.Formatter,
             record: logging.LogRecord,
             datefmt: str | None = None):
    return  datetime.datetime.fromtimestamp(
            record.created,
            datetime.timezone.utc).astimezone().isoformat()

logging.Formatter.formatTime = _fmtTime


if __name__ == "__main__":
    from kotai.console.application import main
    import sys

    sys.exit(main())

# =========================================================================== #
