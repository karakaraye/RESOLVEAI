import time
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from config.celery import debug_task
from apps.handoffs.models import ForwardingHandoff
from apps.handoffs.tasks import dispatch_handoff_task
from apps.intelligence.tasks import process_complaint_intelligence_task
from apps.complaints.models import Complaint

print("Testing Celery async worker...")

# 1. Debug task
res1 = debug_task.delay()
print("Dispatched debug_task. Task ID:", res1.id)

# 2. Handoff dispatch task
handoff = ForwardingHandoff.objects.first()
if handoff:
    print(f"Testing dispatch for handoff {handoff.id} [{handoff.state}]...")
    res2 = dispatch_handoff_task.delay(str(handoff.id))
    print("Dispatched dispatch_handoff_task. Task ID:", res2.id)

    # Poll for async result from worker
    for i in range(10):
        time.sleep(1)
        if res2.ready():
            print("Worker completed dispatch_handoff_task! Result:", res2.result)
            break
        print(f"Waiting for worker... ({i+1}s)")

# 3. AI intelligence task
comp = Complaint.objects.first()
if comp:
    print(f"Testing AI pipeline task for complaint {comp.reference}...")
    res3 = process_complaint_intelligence_task.delay(str(comp.id), force_refresh=False)
    print("Dispatched process_complaint_intelligence_task. Task ID:", res3.id)
    for i in range(10):
        time.sleep(1)
        if res3.ready():
            print("Worker completed process_complaint_intelligence_task! Result:", res3.result)
            break
        print(f"Waiting for AI worker... ({i+1}s)")
