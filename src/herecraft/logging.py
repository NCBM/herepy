import logging
from logging import DEBUG, ERROR, INFO, WARN, Formatter, Handler, LogRecord
from typing import override

from com.mojang.logging import LogUtils
from org.slf4j import Logger as SLFLogger


class SLFLoggerHandler(Handler):
    java_logger: SLFLogger = LogUtils.getLogger()

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(Formatter("[%(name)s] %(message)s"))

    @override
    def emit(self, record: LogRecord) -> None:
        """
        Emit a log record by forwarding it to the Java SLF4J Logger.
        """
        # Map Python log levels to SLF4J log levels
        level = record.levelno
        message = self.format(record)

        if level >= ERROR:  # CRITICAL/ERROR
            self.java_logger.error(message)
        elif level >= WARN:  # WARNING
            self.java_logger.warn(message)
        elif level >= INFO:  # INFO
            self.java_logger.info(message)
        elif level >= DEBUG:  # DEBUG
            self.java_logger.debug(message)
        else:  # TRACE
            self.java_logger.trace(message)


# INFO rather than basicConfig's default WARNING: "this unit loaded" is an INFO record, and until the
# handler below existed those records went nowhere at all.
logging.basicConfig(level=INFO, handlers=(SLFLoggerHandler(),), force=True)
