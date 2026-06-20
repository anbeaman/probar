import pytest

from probar.core.rate_limit import TokenBucket


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        TokenBucket(0)
    with pytest.raises(ValueError):
        TokenBucket(-1)


def test_acquire_more_than_capacity_raises():
    tb = TokenBucket(rate=5, capacity=2)
    with pytest.raises(ValueError):
        tb.acquire(3)


def test_low_rate_does_not_deadlock():
    # rate<1 时容量应被抬到至少 1,acquire(1) 才不会永久阻塞
    tb = TokenBucket(rate=0.5)
    assert tb.capacity >= 1
    tb.acquire(1)  # 初始令牌满桶,立即返回
