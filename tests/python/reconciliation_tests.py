import threading
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def reconcile(self, *, service_name=None, allow_recovery=False):
        self.calls.append((service_name, allow_recovery))
        return {"service": service_name, "allow_recovery": allow_recovery, "status": "observed"}


def test_reconciler_is_bounded_and_preserves_policy():
    from rift.reconciliation import ReconcilePolicy, RiftReconciler

    orchestrator = FakeOrchestrator()
    reports = []
    reconciler = RiftReconciler(
        orchestrator,
        policy=ReconcilePolicy(interval_seconds=0.001, allow_recovery=True, max_iterations=2),
        on_report=reports.append,
    )
    result = reconciler.run(threading.Event(), service_name="chat")
    assert result["iterations_completed"] == 2
    assert len(orchestrator.calls) == 2
    assert all(call == ("chat", True) for call in orchestrator.calls)
    assert len(reports) == 2


def test_reconcile_policy_rejects_unsafe_values():
    from rift.reconciliation import ReconcilePolicy

    for kwargs in ({"interval_seconds": 0}, {"max_iterations": -1}):
        try:
            ReconcilePolicy(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid policy accepted: {kwargs}")


if __name__ == "__main__":
    test_reconciler_is_bounded_and_preserves_policy()
    test_reconcile_policy_rejects_unsafe_values()
    print("reconciliation_tests: PASS")
