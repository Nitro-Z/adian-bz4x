"""Budget kill switch: when the budget notification says cost >= budget, disable billing on the project.

Triggered by the Pub/Sub topic `budget-kill` that the 6,000 TWD budget publishes to.
Disabling billing stops every paid service in the project (Cloud Run, VMs, Vertex AI). To resume:
  gcloud billing projects link <PROJECT_ID> --billing-account=<BILLING_ACCOUNT_ID>
A message attribute dryRun=1 only logs what would happen (used for testing).
"""
import base64, json, os
import functions_framework
from googleapiclient import discovery

PROJECT_NAME = f"projects/{os.environ['TARGET_PROJECT']}"


@functions_framework.cloud_event
def stop_billing(cloud_event):
    msg = cloud_event.data["message"]
    attrs = msg.get("attributes") or {}
    data = json.loads(base64.b64decode(msg["data"]).decode())
    cost, budget = float(data.get("costAmount", 0)), float(data.get("budgetAmount", 0))
    dry = attrs.get("dryRun") == "1"
    print(json.dumps({"cost": cost, "budget": budget, "currency": data.get("currencyCode"), "dryRun": dry}))
    if budget <= 0 or cost < budget:
        print("under budget, nothing to do")
        return
    billing = discovery.build("cloudbilling", "v1", cache_discovery=False)
    info = billing.projects().getBillingInfo(name=PROJECT_NAME).execute()
    if not info.get("billingEnabled"):
        print("billing already disabled")
        return
    if dry:
        print(f"DRY RUN: would disable billing for {PROJECT_NAME}")
        return
    billing.projects().updateBillingInfo(name=PROJECT_NAME, body={"billingAccountName": ""}).execute()
    print(f"BILLING DISABLED for {PROJECT_NAME}: cost {cost} >= budget {budget}")
