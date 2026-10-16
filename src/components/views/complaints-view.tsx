"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import { useResource } from "@/lib/use-resource";
import { useUrlState } from "@/lib/use-url-state";
import { ComplaintRegister } from "../complaint-register";
import { PageHeader } from "../ui";
import { WorkloadStrip } from "../workload-strip";

export function ComplaintsView() {
  return (
    <>
      <PageHeader
        title="Complaints"
        description="Every complaint you’re allowed to see, from your bank’s approved channels."
        actions={
          <Link href="/complaints/new" className="button button-primary">
            <Plus size={16} aria-hidden="true" />
            <span>Log New Complaint</span>
          </Link>
        }
      />
      <ComplaintRegister scope="all" searchLabel="Search by reference, customer or issue" />
    </>
  );
}

export function MyCasesView() {
  const summary = useResource("summary:mine", (signal) => api.workspaceSummary("mine", signal));
  const { params } = useUrlState();
  const status = params.get("status");
  const due = params.get("due");
  const counts = summary.state === "ready" ? summary.data.counts : null;

  return (
    <>
      <PageHeader title="My cases" description="Cases assigned to you for review, investigation or follow-up." />
      {counts && (
        <WorkloadStrip label="Your workload" items={[
          { label: "Total assigned", value: counts.totalAssigned ?? 0, href: "/my-cases", current: !status && !due },
          { label: "Needs action", value: counts.needsAttention, href: "/my-cases?status=NEEDS_ACTION", tone: "warning", current: status === "NEEDS_ACTION" },
          { label: "Overdue", value: counts.overdue, href: "/my-cases?due=overdue", tone: "danger", current: due === "overdue" },
          { label: "In progress", value: counts.inProgress, href: "/my-cases?status=IN_PROGRESS", current: status === "IN_PROGRESS" },
          { label: "Awaiting verification", value: counts.awaitingVerification, href: "/my-cases?status=AWAITING_VERIFICATION", tone: "verify", current: status === "AWAITING_VERIFICATION" },
        ]} />
      )}
      <ComplaintRegister scope="mine" searchLabel="Search your cases" />
    </>
  );
}
