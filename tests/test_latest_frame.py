import pytest

from handmusic.tracking.latest_frame import FrameStreamClosed, LatestFrameQueue


def test_latest_frame_replaces_stale_frame() -> None:
    queue: LatestFrameQueue[int] = LatestFrameQueue()
    queue.put(1)
    queue.put(2)
    assert queue.get() == 2


def test_closed_queue_rejects_put_and_unblocks_get() -> None:
    queue: LatestFrameQueue[int] = LatestFrameQueue()
    queue.close()
    with pytest.raises(FrameStreamClosed):
        queue.put(1)
    with pytest.raises(FrameStreamClosed):
        queue.get(timeout=0.01)


def test_empty_queue_times_out() -> None:
    queue: LatestFrameQueue[int] = LatestFrameQueue()
    with pytest.raises(TimeoutError):
        queue.get(timeout=0.001)
