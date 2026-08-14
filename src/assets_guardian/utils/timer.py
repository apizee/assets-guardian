import logging
import time

logger = logging.getLogger(__name__)


def start_timer() -> float:
    """ """
    return time.perf_counter()


def end_timer(_start: float) -> None:
    """ """
    elapsed = time.perf_counter() - _start
    #
    if elapsed >= 60:
        #
        minutes, seconds = divmod(elapsed, 60)
        duration = f"{int(minutes)}m {seconds:.1f}s"
    else:
        duration = f"{elapsed:.1f}s"
    logger.info("Completed in %s.", duration)
