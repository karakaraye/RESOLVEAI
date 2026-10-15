"""
Operational reporting and aggregate intelligence services for ResolveAI.
Implements real PostgreSQL queries for all seven BIIRS standard report types
with strict tenant isolation, verified vs. reported resolution segregation,
accurate denominators, and live data source freshness coverage.
"""

from datetime import datetime, timedelta, time
import logging
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Avg, Count, F, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.complaints.models import Complaint, ComplaintCategory
from apps.handoffs.models import ForwardingHandoff, ReceivingTeam
from apps.incidents.models import Incident, IncidentComplaint
from apps.tenants.models import DataSource, Tenant

logger = logging.getLogger(__name__)

REPORT_TYPES = {
    "OVERVIEW": "overview",
    "COMPLAINT_VOLUMES": "complaint-volumes",
    "RECURRING_ISSUES": "recurring-issues",
    "RESOLUTION_PERFORMANCE": "resolution-performance",
    "TEAM_RESPONSE_TIMES": "team-response-times",
    "OVERDUE_CASES": "overdue-cases",
    "INCIDENT_TRENDS": "incident-trends",
}

SLUG_TO_TYPE = {v: k for k, v in REPORT_TYPES.items()}


class ReportService:
    """
    Computes verified operational metrics, trends, and breakdowns
    across complaint lifecycle, handoffs, and incident intelligence.
    """

    @classmethod
    def get_report(
        cls,
        tenant: Tenant,
        report_slug: str,
        range_code: str = "30d",
        from_str: Optional[str] = None,
        to_str: Optional[str] = None,
    ) -> Dict[str, Any]:
        report_type = SLUG_TO_TYPE.get(report_slug.lower())
        if not report_type:
            raise ValidationError(f"Unknown report type '{report_slug}'.")

        start_dt, end_dt = cls._parse_date_range(range_code, from_str, to_str)
        coverage = cls._get_data_source_coverage(tenant)

        generators = {
            "OVERVIEW": cls._build_overview_report,
            "COMPLAINT_VOLUMES": cls._build_complaint_volumes_report,
            "RECURRING_ISSUES": cls._build_recurring_issues_report,
            "RESOLUTION_PERFORMANCE": cls._build_resolution_performance_report,
            "TEAM_RESPONSE_TIMES": cls._build_team_response_times_report,
            "OVERDUE_CASES": cls._build_overdue_cases_report,
            "INCIDENT_TRENDS": cls._build_incident_trends_report,
        }

        generator = generators[report_type]
        report_payload = generator(tenant, start_dt, end_dt)

        return {
            "type": report_type,
            "period": {
                "from": start_dt.date().isoformat(),
                "to": end_dt.date().isoformat(),
            },
            "coverage": coverage,
            "definitions": report_payload.get("definitions", []),
            "metrics": report_payload.get("metrics", []),
            "series": report_payload.get("series"),
            "rows": report_payload.get("rows"),
            "generatedAt": timezone.now().isoformat(),
        }

    # -------------------------------------------------------------------------
    # Helper: Date Range & Coverage
    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_date_range(
        range_code: str, from_str: Optional[str], to_str: Optional[str]
    ) -> Tuple[datetime, datetime]:
        now = timezone.now()

        if range_code == "custom":
            if not from_str or not to_str:
                raise ValidationError("Custom date range requires both 'from' and 'to' parameters.")
            try:
                from_date = datetime.strptime(from_str, "%Y-%m-%d").date()
                to_date = datetime.strptime(to_str, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationError("Dates must be formatted as YYYY-MM-DD.")
            if from_date > to_date:
                raise ValidationError("The start date must be on or before the end date.")
            
            tz = timezone.get_current_timezone()
            start_dt = timezone.make_aware(datetime.combine(from_date, time.min), tz)
            end_dt = timezone.make_aware(datetime.combine(to_date, time.max), tz)
            return start_dt, end_dt

        days_map = {"7d": 7, "30d": 30, "90d": 90}
        days = days_map.get(range_code, 30)
        start_dt = now - timedelta(days=days)
        end_dt = now
        return start_dt, end_dt

    @staticmethod
    def _get_data_source_coverage(tenant: Tenant) -> Dict[str, Any]:
        data_sources = DataSource.objects.filter(tenant=tenant).order_by("name")
        sources_list = []
        stale_or_unavailable = 0

        for ds in data_sources:
            sources_list.append({
                "name": ds.name,
                "status": ds.status,
                "lastUpdatedAt": ds.last_updated_at.isoformat() if ds.last_updated_at else None,
            })
            if ds.status != DataSource.Status.AVAILABLE:
                stale_or_unavailable += 1

        is_complete = stale_or_unavailable == 0
        note = None
        if not is_complete:
            note = f"{stale_or_unavailable} data source(s) are stale or unavailable; reported metrics may represent partial data."

        return {
            "complete": is_complete,
            "note": note,
            "sources": sources_list,
        }

    @staticmethod
    def _generate_daily_series(
        start_dt: datetime, end_dt: datetime, counts_by_date: Dict[str, int], label: str
    ) -> Dict[str, Any]:
        points = []
        cur_date = start_dt.date()
        end_date = end_dt.date()

        while cur_date <= end_date:
            date_key = cur_date.isoformat()
            points.append({
                "date": date_key,
                "value": counts_by_date.get(date_key, 0),
            })
            cur_date += timedelta(days=1)

        return {
            "label": label,
            "points": points,
        }

    # -------------------------------------------------------------------------
    # 1. OVERVIEW
    # -------------------------------------------------------------------------
    @classmethod
    def _build_overview_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        complaints_qs = Complaint.objects.filter(tenant=tenant)
        received_in_period = complaints_qs.filter(received_at__gte=start_dt, received_at__lte=end_dt)
        total_received = received_in_period.count()

        active_statuses = [
            Complaint.Status.NEW,
            Complaint.Status.NEEDS_ACTION,
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.FORWARDED,
            Complaint.Status.AWAITING_VERIFICATION,
            Complaint.Status.REOPENED,
        ]
        active_count = complaints_qs.filter(status__in=active_statuses).count()

        # Independently verified resolutions in period
        verified_resolved_qs = complaints_qs.filter(
            status=Complaint.Status.RESOLVED,
            resolution_verification=Complaint.ResolutionVerification.VERIFIED,
            resolution_verified_at__gte=start_dt,
            resolution_verified_at__lte=end_dt,
        )
        verified_resolved_count = verified_resolved_qs.count()

        # Pending unverified resolutions
        pending_verification_count = complaints_qs.filter(
            status=Complaint.Status.AWAITING_VERIFICATION
        ).count()

        # Resolution rate: verified resolutions vs total closed or outcome-reported cases
        total_outcomes = complaints_qs.filter(
            Q(resolution_reported_at__isnull=False) | Q(status__in=[Complaint.Status.RESOLVED, Complaint.Status.AWAITING_VERIFICATION]),
            received_at__gte=start_dt,
            received_at__lte=end_dt,
        ).count()
        resolution_rate = round(100.0 * verified_resolved_count / total_outcomes, 1) if total_outcomes > 0 else None

        # Mean resolution latency (verified only)
        verified_cases = verified_resolved_qs.exclude(resolution_verified_at__isnull=True).exclude(received_at__isnull=True)
        durations = [
            (c.resolution_verified_at - c.received_at).total_seconds() / 3600.0
            for c in verified_cases
            if c.resolution_verified_at > c.received_at
        ]
        avg_res_hours = round(sum(durations) / len(durations), 1) if durations else None

        # Daily series
        daily_counts = (
            received_in_period
            .annotate(day=TruncDate("received_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in daily_counts if row["day"]}
        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, "Complaints received per day")

        # Breakdown by channel
        channel_counts = (
            received_in_period
            .values("source_channel")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        channel_items = []
        for ch in channel_counts:
            ch_name = ch["source_channel"] or "Unknown"
            cnt = ch["cnt"]
            pct = f"{round(100.0 * cnt / total_received, 1)}% of total" if total_received > 0 else "0%"
            channel_items.append({
                "label": ch_name,
                "value": cnt,
                "secondary": pct,
                "filter": f"channel={ch_name}",
            })

        return {
            "definitions": [
                {"term": "Total Ingested", "meaning": "All complaints received into the system within the selected time window."},
                {"term": "Verified Resolved", "meaning": "Complaints with an outcome independently reviewed and approved by a designated verifier."},
                {"term": "Pending Verification", "meaning": "Complaints where an operator proposed a resolution awaiting independent maker-checker review."},
                {"term": "Active Workload", "meaning": "Cases currently needing action, under investigation, forwarded, or awaiting verification."},
                {"term": "Verified Resolution Rate", "meaning": "Percentage of closed outcomes verified as resolved against total outcomes reported."},
            ],
            "metrics": [
                {"key": "total_received", "label": "Complaints received", "value": total_received, "unit": "count", "filter": "status=ALL"},
                {"key": "active_cases", "label": "Active cases", "value": active_count, "unit": "count", "filter": "status=IN_PROGRESS"},
                {"key": "verified_resolved", "label": "Verified resolved", "value": verified_resolved_count, "unit": "count", "filter": "status=RESOLVED"},
                {"key": "pending_verification", "label": "Pending verification", "value": pending_verification_count, "unit": "count", "filter": "status=AWAITING_VERIFICATION"},
                {"key": "verified_rate", "label": "Verified resolution rate", "value": resolution_rate, "unit": "percent"},
                {"key": "avg_res_time", "label": "Avg verified resolution time", "value": avg_res_hours, "unit": "hours"},
            ],
            "series": series,
            "rows": {
                "heading": "Complaints by Intake Channel",
                "valueLabel": "complaints",
                "items": channel_items,
            },
        }

    # -------------------------------------------------------------------------
    # 2. COMPLAINT VOLUMES
    # -------------------------------------------------------------------------
    @classmethod
    def _build_complaint_volumes_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        received_qs = Complaint.objects.filter(
            tenant=tenant, received_at__gte=start_dt, received_at__lte=end_dt
        )
        total_received = received_qs.count()
        num_days = max(1, (end_dt.date() - start_dt.date()).days + 1)
        daily_avg = round(total_received / float(num_days), 1)

        daily_counts = (
            received_qs
            .annotate(day=TruncDate("received_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in daily_counts if row["day"]}
        peak_volume = max(counts_dict.values()) if counts_dict else 0

        reopened_count = Complaint.objects.filter(
            tenant=tenant, status=Complaint.Status.REOPENED, updated_at__gte=start_dt, updated_at__lte=end_dt
        ).count()

        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, "Daily complaint intake")

        channel_counts = (
            received_qs
            .values("source_channel")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        channel_items = [
            {
                "label": ch["source_channel"] or "Unknown",
                "value": ch["cnt"],
                "secondary": f"{round(100.0 * ch['cnt'] / total_received, 1)}%" if total_received > 0 else "0%",
                "filter": f"channel={ch['source_channel'] or ''}",
            }
            for ch in channel_counts
        ]

        return {
            "definitions": [
                {"term": "Total Volume", "meaning": "Net new complaints ingested across all integrated banking channels."},
                {"term": "Daily Ingestion Rate", "meaning": "Average number of customer disputes logged per calendar day in the period."},
                {"term": "Peak Daily Volume", "meaning": "Highest number of complaints received on any single day within the selected window."},
                {"term": "Reopened Volume", "meaning": "Complaints that were reopened following customer dispute or newly submitted evidence."},
            ],
            "metrics": [
                {"key": "total_received", "label": "Total complaints received", "value": total_received, "unit": "count"},
                {"key": "daily_avg", "label": "Daily average", "value": daily_avg, "unit": "count"},
                {"key": "peak_volume", "label": "Peak daily intake", "value": peak_volume, "unit": "count"},
                {"key": "reopened_count", "label": "Reopened cases", "value": reopened_count, "unit": "count", "filter": "status=REOPENED"},
            ],
            "series": series,
            "rows": {
                "heading": "Complaint Volume by Channel",
                "valueLabel": "complaints",
                "items": channel_items,
            },
        }

    # -------------------------------------------------------------------------
    # 3. RECURRING ISSUES
    # -------------------------------------------------------------------------
    @classmethod
    def _build_recurring_issues_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        complaints_in_period = Complaint.objects.filter(
            tenant=tenant, received_at__gte=start_dt, received_at__lte=end_dt
        )
        total_count = complaints_in_period.count()

        category_breakdown = (
            complaints_in_period
            .values("category__code", "category__label")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        distinct_categories = len(category_breakdown)
        top_cat = category_breakdown[0] if category_breakdown else None
        top_cat_share = round(100.0 * top_cat["cnt"] / total_count, 1) if (top_cat and total_count > 0) else None

        active_incidents_count = Incident.objects.filter(
            tenant=tenant,
            status__in=[Incident.Status.CANDIDATE, Incident.Status.INVESTIGATING, Incident.Status.CONFIRMED],
        ).count()

        repeat_customers_count = (
            complaints_in_period
            .values("customer_id")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .count()
        )

        # Series: trend for the top recurring category
        top_cat_code = top_cat["category__code"] if top_cat else None
        top_cat_label = top_cat["category__label"] if top_cat else "No categories"
        series_label = f"Daily trend: {top_cat_label}"

        top_cat_daily = (
            complaints_in_period
            .filter(category__code=top_cat_code)
            .annotate(day=TruncDate("received_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        ) if top_cat_code else []
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in top_cat_daily if row["day"]}
        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, series_label)

        rows_items = []
        for cat in category_breakdown:
            label = cat["category__label"] or "Uncategorized"
            cnt = cat["cnt"]
            pct = f"{round(100.0 * cnt / total_count, 1)}% of total" if total_count > 0 else "0%"
            code = cat["category__code"] or ""
            rows_items.append({
                "label": label,
                "value": cnt,
                "secondary": pct,
                "filter": f"category={code}" if code else "",
            })

        return {
            "definitions": [
                {"term": "Category Concentration", "meaning": "Proportion of total complaint volume represented by the single largest recurring category."},
                {"term": "Recurring Categories", "meaning": "Number of distinct complaint categories with at least one customer complaint in the period."},
                {"term": "Emerging Incidents", "meaning": "Active or candidate incident clusters linking multiple customer complaints sharing common failure signatures."},
                {"term": "Repeat Inquiries", "meaning": "Number of distinct customers filing more than one complaint in the selected period."},
            ],
            "metrics": [
                {"key": "distinct_categories", "label": "Categories affected", "value": distinct_categories, "unit": "count"},
                {"key": "top_cat_share", "label": "Top category concentration", "value": top_cat_share, "unit": "percent"},
                {"key": "active_incidents", "label": "Emerging incident clusters", "value": active_incidents_count, "unit": "count"},
                {"key": "repeat_customers", "label": "Customers with repeat disputes", "value": repeat_customers_count, "unit": "count"},
            ],
            "series": series,
            "rows": {
                "heading": "Recurring Complaints by Issue Category",
                "valueLabel": "cases",
                "items": rows_items,
            },
        }

    # -------------------------------------------------------------------------
    # 4. RESOLUTION PERFORMANCE
    # -------------------------------------------------------------------------
    @classmethod
    def _build_resolution_performance_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        complaints_qs = Complaint.objects.filter(tenant=tenant)

        verified_qs = complaints_qs.filter(
            status=Complaint.Status.RESOLVED,
            resolution_verification=Complaint.ResolutionVerification.VERIFIED,
            resolution_verified_at__gte=start_dt,
            resolution_verified_at__lte=end_dt,
        )
        verified_count = verified_qs.count()

        pending_verification_count = complaints_qs.filter(
            status=Complaint.Status.AWAITING_VERIFICATION
        ).count()

        # Maker-checker verification lag
        lags = []
        for c in verified_qs:
            if c.resolution_verified_at and c.resolution_reported_at and c.resolution_verified_at >= c.resolution_reported_at:
                lags.append((c.resolution_verified_at - c.resolution_reported_at).total_seconds() / 3600.0)
        avg_lag_hours = round(sum(lags) / len(lags), 1) if lags else None

        # SLA Compliance: verified on-time before due_at
        with_sla = [c for c in verified_qs if c.due_at and c.resolution_verified_at]
        on_time = [c for c in with_sla if c.resolution_verified_at <= c.due_at]
        sla_pct = round(100.0 * len(on_time) / len(with_sla), 1) if with_sla else None

        # Series: daily verified resolutions
        daily_verified = (
            verified_qs
            .annotate(day=TruncDate("resolution_verified_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in daily_verified if row["day"]}
        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, "Daily verified resolutions")

        # Rows: verified resolutions grouped by resolution outcome summary or category
        cat_breakdown = (
            verified_qs
            .values("category__label")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        rows_items = [
            {
                "label": cat["category__label"] or "General Resolution",
                "value": cat["cnt"],
                "secondary": f"{round(100.0 * cat['cnt'] / verified_count, 1)}% verified" if verified_count > 0 else "0%",
                "filter": "status=RESOLVED",
            }
            for cat in cat_breakdown
        ]

        return {
            "definitions": [
                {"term": "Verified Resolutions", "meaning": "Cases independently reviewed and approved by an authorized verifier (Maker-Checker Segregation)."},
                {"term": "Reported Pending", "meaning": "Cases where an operator recorded a resolution outcome, but independent verification has not occurred."},
                {"term": "Maker-Checker Lag", "meaning": "Mean duration from initial outcome recording by the maker until verification approval by the checker."},
                {"term": "SLA Met", "meaning": "Percentage of verified resolutions completed before the mandated resolution due timestamp."},
            ],
            "metrics": [
                {"key": "verified_resolutions", "label": "Verified resolutions", "value": verified_count, "unit": "count", "filter": "status=RESOLVED"},
                {"key": "pending_verification", "label": "Pending verification", "value": pending_verification_count, "unit": "count", "filter": "status=AWAITING_VERIFICATION"},
                {"key": "avg_verification_lag", "label": "Avg maker-checker lag", "value": avg_lag_hours, "unit": "hours"},
                {"key": "sla_compliance", "label": "Verified SLA compliance", "value": sla_pct, "unit": "percent"},
            ],
            "series": series,
            "rows": {
                "heading": "Verified Resolutions by Category",
                "valueLabel": "resolutions",
                "items": rows_items,
            },
        }

    # -------------------------------------------------------------------------
    # 5. TEAM RESPONSE TIMES
    # -------------------------------------------------------------------------
    @classmethod
    def _build_team_response_times_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        handoffs_in_period = ForwardingHandoff.objects.filter(
            tenant=tenant, created_at__gte=start_dt, created_at__lte=end_dt
        ).select_related("team")
        total_handoffs = handoffs_in_period.count()

        ack_durations = [
            max(0.0, (h.acknowledged_at - h.created_at).total_seconds() / 3600.0)
            for h in handoffs_in_period
            if h.acknowledged_at is not None
        ]
        avg_ack_hours = round(sum(ack_durations) / len(ack_durations), 1) if ack_durations else None

        resp_durations = [
            max(0.0, (h.responded_at - h.created_at).total_seconds() / 3600.0)
            for h in handoffs_in_period
            if h.responded_at is not None
        ]
        avg_resp_hours = round(sum(resp_durations) / len(resp_durations), 1) if resp_durations else None

        now = timezone.now()
        breached_count = handoffs_in_period.filter(
            Q(state=ForwardingHandoff.State.OVERDUE)
            | Q(response_due_at__lt=now, responded_at__isnull=True)
            | Q(responded_at__gt=F("response_due_at"))
        ).count()

        # Series: daily forwarded handoffs
        daily_handoffs = (
            handoffs_in_period
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in daily_handoffs if row["day"]}
        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, "Daily forwarded handoffs")

        # Rows: performance by receiving team
        teams = ReceivingTeam.objects.filter(tenant=tenant)
        rows_items = []
        for tm in teams:
            team_handoffs = [h for h in handoffs_in_period if h.team_id == tm.id]
            cnt = len(team_handoffs)
            team_resp_durations = [
                (h.responded_at - h.created_at).total_seconds() / 3600.0
                for h in team_handoffs
                if h.responded_at and h.responded_at >= h.created_at
            ]
            team_avg_resp = round(sum(team_resp_durations) / len(team_resp_durations), 1) if team_resp_durations else None
            sec_text = f"{cnt} handoffs · {team_avg_resp}h avg" if team_avg_resp is not None else f"{cnt} handoffs · pending response"
            rows_items.append({
                "label": tm.name,
                "value": team_avg_resp if team_avg_resp is not None else (cnt if cnt > 0 else None),
                "secondary": sec_text,
                "filter": "",
            })

        return {
            "definitions": [
                {"term": "Forwarded Handoffs", "meaning": "Complaints dispatched to operational receiving teams (e.g. Card Operations, Settlement)."},
                {"term": "Acknowledgement Time", "meaning": "Elapsed duration from handoff creation until receiving team registers receipt."},
                {"term": "Response Time", "meaning": "Elapsed duration from handoff creation until receiving team returns substantive findings or action."},
                {"term": "Breached Handoffs", "meaning": "Handoffs that surpassed SLA response deadline before receiving team response."},
            ],
            "metrics": [
                {"key": "total_handoffs", "label": "Total forwarded handoffs", "value": total_handoffs, "unit": "count"},
                {"key": "avg_ack_hours", "label": "Avg acknowledgement time", "value": avg_ack_hours, "unit": "hours"},
                {"key": "avg_resp_hours", "label": "Avg operational response time", "value": avg_resp_hours, "unit": "hours"},
                {"key": "breached_handoffs", "label": "SLA breached handoffs", "value": breached_count, "unit": "count"},
            ],
            "series": series,
            "rows": {
                "heading": "Response Turnaround by Receiving Team",
                "valueLabel": "hours",
                "items": rows_items,
            },
        }

    # -------------------------------------------------------------------------
    # 6. OVERDUE CASES
    # -------------------------------------------------------------------------
    @classmethod
    def _build_overdue_cases_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        now = timezone.now()
        complaints_qs = Complaint.objects.filter(tenant=tenant)

        # Active unresolved cases that are overdue
        overdue_qs = complaints_qs.filter(
            due_at__lt=now
        ).exclude(
            status=Complaint.Status.RESOLVED
        )
        total_overdue = overdue_qs.count()

        active_count = complaints_qs.exclude(status=Complaint.Status.RESOLVED).count()
        overdue_rate = round(100.0 * total_overdue / active_count, 1) if active_count > 0 else 0.0

        critical_overdue = overdue_qs.filter(priority=Complaint.Priority.CRITICAL).count()

        # Maximum overdue latency
        overdue_latencies = [
            (now - c.due_at).total_seconds() / 3600.0
            for c in overdue_qs
            if c.due_at and now > c.due_at
        ]
        max_overdue_hours = round(max(overdue_latencies), 1) if overdue_latencies else None

        # Series: cases past due in the period
        daily_overdue = (
            overdue_qs
            .filter(due_at__gte=start_dt, due_at__lte=end_dt)
            .annotate(day=TruncDate("due_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in daily_overdue if row["day"]}
        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, "Cases breaching SLA by deadline")

        # Rows: Overdue cases by category
        cat_overdue = (
            overdue_qs
            .values("category__code", "category__label")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
        )
        rows_items = [
            {
                "label": cat["category__label"] or "Uncategorized",
                "value": cat["cnt"],
                "secondary": f"{round(100.0 * cat['cnt'] / total_overdue, 1)}% of overdue" if total_overdue > 0 else "0%",
                "filter": f"category={cat['category__code'] or ''}",
            }
            for cat in cat_overdue
        ]

        return {
            "definitions": [
                {"term": "Overdue Case", "meaning": "Complaint where current time has exceeded due_at without verified resolution."},
                {"term": "Overdue Rate", "meaning": "Proportion of all active open complaints currently in SLA breach."},
                {"term": "Critical Overdue", "meaning": "Overdue cases categorized with CRITICAL priority rating."},
                {"term": "Max Latency", "meaning": "Elapsed time past SLA deadline for the single most overdue open complaint."},
            ],
            "metrics": [
                {"key": "total_overdue", "label": "Total overdue complaints", "value": total_overdue, "unit": "count"},
                {"key": "overdue_rate", "label": "Overdue rate", "value": overdue_rate, "unit": "percent"},
                {"key": "critical_overdue", "label": "Critical overdue cases", "value": critical_overdue, "unit": "count"},
                {"key": "max_overdue_hours", "label": "Longest overdue latency", "value": max_overdue_hours, "unit": "hours"},
            ],
            "series": series,
            "rows": {
                "heading": "Overdue Cases by Category",
                "valueLabel": "cases",
                "items": rows_items,
            },
        }

    # -------------------------------------------------------------------------
    # 7. INCIDENT TRENDS
    # -------------------------------------------------------------------------
    @classmethod
    def _build_incident_trends_report(cls, tenant: Tenant, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
        incidents_qs = Incident.objects.filter(tenant=tenant)
        active_incidents = incidents_qs.filter(
            status__in=[Incident.Status.CANDIDATE, Incident.Status.INVESTIGATING, Incident.Status.CONFIRMED]
        )
        active_count = active_incidents.count()

        resolved_count = incidents_qs.filter(
            status=Incident.Status.RESOLVED, updated_at__gte=start_dt, updated_at__lte=end_dt
        ).count()

        # Complaints linked to incidents in period
        links_in_period = IncidentComplaint.objects.filter(
            tenant=tenant, associated_at__gte=start_dt, associated_at__lte=end_dt
        )
        linked_complaints_count = links_in_period.count()

        avg_blast_radius = (
            round(linked_complaints_count / float(active_count), 1) if active_count > 0 else None
        )

        # Series: daily complaints linked to incidents
        daily_links = (
            links_in_period
            .annotate(day=TruncDate("associated_at"))
            .values("day")
            .annotate(cnt=Count("id"))
            .order_by("day")
        )
        counts_dict = {row["day"].isoformat(): row["cnt"] for row in daily_links if row["day"]}
        series = cls._generate_daily_series(start_dt, end_dt, counts_dict, "Complaints linked to incidents per day")

        # Rows: active and recent incidents by linked complaints
        incidents_with_counts = (
            incidents_qs
            .annotate(linked_cnt=Count("complaint_associations"))
            .order_by("-linked_cnt", "-created_at")[:10]
        )
        rows_items = [
            {
                "label": f"{inc.reference}: {inc.title}",
                "value": inc.linked_cnt,
                "secondary": f"Severity: {inc.severity} · Status: {inc.get_status_display()}",
                "filter": f"incident={inc.reference}",
            }
            for inc in incidents_with_counts
        ]

        return {
            "definitions": [
                {"term": "Active Incidents", "meaning": "Confirmed or candidate incidents currently under active investigation or mitigation."},
                {"term": "Linked Complaints", "meaning": "Customer complaints tied to a detected common root cause without collapsing complaint records."},
                {"term": "Average Blast Radius", "meaning": "Mean number of customer complaints linked per identified incident."},
                {"term": "Resolved Incidents", "meaning": "Systemic failure incidents marked as resolved within the selected period."},
            ],
            "metrics": [
                {"key": "active_incidents", "label": "Active emerging incidents", "value": active_count, "unit": "count"},
                {"key": "linked_complaints", "label": "Complaints linked to incidents", "value": linked_complaints_count, "unit": "count"},
                {"key": "avg_blast_radius", "label": "Avg complaints per incident", "value": avg_blast_radius, "unit": "count"},
                {"key": "resolved_incidents", "label": "Resolved incidents", "value": resolved_count, "unit": "count"},
            ],
            "series": series,
            "rows": {
                "heading": "Incidents by Blast Radius (Linked Cases)",
                "valueLabel": "linked cases",
                "items": rows_items,
            },
        }
