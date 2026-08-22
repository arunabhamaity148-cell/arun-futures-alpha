"""Tests for RingBuffer."""
import threading

from trader_arun.core.ringbuffer import RingBuffer


def test_ringbuffer_bounded():
    rb = RingBuffer(maxlen=3)
    for i in range(10):
        rb.append(i)
    assert len(rb) == 3
    assert rb.snapshot() == [7, 8, 9]


def test_ringbuffer_last():
    rb = RingBuffer(maxlen=5)
    rb.append(10)
    rb.append(20)
    assert rb.last() == 20


def test_ringbuffer_latest_n():
    rb = RingBuffer(maxlen=5)
    for i in range(5):
        rb.append(i)
    assert rb.latest(2) == [3, 4]
    assert rb.latest(0) == []
    assert rb.latest(10) == [0, 1, 2, 3, 4]


def test_ringbuffer_clear():
    rb = RingBuffer(maxlen=5)
    rb.extend([1, 2, 3])
    assert len(rb) == 3
    rb.clear()
    assert len(rb) == 0


def test_ringbuffer_threadsafe():
    rb = RingBuffer(maxlen=1000)

    def producer():
        for i in range(1000):
            rb.append(i)

    threads = [threading.Thread(target=producer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(rb) == 1000  # exactly maxlen


def test_ringbuffer_invalid_maxlen():
    import pytest
    with pytest.raises(ValueError):
        RingBuffer(maxlen=0)
    with pytest.raises(ValueError):
        RingBuffer(maxlen=-1)
