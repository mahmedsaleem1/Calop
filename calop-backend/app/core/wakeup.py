"""A shared event the worker threads wait on. Request threads call wake() after queueing a job."""
import threading

job_available = threading.Event()


def wake() -> None:
    job_available.set()
