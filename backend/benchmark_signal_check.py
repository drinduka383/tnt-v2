"""Small, reproducible screening benchmark; no catalog scores are used."""
from collections import Counter
import json
import numpy as np

from src.services.signal_check import event_windows, repeat_result


def benchmark():
    rng = np.random.default_rng(142874279)
    period, duration, epoch = 3., .08, 2459501.
    time = 2459500. + np.arange(0., 23., .005)
    phase = (time - epoch + period / 2) % period - period / 2
    core = abs(phase) <= duration / 2
    totals = {}
    for case in ['transits', 'no_transits', 'gaps', 'noisy_transits', 'wrong_timing']:
        outcomes = Counter()
        for _ in range(30):
            noise = .025 if case == 'noisy_transits' else .001
            flux = 1. + rng.normal(0, noise, len(time))
            if case in ('transits', 'noisy_transits'):
                flux[core] *= .995
            if case == 'wrong_timing':
                flux[abs(phase - .30) <= duration / 2] *= .995
            keep = ~core if case == 'gaps' else np.ones(len(time), dtype=bool)
            t, f = time[keep], flux[keep]
            functional = event_windows(t, f, period, epoch, duration)
            injected = event_windows(t, f * np.where(core[keep], .995, 1.), period, epoch, duration)
            outcome = repeat_result(functional, 5000, injected)
            outcomes[outcome['status']] += 1
        totals[case] = dict(outcomes)
    return totals


if __name__ == '__main__':
    print(json.dumps(benchmark(), indent=2))
