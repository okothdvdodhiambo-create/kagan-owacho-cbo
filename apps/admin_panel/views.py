"""The custom admin dashboard: everything the committee needs, no code editing."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import admin_required
from apps.accounts.models import User
from apps.communications.forms import EmailCampaignForm
from apps.communications.models import ContactMessage, EmailCampaign
from apps.communications.services import broadcast_event_report, deliver_campaign
from apps.contributions.models import Contribution
from apps.contributions.services import mark_confirmed, mark_rejected
from apps.core.forms import NavItemForm, SiteSettingsForm, SliderImageForm, SocialLinkForm
from apps.core.models import AuditLog, NavItem, SiteSettings, SliderImage, SocialLink
from apps.events.forms import EventForm, EventReportForm, EventReportPhotoForm
from apps.events.models import Event, EventReport, EventReportPhoto
from apps.incidents.forms import IncidentStatusForm
from apps.incidents.models import Incident, IncidentResponse
from apps.membership.forms import MemberDetailsForm
from apps.membership.models import DropdownOption, Member

from . import exports
from .forms import ContributionDecisionForm, DropdownOptionForm, IncidentResponseForm

PAGE_SIZE = 20


def _paginate(request, queryset, size=PAGE_SIZE):
    paginator = Paginator(queryset, size)
    return paginator.get_page(request.GET.get("page"))


# ----------------------------------------------------------------- 1. overview
@admin_required
def dashboard(request):
    from apps.incidents.models import Incident as IncidentModel

    now = timezone.now()
    month_start = timezone.localdate().replace(day=1)
    members = Member.objects.all()
    contributions = Contribution.objects.all()
    context = {
        "page_title": "Admin dashboard",
        "active_section": "overview",
        "stats": {
            "members_total": members.count(),
            "members_active": members.filter(status=Member.Status.ACTIVE).count(),
            "members_pending": members.filter(verified=False).count(),
            "contributions_ksh": float(contributions.filter(status=Contribution.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or 0),
            "month_ksh": float(
                contributions.filter(status=Contribution.Status.CONFIRMED, created_at__date__gte=month_start).aggregate(s=Sum("amount"))["s"] or 0
            ),
            "pending_verifications": contributions.filter(
                status__in=[Contribution.Status.PENDING, Contribution.Status.WAITING]
            ).count(),
            "new_incidents": IncidentModel.objects.filter(status=IncidentModel.Status.NEW).count(),
            "events": Event.objects.count(),
            "contact_unread": ContactMessage.objects.filter(handled=False).count(),
        },
        "recent_members": members.order_by("-created_at")[:6],
        "recent_contributions": contributions.select_related("member")[:6],
        "recent_incidents": IncidentModel.objects.select_related("member")[:5],
        "mpesa_live": _mpesa_live(),
        "this_month_label": month_start.strftime("%B %Y"),
    }
    return render(request, "admin_panel/overview.html", context)


def _mpesa_live():
    from apps.contributions.daraja import get_client

    return get_client().configured


# ------------------------------------------------------------- 2 & 3. members
@admin_required
def member_list(request):
    queryset = Member.objects.select_related("user")
    search = (request.GET.get("q") or "").strip()
    status = request.GET.get("status") or ""
    role = request.GET.get("role") or ""
    gender = request.GET.get("gender") or ""
    verified = request.GET.get("verified") or ""
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
            | Q(membership_no__icontains=search)
            | Q(location__icontains=search)
        )
    if status:
        queryset = queryset.filter(status=status)
    if role:
        queryset = queryset.filter(role=role)
    if gender:
        queryset = queryset.filter(gender=gender)
    if verified == "yes":
        queryset = queryset.filter(verified=True)
    elif verified == "no":
        queryset = queryset.filter(verified=False)
    fmt = request.GET.get("export")
    if fmt in ("csv", "xlsx"):
        return exports.export_members(queryset, fmt)
    context = {
        "page_title": "Registered members",
        "active_section": "members",
        "members": _paginate(request, queryset),
        "statuses": Member.Status.choices,
        "roles": DropdownOption.objects.filter(field=DropdownOption.Field.ROLE, active=True),
        "genders": DropdownOption.objects.filter(field=DropdownOption.Field.GENDER, active=True),
        "search": search,
        "selected_status": status,
        "selected_role": role,
        "selected_gender": gender,
        "selected_verified": verified,
        "accounts_without_membership": User.objects.filter(is_admin=False, profile__isnull=True).count(),
        "total_value": float(
            Contribution.objects.filter(member__in=queryset, status=Contribution.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or 0
        ),
    }
    return render(request, "admin_panel/member_list.html", context)


@admin_required
def member_detail(request, pk):
    member = get_object_or_404(Member.objects.select_related("user"), pk=pk)
    form = MemberDetailsForm(request.POST or None, instance=member)
    if request.method == "POST" and "action" in request.POST:
        return _member_action(request, member)
    if request.method == "POST" and form.is_valid():
        form.save()
        AuditLog.record(request.user, "member.edited", target=member.membership_no or member.email, request=request)
        messages.success(request, "Member record saved.")
        return redirect("admin_panel:member_detail", pk=member.pk)
    context = {
        "page_title": member.full_name,
        "active_section": "members",
        "member": member,
        "form": form,
        "contributions": Contribution.objects.filter(member=member)[:20],
        "incidents": Incident.objects.filter(member=member)[:10],
        "totals": Contribution.totals(member),
        "account": member.user,
    }
    return render(request, "admin_panel/member_detail.html", context)


@transaction.atomic
def _member_action(request, member):
    from django.conf import settings

    from apps.membership import services as membership_services

    action = request.POST.get("action")
    actor = request.user
    error = False
    if action == "suspend":
        member.status = Member.Status.SUSPENDED
        member.save(update_fields=["status", "updated_at"])
        message = f"{member.full_name} was suspended."
    elif action == "activate":
        membership_services.confirm_membership(member, request)
        message = f"{member.full_name} is active again as {member.membership_no}."
    elif action == "verify_now":
        membership_services.confirm_membership(member, request)
        message = f"{member.full_name} is verified as {member.membership_no} and their account is active."
    elif action == "resend_code":
        allowed, seconds = member.can_resend_code
        if not allowed:
            messages.error(request, f"Please wait {seconds} seconds before sending another code.")
            return redirect("admin_panel:member_detail", pk=member.pk)
        _code, plaintext, report = membership_services.issue_code(member)
        if membership_services.email_not_configured():
            message = (
                f"No code was sent to {member.email}: this site has no mail server configured, so "
                "codes are only printed to the server log. Set EMAIL_HOST, EMAIL_PORT, "
                "EMAIL_HOST_USER, EMAIL_HOST_PASSWORD and DEFAULT_FROM_EMAIL in Render's "
                "Environment tab and redeploy - or use 'Verify by hand' after checking their ID."
            )
            error = True
        elif membership_services.email_failed(report):
            message = f"The code could not be emailed to {member.email}. Check the SMTP settings."
            error = True
        else:
            message = f"A fresh 6-digit code was emailed to {member.email}."
        if settings.DEBUG:
            messages.info(request, f"Development mode - the code is {plaintext}.")
    elif action == "reset_access":
        message = _send_password_link(member, request)
    elif action == "delete":
        if request.POST.get("confirm") != "yes":
            messages.error(request, "Tick the confirmation box before deleting a member.")
            return redirect("admin_panel:member_detail", pk=member.pk)
        label = member.membership_no or member.email
        member.delete()
        AuditLog.record(actor, "member.deleted", target=label, request=request)
        messages.success(request, f"Deleted {label}.")
        return redirect("admin_panel:member_list")
    else:
        messages.error(request, "Unknown action.")
        return redirect("admin_panel:member_detail", pk=member.pk)
    AuditLog.record(actor, f"member.{action}", target=member.membership_no or member.email, request=request)
    if error:
        messages.error(request, message)
    else:
        messages.success(request, message)
    return redirect("admin_panel:member_detail", pk=member.pk)


def _send_password_link(member, request):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    from apps.communications.services import send_welcome_account_link

    user = member.user
    if user is None:
        user = User.objects.create_user(email=member.email, name=member.full_name, password=None, phone=member.phone)
        member.user = user
        member.save(update_fields=["user", "updated_at"])
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    send_welcome_account_link(member, request.build_absolute_uri(path))
    return f"A fresh password link was emailed to {member.email}."


# -------------------------------------------------------------- 4. announcements
@admin_required
def campaign_list(request):
    return render(
        request,
        "admin_panel/campaign_list.html",
        {
            "page_title": "Send email or SMS",
            "active_section": "messages",
            "campaigns": EmailCampaign.objects.select_related("created_by"),
            "members_total": Member.objects.filter(verified=True).count(),
        },
    )


@admin_required
def campaign_create(request):
    form = EmailCampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.created_by = request.user
        campaign.save()
        form.save_m2m()
        emails, sms, error = deliver_campaign(campaign)
        campaign.email_count, campaign.sms_count = emails, sms
        campaign.status = "sent" if emails or sms else "draft"
        campaign.sent_at = timezone.now() if emails or sms else None
        campaign.error_note = error
        campaign.save()
        AuditLog.record(request.user, "campaign.sent", target=campaign.subject, details=f"{emails} emails, {sms} SMS", request=request)
        if emails or sms:
            messages.success(request, f"Sent: {emails} email(s), {sms} SMS.")
        else:
            messages.warning(request, error or "Nothing was sent.")
        return redirect("admin_panel:campaign_list")
    return render(
        request,
        "admin_panel/campaign_form.html",
        {"form": form, "page_title": "New announcement", "active_section": "messages", "preview": Member.objects.filter(verified=True).count()},
    )


# ------------------------------------------------------------------- 5. events
@admin_required
def event_list(request):
    return render(
        request,
        "admin_panel/event_list.html",
        {
            "page_title": "Event calendar",
            "active_section": "events",
            "events": Event.objects.select_related("created_by").order_by("-starts_at"),
            "reports": EventReport.objects.select_related("event").order_by("-created_at")[:10],
        },
    )


@admin_required
def event_form(request, pk=None):
    event = get_object_or_404(Event, pk=pk) if pk else None
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.created_by = request.user
        saved.save()
        AuditLog.record(request.user, "event.saved", target=saved.title, request=request)
        messages.success(request, "Event saved.")
        return redirect("admin_panel:event_list")
    return render(
        request,
        "admin_panel/event_form.html",
        {
            "form": form,
            "event": event,
            "page_title": ("Edit event" if event else "New event"),
            "active_section": "events",
            "report_form": EventReportForm(initial={"event": event.pk} if event else None),
        },
    )


@admin_required
def event_delete(request, pk):
    if request.method != "POST":
        return redirect("admin_panel:event_list")
    event = get_object_or_404(Event, pk=pk)
    if request.POST.get("confirm") != "yes":
        messages.error(request, "Tick the confirmation box before deleting.")
        return redirect("admin_panel:event_list")
    title = event.title
    event.delete()
    AuditLog.record(request.user, "event.deleted", target=title, request=request)
    messages.success(request, f"Deleted '{title}'.")
    return redirect("admin_panel:event_list")


# ---------------------------------------------------------------- 6. reports
@admin_required
def report_list(request):
    return render(
        request,
        "admin_panel/report_list.html",
        {
            "page_title": "Event reports",
            "active_section": "reports",
            "reports": EventReport.objects.select_related("event").prefetch_related("photos"),
            "events": Event.objects.all(),
        },
    )


@admin_required
@transaction.atomic
def report_create(request, pk=None):
    report = get_object_or_404(EventReport, pk=pk) if pk else None
    form = EventReportForm(request.POST or None, instance=report)
    photo_form = EventReportPhotoForm()
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.created_by = request.user
        saved.save()
        for image in request.FILES.getlist("photo"):
            upload = EventReportPhotoForm({"caption": request.POST.get("caption", "")}, {"image": image})
            if upload.is_valid():
                photo = upload.save(commit=False)
                photo.report = saved
                photo.save()
            else:
                messages.warning(request, "One photo was skipped: " + "; ".join(upload.errors.get("image", [])))
        AuditLog.record(request.user, "report.saved", target=saved.title, request=request)
        if request.POST.get("email_members") == "on" and saved.published:
            sent = broadcast_event_report(saved)
            saved.emailed_at = timezone.now()
            saved.save(update_fields=["emailed_at"])
            messages.info(request, f"Report emailed to {sent} member(s).")
        messages.success(request, "Report saved and visible on the public pages.")
        return redirect("admin_panel:report_list")
    return render(
        request,
        "admin_panel/report_form.html",
        {
            "form": form,
            "report": report,
            "photo_form": photo_form,
            "photos": list(report.photos.all()) if report else [],
            "page_title": ("Edit report" if report else "Write an event report"),
            "active_section": "reports",
        },
    )


@admin_required
def report_delete(request, pk):
    if request.method != "POST":
        return redirect("admin_panel:report_list")
    report = get_object_or_404(EventReport, pk=pk)
    title = report.title
    if request.POST.get("confirm") == "yes":
        report.delete()
        AuditLog.record(request.user, "report.deleted", target=title, request=request)
        messages.success(request, f"Deleted report '{title}'.")
    else:
        messages.error(request, "Tick the confirmation box before deleting.")
    return redirect("admin_panel:report_list")


@admin_required
def photo_delete(request, pk):
    photo = get_object_or_404(EventReportPhoto, pk=pk)
    report_pk = photo.report_id
    photo.delete()
    messages.success(request, "Photo removed.")
    return redirect("admin_panel:report_edit", pk=report_pk)


# ------------------------------------------------------------ 7. contributions
@admin_required
def contribution_list(request):
    rows = Contribution.objects.select_related("member", "verified_by")
    status = request.GET.get("status") or ""
    method = request.GET.get("method") or ""
    member_q = (request.GET.get("member") or "").strip()
    date_from = request.GET.get("from") or ""
    date_to = request.GET.get("to") or ""
    if status:
        rows = rows.filter(status=status)
    if method:
        rows = rows.filter(method=method)
    if member_q:
        rows = rows.filter(Q(member__full_name__icontains=member_q) | Q(member__membership_no__icontains=member_q))
    if date_from:
        rows = rows.filter(created_at__date__gte=date_from)
    if date_to:
        rows = rows.filter(created_at__date__lte=date_to)
    fmt = request.GET.get("export")
    if fmt in ("csv", "xlsx"):
        return exports.export_contributions(rows, fmt)
    totals = rows.aggregate(s=Sum("amount"))["s"] or 0
    confirmed = Contribution.objects.filter(status=Contribution.Status.CONFIRMED).aggregate(s=Sum("amount"))["s"] or 0
    context = {
        "page_title": "Contributions",
        "active_section": "contributions",
        "contributions": _paginate(request, rows.order_by("-created_at")),
        "statuses": Contribution.Status.choices,
        "methods": Contribution.Method.choices,
        "selected_status": status,
        "selected_method": method,
        "member_q": member_q,
        "date_from": date_from,
        "date_to": date_to,
        "filtered_total": float(totals),
        "confirmed_total": float(confirmed),
    }
    return render(request, "admin_panel/contribution_list.html", context)


@admin_required
def contribution_decide(request, pk):
    contribution = get_object_or_404(Contribution.objects.select_related("member"), pk=pk)
    form = ContributionDecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        decision = form.cleaned_data["decision"]
        reference = form.cleaned_data["reference"].strip()
        if reference:
            contribution.reference = reference
        if decision == Contribution.Status.CONFIRMED:
            mark_confirmed(contribution, request.user)
            note = "confirmed"
        else:
            mark_rejected(contribution, request.user, form.cleaned_data["reason"])
            note = "rejected"
        from apps.communications.services import notify_member_of_contribution_status

        notify_member_of_contribution_status(contribution)
        AuditLog.record(request.user, f"contribution.{note}", target=f"{contribution.member} {contribution.amount}", request=request)
        messages.success(request, f"Contribution {note}. The member was notified.")
        return redirect("admin_panel:contribution_list")
    return render(
        request,
        "admin_panel/contribution_decide.html",
        {"contribution": contribution, "form": form, "page_title": "Verify contribution", "active_section": "contributions"},
    )


# ----------------------------------------------------------------- 8. incidents
@admin_required
def incident_list(request):
    rows = Incident.objects.select_related("member")
    status = request.GET.get("status") or ""
    if status:
        rows = rows.filter(status=status)
    return render(
        request,
        "admin_panel/incident_list.html",
        {
            "page_title": "Incident inbox",
            "active_section": "incidents",
            "incidents": _paginate(request, rows),
            "statuses": Incident.Status.choices,
            "selected_status": status,
            "counts": dict(Incident.objects.values_list("status").annotate(n=Count("pk"))),
        },
    )


@admin_required
def incident_detail(request, pk):
    incident = get_object_or_404(Incident.objects.select_related("member", "handling_admin"), pk=pk)
    status_form = IncidentStatusForm(request.POST or None, instance=incident)
    reply_form = IncidentResponseForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("form") == "status" and status_form.is_valid():
            incident = status_form.save()
            AuditLog.record(request.user, "incident.status", target=incident.title, details=incident.get_status_display(), request=request)
            messages.success(request, "Status updated.")
            return redirect("admin_panel:incident_detail", pk=incident.pk)
        if request.POST.get("form") == "reply" and reply_form.is_valid():
            reply = reply_form.save(commit=False)
            reply.incident = incident
            reply.author = request.user
            reply.save()
            if reply.notify_member:
                from apps.communications.services import send_incident_reply

                send_incident_reply(incident)
            AuditLog.record(request.user, "incident.replied", target=incident.title, request=request)
            messages.success(request, "Reply saved and the member notified.")
            return redirect("admin_panel:incident_detail", pk=incident.pk)
    return render(
        request,
        "admin_panel/incident_detail.html",
        {
            "incident": incident,
            "status_form": status_form,
            "reply_form": reply_form,
            "page_title": incident.title,
            "active_section": "incidents",
        },
    )


# ------------------------------------------------------------------ 9. settings
@admin_required
def settings_home(request):
    return render(request, "admin_panel/settings_home.html", {"page_title": "Site settings", "active_section": "settings"})


@admin_required
def settings_site(request):
    site = SiteSettings.load()
    form = SiteSettingsForm(request.POST or None, request.FILES or None, instance=site)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.updated_by = request.user
        saved.save()
        AuditLog.record(request.user, "settings.site", target="site settings", request=request)
        messages.success(request, "Site settings saved.")
        return redirect("admin_panel:settings_site")
    return render(
        request,
        "admin_panel/settings_site.html",
        {"form": form, "site": site, "page_title": "Branding, text & contacts", "active_section": "settings"},
    )


@admin_required
def settings_slider(request):
    images = SliderImage.objects.all()
    editing = SliderImage.objects.filter(pk=request.GET.get("edit") or 0).first()
    form = SliderImageForm(request.POST or None, request.FILES or None, instance=editing)
    if request.method == "POST" and form.is_valid():
        form.save()
        AuditLog.record(request.user, "settings.slider", target="slider photo saved", request=request)
        messages.success(request, "Slider photo saved.")
        return redirect("admin_panel:settings_slider")
    return render(
        request,
        "admin_panel/settings_slider.html",
        {
            "images": images,
            "form": form,
            "editing": editing,
            "page_title": "Home slider photos",
            "active_section": "settings",
        },
    )


@admin_required
def slider_delete(request, pk):
    image = get_object_or_404(SliderImage, pk=pk)
    image.delete()
    AuditLog.record(request.user, "settings.slider.delete", target=f"slide {pk}", request=request)
    messages.success(request, "Slider photo removed.")
    return redirect("admin_panel:settings_slider")


@admin_required
def settings_social(request):
    links = SocialLink.objects.all()
    editing = SocialLink.objects.filter(pk=request.GET.get("edit") or 0).first()
    form = SocialLinkForm(request.POST or None, instance=editing)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Social link saved.")
        return redirect("admin_panel:settings_social")
    return render(
        request,
        "admin_panel/settings_social.html",
        {"links": links, "form": form, "editing": editing, "page_title": "Social media links", "active_section": "settings"},
    )


@admin_required
def settings_nav(request):
    items = NavItem.objects.all()
    editing = NavItem.objects.filter(pk=request.GET.get("edit") or 0).first()
    form = NavItemForm(request.POST or None, instance=editing)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Navigation button saved.")
        return redirect("admin_panel:settings_nav")
    return render(
        request,
        "admin_panel/settings_nav.html",
        {"items": items, "form": form, "editing": editing, "page_title": "Navigation buttons", "active_section": "settings"},
    )


@admin_required
def nav_delete(request, pk):
    item = get_object_or_404(NavItem, pk=pk)
    item.delete()
    messages.success(request, "Button removed.")
    return redirect("admin_panel:settings_nav")


@admin_required
def settings_options(request):
    field = request.GET.get("field", DropdownOption.Field.ROLE)
    options = DropdownOption.objects.filter(field=field)
    form = DropdownOptionForm(request.POST or None, initial={"field": field})
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"'{form.instance.label}' saved.")
        return redirect(reverse("admin_panel:settings_options") + f"?field={form.instance.field}")
    return render(
        request,
        "admin_panel/settings_options.html",
        {
            "options": options,
            "form": form,
            "fields": DropdownOption.Field.choices,
            "current_field": field,
            "page_title": "Dropdown options",
            "active_section": "settings",
        },
    )


@admin_required
def option_delete(request, pk):
    option = get_object_or_404(DropdownOption, pk=pk)
    field = option.field
    option.delete()
    messages.success(request, "Option removed.")
    return redirect(reverse("admin_panel:settings_options") + f"?field={field}")


# ------------------------------------------------------------------- misc pages
@admin_required
def audit_list(request):
    entries = AuditLog.objects.select_related("actor")
    search = (request.GET.get("q") or "").strip()
    if search:
        entries = entries.filter(Q(action__icontains=search) | Q(target__icontains=search) | Q(details__icontains=search))
    return render(
        request,
        "admin_panel/audit_list.html",
        {"entries": _paginate(request, entries, 50), "search": search, "page_title": "Audit log", "active_section": "audit"},
    )


@admin_required
def contact_list(request):
    messages_box = ContactMessage.objects.select_related("member")
    handled = request.GET.get("handled", "")
    if handled == "yes":
        messages_box = messages_box.filter(handled=True)
    elif handled == "no":
        messages_box = messages_box.filter(handled=False)
    return render(
        request,
        "admin_panel/contact_list.html",
        {
            "inbox": _paginate(request, messages_box, 30),
            "handled_filter": handled,
            "page_title": "Member messages",
            "active_section": "messages",
        },
    )


@admin_required
def contact_mark(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    message.handled = not message.handled
    message.handled_by = request.user if message.handled else None
    message.save()
    messages.success(request, "Marked as handled." if message.handled else "Reopened.")
    return redirect("admin_panel:contact_list")
