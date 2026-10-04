import json
from unittest.mock import patch
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .access import GROUP_MANAGER_ROLE
from .models import (
    ActivityLog, PendingAssignmentDismissal, PosterGroupWhyUseful, ProceedingsSource, ResearchGroup,
    ResearchInterest, ResearchPoster, UserGroupMembership,
)


@override_settings(
    SHIBBOLETH_AUTH=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class GroupManagementAccessTests(TestCase):

    entry_pages = ("upload", "dashboard", "conference", "my_groups")
    superusers = ("super_no_membership", "super_member")
    managers = ("manager_no_membership", "manager_member")
    ordinary_users = ("member", "no_membership")

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager_role, _ = Group.objects.get_or_create(name=GROUP_MANAGER_ROLE)
        cls.group = ResearchGroup.objects.create(name="Access regression research group")
        cls.interest = ResearchInterest.objects.create(group=cls.group, text="Original research interest")
        cls.users = {}
        for role in cls.superusers + cls.managers + cls.ordinary_users:
            user = User.objects.create_user(
                username=role,
                is_superuser=role in cls.superusers,
                is_staff=role == "super_member",
            )
            cls.users[role] = user
            if role in cls.managers:
                user.groups.add(cls.manager_role)
            if role in ("super_member", "manager_member", "member"):
                UserGroupMembership.objects.create(user=user, group=cls.group, is_primary=True)

    def sign_in(self, role, client=None):
        client = client or self.client
        client.force_login(self.users[role], backend="django.contrib.auth.backends.ModelBackend")
        return client

    def entry_pages_for(self, role):
        # Users outside every research group are funnelled to the upload page.
        return ("upload",) if role.endswith("no_membership") else self.entry_pages

    def assert_management_navigation(self, response, *, groups, users):
        self.assertEqual(response.status_code, 200)
        for route, visible in (("group_list", groups), ("user_admin_list", users)):
            href = f'href="{reverse(route)}"'
            if visible:
                self.assertContains(response, href)
            else:
                self.assertNotContains(response, href)
        if groups:
            self.assertContains(response, "Manage Groups")

    def test_superusers_can_find_management_from_every_entry_page(self):
        for role in self.superusers:
            self.sign_in(role)
            for page in self.entry_pages:
                with self.subTest(role=role, page=page):
                    self.assert_management_navigation(self.client.get(reverse(page)), groups=True, users=True)

    def test_group_managers_can_find_management_without_research_membership(self):
        for role in self.managers:
            self.sign_in(role)
            for page in self.entry_pages_for(role):
                with self.subTest(role=role, page=page):
                    self.assert_management_navigation(self.client.get(reverse(page)), groups=True, users=False)

    def test_ordinary_users_do_not_see_management_links(self):
        for role in self.ordinary_users:
            self.sign_in(role)
            for page in self.entry_pages_for(role):
                with self.subTest(role=role, page=page):
                    self.assert_management_navigation(self.client.get(reverse(page)), groups=False, users=False)

    def test_users_without_groups_are_sent_to_the_upload_page(self):
        for role in ("manager_no_membership", "no_membership"):
            self.sign_in(role)
            for page in ("dashboard", "conference", "my_groups"):
                with self.subTest(role=role, page=page):
                    self.assertRedirects(self.client.get(reverse(page)), reverse("upload"), fetch_redirect_response=False)
            response = self.client.get(reverse("upload"))
            self.assertContains(response, "Uploads and Dashboard are locked")
            self.assertNotContains(response, "no-groups-banner")
            self.assertNotContains(response, f'href="{reverse("dashboard")}"')
            self.assertNotContains(response, f'href="{reverse("my_groups")}"')

    def test_locked_upload_page_shows_the_admin_contact_only_when_configured(self):
        self.sign_in("no_membership")
        with override_settings(ADMIN_CONTACT_EMAIL="posterhub-admin@example.org"):
            response = self.client.get(reverse("upload"))
            self.assertContains(response, 'href="mailto:posterhub-admin@example.org"')
            self.assertEqual(
                self.client.get(reverse("dashboard"), HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()["message"].count(
                    "posterhub-admin@example.org"
                ),
                1,
            )
        with override_settings(ADMIN_CONTACT_EMAIL=""):
            self.assertNotContains(self.client.get(reverse("upload")), "mailto:")

    def test_anonymous_visitors_must_sign_in(self):
        for page in self.entry_pages + ("group_list", "user_admin_list"):
            with self.subTest(page=page):
                url = reverse(page)
                self.assertRedirects(
                    self.client.get(url), f"{reverse('login')}?next={url}", fetch_redirect_response=False
                )
        self.assertRedirects(
            self.client.post(reverse("group_create"), {"name": "Anonymous creation"}),
            f"{reverse('login')}?next={reverse('group_create')}",
            fetch_redirect_response=False,
        )
        self.assertFalse(ResearchGroup.objects.filter(name="Anonymous creation").exists())

    def test_personal_group_cards_offer_editing_only_to_group_managers(self):
        edit_href = f'href="{reverse("group_edit", args=[self.group.pk])}"'
        for role in ("super_member", "manager_member", "member"):
            with self.subTest(role=role):
                self.sign_in(role)
                response = self.client.get(reverse("my_groups"))
                self.assertContains(response, self.interest.text)
                if role == "member":
                    self.assertNotContains(response, edit_href)
                else:
                    self.assertContains(response, edit_href)
                    self.assertContains(response, "Edit group &amp; interests")

    def test_my_groups_lists_other_groups_with_their_interests(self):
        other = ResearchGroup.objects.create(name="Other lab")
        ResearchInterest.objects.create(group=other, text="Robot perception")
        self.sign_in("member")
        response = self.client.get(reverse("my_groups"))
        self.assertContains(response, "Other Groups")
        self.assertContains(response, "Other lab")
        self.assertContains(response, "Robot perception")
        self.assertEqual(
            [g.pk for g in response.context["other_groups"]],
            list(ResearchGroup.objects.exclude(memberships__user=self.users["member"]).values_list("pk", flat=True)),
        )
        self.assertNotIn(self.group.pk, [g.pk for g in response.context["other_groups"]])

    def test_authorized_users_can_open_group_and_interest_forms(self):
        for role in self.superusers + self.managers:
            with self.subTest(role=role):
                self.sign_in(role)
                response = self.client.get(reverse("group_list"))
                self.assertContains(response, f'action="{reverse("group_create")}"')
                self.assertContains(response, 'name="research_interests"')
                response = self.client.get(reverse("group_edit", args=[self.group.pk]))
                self.assertContains(response, f'action="{reverse("interest_add", args=[self.group.pk])}"')
                self.assertContains(response, f'action="{reverse("interest_edit", args=[self.interest.pk])}"')

    def test_group_creation_is_confirmed_with_a_toast(self):
        self.sign_in("super_member")
        response = self.client.post(reverse("group_create"), {"name": "Toast group"}, follow=True)
        self.assertContains(response, 'class="toast toast-success')
        self.assertContains(response, "Group &quot;Toast group&quot; created.")
        self.assertNotContains(response, 'class="flash-alert')

    def test_group_edit_confirmations_are_shown_as_toasts(self):
        self.sign_in("super_member")
        response = self.client.post(
            reverse("group_edit", args=[self.group.pk]), {"name": "Renamed for toast"}, follow=True,
        )
        self.assertContains(response, 'class="toast toast-success')
        self.assertContains(response, "Group &quot;Renamed for toast&quot; updated.")
        self.assertNotContains(response, 'class="flash-alert')

    def test_user_management_confirmations_are_shown_as_toasts(self):
        self.sign_in("super_member")
        response = self.client.post(
            reverse("user_toggle_group_manager", args=[self.users["member"].pk]), follow=True,
        )
        self.assertContains(response, 'class="toast toast-success')
        self.assertContains(response, "added to group managers.")
        self.assertNotContains(response, 'class="flash-alert')

    def test_authorized_users_can_create_edit_and_delete_groups_and_interests(self):
        for role in self.superusers + self.managers:
            with self.subTest(role=role):
                self.sign_in(role)
                group_name = f"Created by {role}"
                response = self.client.post(reverse("group_create"), {
                    "name": group_name,
                    "research_interests": "Computer vision\n\n  Medical imaging  \n",
                })
                self.assertRedirects(response, reverse("group_list"), fetch_redirect_response=False)
                group = ResearchGroup.objects.get(name=group_name)
                self.assertEqual(list(group.interests.values_list("text", flat=True)), ["Computer vision", "Medical imaging"])

                edit_url = reverse("group_edit", args=[group.pk])
                response = self.client.post(edit_url, {"name": f"Renamed by {role}"})
                self.assertRedirects(response, edit_url, fetch_redirect_response=False)
                group.refresh_from_db()
                self.assertEqual(group.name, f"Renamed by {role}")

                response = self.client.post(reverse("interest_add", args=[group.pk]), {
                    "text": "Representation learning\nRobotics",
                })
                self.assertRedirects(response, edit_url, fetch_redirect_response=False)
                self.assertEqual(group.interests.count(), 4)
                interest = group.interests.get(text="Representation learning")
                response = self.client.post(reverse("interest_edit", args=[interest.pk]), {"text": "Self-supervised learning"})
                self.assertRedirects(response, edit_url, fetch_redirect_response=False)
                interest.refresh_from_db()
                self.assertEqual(interest.text, "Self-supervised learning")

                response = self.client.post(reverse("interest_delete", args=[interest.pk]))
                self.assertRedirects(response, edit_url, fetch_redirect_response=False)
                self.assertFalse(ResearchInterest.objects.filter(pk=interest.pk).exists())
                response = self.client.post(reverse("group_delete", args=[group.pk]))
                self.assertRedirects(response, reverse("group_list"), fetch_redirect_response=False)
                self.assertFalse(ResearchGroup.objects.filter(pk=group.pk).exists())
                self.assertFalse(ResearchInterest.objects.filter(group_id=group.pk).exists())

    def test_authorized_users_can_add_and_remove_group_members(self):
        target = self.users["no_membership"]
        for role in self.superusers + self.managers:
            with self.subTest(role=role):
                self.sign_in(role)
                response = self.client.post(reverse("group_add_member", args=[self.group.pk]), {"user_ids": [target.pk]})
                self.assertRedirects(response, reverse("group_edit", args=[self.group.pk]), fetch_redirect_response=False)
                self.assertTrue(UserGroupMembership.objects.get(user=target, group=self.group).is_primary)
                response = self.client.post(reverse("group_remove_member", args=[self.group.pk, target.pk]))
                self.assertRedirects(response, reverse("group_edit", args=[self.group.pk]), fetch_redirect_response=False)
                self.assertFalse(UserGroupMembership.objects.filter(user=target, group=self.group).exists())

    def test_add_member_from_pending_list_returns_to_group_list(self):
        target = self.users["no_membership"]
        self.sign_in("super_no_membership")
        next_url = reverse("group_list") + "?q=lab"
        response = self.client.post(reverse("group_add_member", args=[self.group.pk]), {
            "user_ids": [target.pk], "next": next_url,
        })
        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertTrue(UserGroupMembership.objects.filter(user=target, group=self.group).exists())

        response = self.client.post(reverse("group_add_member", args=[self.group.pk]), {
            "user_ids": [target.pk], "next": "https://evil.example.com/",
        })
        self.assertRedirects(response, reverse("group_edit", args=[self.group.pk]), fetch_redirect_response=False)

    def test_add_member_ajax_returns_json_without_redirect(self):
        target = self.users["no_membership"]
        self.sign_in("super_no_membership")
        url = reverse("group_add_member", args=[self.group.pk])
        response = self.client.post(url, {"user_ids": [target.pk]}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual([m["user_id"] for m in data["added"]], [target.pk])
        self.assertTrue(data["added"][0]["is_primary"])
        self.assertEqual(data["messages"][0]["type"], "success")

        response = self.client.post(url, {"user_ids": [target.pk]}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.json()["already"], [target.pk])

        response = self.client.post(url, {}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)

    def test_removal_dialog_warns_only_when_it_is_the_users_last_group(self):
        warning = "This is the user's last group"
        edit_url = reverse("group_edit", args=[self.group.pk])
        self.sign_in("super_no_membership")

        def warned(user):
            response = self.client.get(edit_url)
            action = reverse("group_remove_member", args=[self.group.pk, user.pk])
            form = response.content.decode().split(f'action="{action}"', 1)[1].split(">", 1)[0]
            return warning in form

        self.assertTrue(warned(self.users["member"]))
        self.assertTrue(warned(self.users["manager_member"]))
        self.assertFalse(warned(self.users["super_member"]))

        other = ResearchGroup.objects.create(name="Second research group")
        UserGroupMembership.objects.create(user=self.users["member"], group=other)
        self.assertFalse(warned(self.users["member"]))

    def test_apostrophes_in_data_attributes_are_html_escaped_not_js_escaped(self):
        member = self.users["member"]
        member.first_name, member.last_name = "Anna", "D'Angelo"
        member.save()
        self.sign_in("super_no_membership")
        response = self.client.get(reverse("group_edit", args=[self.group.pk]))
        self.assertContains(response, 'data-confirm="Remove Anna D&#x27;Angelo from the group')
        self.assertNotContains(response, "\\u0027")

        self.sign_in("member")
        response = self.client.get(reverse("dashboard"), {"search": "Alzheimer's"})
        self.assertContains(response, 'data-search-query="Alzheimer&#x27;s"')

    def test_add_member_picker_lists_surname_first_alphabetically(self):
        User = get_user_model()
        User.objects.create_user(username="aa_rossi", first_name="Mario", last_name="Rossi")
        User.objects.create_user(username="zz_bianchi", first_name="Anna", last_name="bianchi")
        User.objects.create_user(username="b_rossi", first_name="Mario", last_name="Rossi")
        User.objects.create_user(username="a_rossi_luca", first_name="Luca", last_name="Rossi")
        self.sign_in("super_no_membership")
        response = self.client.get(reverse("group_edit", args=[self.group.pk]))
        named = [u.username for u in response.context["all_users"] if u.last_name]
        self.assertEqual(named, ["zz_bianchi", "a_rossi_luca", "aa_rossi", "b_rossi"])
        self.assertContains(response, "Bianchi Anna — zz_bianchi")

    def test_ordinary_users_cannot_open_management_pages_directly(self):
        for role in self.ordinary_users:
            self.sign_in(role)
            for url in (reverse("group_list"), reverse("group_edit", args=[self.group.pk])):
                with self.subTest(role=role, url=url):
                    self.assertRedirects(self.client.get(url), reverse("dashboard"), fetch_redirect_response=False)

    def test_ordinary_users_cannot_mutate_groups_interests_or_memberships(self):
        original_memberships = list(UserGroupMembership.objects.order_by("pk").values_list("user_id", "group_id", "is_primary"))
        requests = (
            ("group_create", [], {"name": "Forbidden group", "research_interests": "Forbidden interest"}),
            ("group_edit", [self.group.pk], {"name": "Forbidden rename"}),
            ("interest_add", [self.group.pk], {"text": "Forbidden interest"}),
            ("interest_edit", [self.interest.pk], {"text": "Forbidden edit"}),
            ("interest_delete", [self.interest.pk], {}),
            ("group_add_member", [self.group.pk], {"user_ids": [self.users["no_membership"].pk]}),
            ("group_remove_member", [self.group.pk, self.users["member"].pk], {}),
            ("group_set_primary", [self.group.pk, self.users["member"].pk], {}),
            ("dismiss_pending_user", [self.users["no_membership"].pk], {}),
            ("group_delete", [self.group.pk], {}),
        )
        for role in self.ordinary_users:
            self.sign_in(role)
            for ajax in (False, True):
                headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if ajax else {}
                for route, args, data in requests:
                    with self.subTest(role=role, route=route, ajax=ajax):
                        response = self.client.post(reverse(route, args=args), data, **headers)
                        if ajax:
                            self.assertEqual(response.status_code, 403)
                        else:
                            self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.group.refresh_from_db()
        self.interest.refresh_from_db()
        self.assertEqual(self.group.name, "Access regression research group")
        self.assertEqual(self.interest.text, "Original research interest")
        self.assertEqual(ResearchGroup.objects.count(), 1)
        self.assertEqual(ResearchInterest.objects.count(), 1)
        self.assertEqual(list(UserGroupMembership.objects.order_by("pk").values_list("user_id", "group_id", "is_primary")), original_memberships)
        self.assertFalse(PendingAssignmentDismissal.objects.exists())

    def test_user_administration_is_reserved_to_superusers(self):
        for role in self.superusers + self.managers + self.ordinary_users:
            with self.subTest(role=role):
                self.sign_in(role)
                response = self.client.get(reverse("user_admin_list"))
                if role in self.superusers:
                    self.assertContains(response, self.users["member"].username)
                else:
                    self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_group_managers_and_ordinary_users_cannot_change_user_roles(self):
        target = self.users["no_membership"]
        for role in self.managers + self.ordinary_users:
            self.sign_in(role)
            for route in ("user_toggle_superuser", "user_toggle_group_manager", "user_delete"):
                with self.subTest(role=role, route=route):
                    response = self.client.post(reverse(route, args=[target.pk]))
                    self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
                    target.refresh_from_db()
                    self.assertFalse(target.is_superuser)
                    self.assertFalse(target.is_staff)
                    self.assertFalse(target.groups.exists())

    def test_management_submissions_still_require_csrf(self):
        client = self.sign_in("super_no_membership", Client(enforce_csrf_checks=True))
        response = client.get(reverse("group_list"))
        self.assertEqual(response.status_code, 200)
        response = client.post(reverse("group_create"), {"name": "Missing CSRF token"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ResearchGroup.objects.filter(name="Missing CSRF token").exists())

    def test_role_changes_are_visible_in_an_existing_browser_session(self):
        user = self.users["no_membership"]
        self.sign_in("no_membership")
        self.assert_management_navigation(self.client.get(reverse("upload")), groups=False, users=False)
        user.groups.add(self.manager_role)
        self.assert_management_navigation(self.client.get(reverse("upload")), groups=True, users=False)
        self.assertEqual(self.client.get(reverse("group_list")).status_code, 200)
        user.groups.remove(self.manager_role)
        self.assert_management_navigation(self.client.get(reverse("upload")), groups=False, users=False)
        self.assertRedirects(self.client.get(reverse("group_list")), reverse("dashboard"), fetch_redirect_response=False)
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])
        self.assert_management_navigation(self.client.get(reverse("upload")), groups=True, users=True)
        self.assertEqual(self.client.get(reverse("user_admin_list")).status_code, 200)

    def test_mutation_only_routes_reject_get_requests(self):
        routes = (
            ("group_create", []),
            ("group_delete", [self.group.pk]),
            ("interest_add", [self.group.pk]),
            ("interest_edit", [self.interest.pk]),
            ("interest_delete", [self.interest.pk]),
        )
        for role in ("super_no_membership", "manager_no_membership"):
            self.sign_in(role)
            for route, args in routes:
                with self.subTest(role=role, route=route):
                    self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 405)
        self.assertTrue(ResearchGroup.objects.filter(pk=self.group.pk).exists())
        self.assertTrue(ResearchInterest.objects.filter(pk=self.interest.pk).exists())


@override_settings(
    SHIBBOLETH_AUTH=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class PosterGroupScopeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="scope_owner")
        cls.teammate = User.objects.create_user(username="scope_teammate")
        cls.outsider = User.objects.create_user(username="scope_outsider")
        cls.admin = User.objects.create_user(username="scope_admin", is_superuser=True)

        cls.team = ResearchGroup.objects.create(name="Scope team")
        cls.other_team = ResearchGroup.objects.create(name="Scope other team")
        ResearchInterest.objects.create(group=cls.team, text="Medical imaging")
        for user in (cls.owner, cls.teammate):
            UserGroupMembership.objects.create(user=user, group=cls.team, is_primary=True)
        UserGroupMembership.objects.create(user=cls.outsider, group=cls.other_team, is_primary=True)

        cls.shared = cls._poster("Shared team paper", cls.owner)
        cls.shared.groups.add(cls.team)
        cls.foreign = cls._poster("Outsider paper", cls.outsider)
        cls.foreign.groups.add(cls.other_team)
        cls.ungrouped = cls._poster("Personal upload", cls.owner)

    @staticmethod
    def _poster(title, uploader):
        return ResearchPoster.objects.create(
            title=title, authors="An Author", summary="A summary.",
            validation_status="approved", uploaded_by=uploader,
        )

    def sign_in(self, user):
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")

    def read_routes(self, poster):
        return (("poster_detail", [poster.pk]), ("edit_poster", [poster.pk]))

    def write_routes(self, poster):
        return (
            ("update_status", [poster.pk], {"status": "rejected"}),
            ("update_notes", [poster.pk], {"notes": "injected"}),
            ("update_tags", [poster.pk], {"tags": "injected"}),
            ("toggle_favorite", [poster.pk], {}),
            ("retry_analysis", [poster.pk], {}),
            ("stop_analysis", [poster.pk], {}),
            ("update_poster_groups", [poster.pk], {}),
            ("delete_poster", [poster.pk], {}),
        )

    def test_teammate_may_read_and_edit_a_paper_uploaded_by_someone_else(self):
        self.sign_in(self.teammate)
        for route, args in self.read_routes(self.shared):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 200)

        response = self.client.post(
            reverse("update_status", args=[self.shared.pk]), {"status": "rejected"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.validation_status, "rejected")

        response = self.client.post(
            reverse("edit_poster", args=[self.shared.pk]),
            {"title": "Renamed by teammate", "authors": "An Author",
             "summary": "A summary.", "category": "other", "validation_status": "approved"},
        )
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.title, "Renamed by teammate")

    def test_teammate_may_annotate_and_requeue_a_paper_uploaded_by_someone_else(self):
        self.sign_in(self.teammate)
        for route, payload, field, expected in (
            ("update_notes", {"notes": "Useful for our work"}, "notes", "Useful for our work"),
            ("update_tags", {"tags": "segmentation"}, "tags", "segmentation"),
        ):
            with self.subTest(route=route):
                response = self.client.post(
                    reverse(route, args=[self.shared.pk]),
                    data=json.dumps(payload), content_type="application/json",
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                self.assertEqual(response.status_code, 200)
                self.shared.refresh_from_db()
                self.assertEqual(getattr(self.shared, field), expected)

        response = self.client.post(
            reverse("toggle_favorite", args=[self.shared.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertTrue(response.json()["is_favorite"])

        with patch("bot_engine.views.process_poster_task.delay") as queued:
            queued.return_value.id = "task-id"
            response = self.client.post(reverse("retry_analysis", args=[self.shared.pk]))
        self.assertEqual(response.status_code, 200)
        queued.assert_called_once()
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.analysis_status, "processing")

        response = self.client.post(reverse("stop_analysis", args=[self.shared.pk]))
        self.assertEqual(response.status_code, 200)
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.analysis_status, "failed")

    def test_teammate_may_delete_a_paper_uploaded_by_someone_else(self):
        victim = self._poster("Deletable team paper", self.owner)
        victim.groups.add(self.team)
        self.sign_in(self.teammate)
        response = self.client.post(
            reverse("delete_poster", args=[victim.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ResearchPoster.objects.filter(pk=victim.pk).exists())

    def test_outsider_cannot_reach_a_paper_from_another_group(self):
        self.sign_in(self.outsider)
        for route, args in self.read_routes(self.shared):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 404)
        for route, args, payload in self.write_routes(self.shared):
            with self.subTest(route=route):
                self.assertEqual(self.client.post(reverse(route, args=args), payload).status_code, 404)
        self.shared.refresh_from_db()
        self.assertEqual(self.shared.title, "Shared team paper")
        self.assertEqual(self.shared.validation_status, "approved")
        self.assertTrue(ResearchPoster.objects.filter(pk=self.shared.pk).exists())
        self.assertEqual(set(self.shared.groups.values_list("pk", flat=True)), {self.team.pk})

    def test_uploader_keeps_access_to_a_paper_with_no_group(self):
        self.sign_in(self.owner)
        self.assertEqual(self.client.get(reverse("poster_detail", args=[self.ungrouped.pk])).status_code, 200)
        self.sign_in(self.outsider)
        self.assertEqual(self.client.get(reverse("poster_detail", args=[self.ungrouped.pk])).status_code, 404)

    def test_superuser_reaches_every_paper(self):
        self.sign_in(self.admin)
        for poster in (self.shared, self.foreign, self.ungrouped):
            with self.subTest(poster=poster.title):
                self.assertEqual(self.client.get(reverse("poster_detail", args=[poster.pk])).status_code, 200)

    def test_bulk_actions_ignore_papers_outside_the_caller_groups(self):
        self.sign_in(self.teammate)
        response = self.client.post(
            reverse("bulk_action"),
            data=json.dumps({"ids": [self.shared.pk, self.foreign.pk], "action": "rejected"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "1 papers set to Rejected")
        self.shared.refresh_from_db()
        self.foreign.refresh_from_db()
        self.assertEqual(self.shared.validation_status, "rejected")
        self.assertEqual(self.foreign.validation_status, "approved")

    def test_bulk_delete_cannot_remove_papers_from_another_group(self):
        self.sign_in(self.teammate)
        response = self.client.post(
            reverse("bulk_action"),
            data=json.dumps({"ids": [self.foreign.pk], "action": "delete"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "0 papers deleted")
        self.assertTrue(ResearchPoster.objects.filter(pk=self.foreign.pk).exists())

    def test_exports_only_contain_papers_from_the_caller_groups(self):
        self.sign_in(self.teammate)
        titles = [item["title"] for item in self.client.get(reverse("export_approved_json")).json()["items"]]
        self.assertIn("Shared team paper", titles)
        self.assertNotIn("Outsider paper", titles)
        csv_body = self.client.get(reverse("export_approved_csv")).content.decode("utf-8-sig")
        self.assertIn("Shared team paper", csv_body)
        self.assertNotIn("Outsider paper", csv_body)

    def test_group_evaluation_is_refused_for_groups_the_caller_is_not_in(self):
        self.foreign.groups.add(self.team)
        self.sign_in(self.teammate)
        url = reverse("poster_why_useful_for_group", args=[self.foreign.pk])
        self.assertEqual(self.client.get(url, {"group_id": self.other_team.pk}).status_code, 403)
        self.sign_in(self.outsider)
        self.assertEqual(
            self.client.get(reverse("poster_why_useful_for_group", args=[self.shared.pk])).status_code, 404,
        )

    def assign_groups(self, poster, group_ids):
        return self.client.post(
            reverse("update_poster_groups", args=[poster.pk]),
            data=json.dumps({"group_ids": group_ids}),
            content_type="application/json",
        )

    def test_a_caller_cannot_add_a_paper_to_a_group_they_do_not_belong_to(self):
        self.sign_in(self.teammate)
        response = self.assign_groups(self.shared, [self.other_team.pk])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(self.shared.groups.values_list("pk", flat=True)), {self.team.pk})

    def test_a_caller_may_detach_their_own_group_but_never_a_foreign_one(self):
        self.foreign.groups.add(self.team)
        self.sign_in(self.teammate)
        response = self.assign_groups(self.foreign, [self.other_team.pk])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(self.foreign.groups.values_list("pk", flat=True)), {self.other_team.pk})
        self.assertEqual([g["id"] for g in response.json()["user_groups"]], [])

    def edit_with_groups(self, poster, group_ids):
        return self.client.post(
            reverse("edit_poster", args=[poster.pk]),
            {"title": poster.title, "authors": "An Author", "summary": "A summary.",
             "category": "other", "validation_status": "approved",
             "groups_submitted": "1", "group_ids": group_ids},
        )

    def test_the_edit_form_reassigns_groups_within_the_callers_own(self):
        UserGroupMembership.objects.create(user=self.teammate, group=self.other_team)
        self.sign_in(self.teammate)
        self.assertContains(
            self.client.get(reverse("edit_poster", args=[self.shared.pk])), 'name="group_ids"',
        )
        response = self.edit_with_groups(self.shared, [self.other_team.pk])
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(set(self.shared.groups.values_list("pk", flat=True)), {self.other_team.pk})

    def test_editing_from_the_poster_page_returns_there_with_a_toast(self):
        self.sign_in(self.teammate)
        detail_url = reverse("poster_detail", args=[self.shared.pk])
        edit_url = reverse("edit_poster", args=[self.shared.pk])
        self.assertContains(self.client.get(detail_url), f'href="{edit_url}?next={quote(detail_url, safe="")}"')
        response = self.client.post(
            edit_url,
            {"title": "Edited from detail", "authors": "An Author", "summary": "A summary.",
             "category": "other", "validation_status": "approved", "next": detail_url},
            follow=True,
        )
        self.assertRedirects(response, detail_url)
        self.assertContains(response, 'class="toast toast-success')
        self.assertContains(response, "Paper updated successfully!")

    def test_the_edit_form_refuses_to_leave_a_paper_without_groups(self):
        self.sign_in(self.teammate)
        response = self.edit_with_groups(self.shared, [])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select at least one group.")
        self.assertEqual(set(self.shared.groups.values_list("pk", flat=True)), {self.team.pk})

    def test_the_edit_form_keeps_groups_the_caller_is_not_in(self):
        self.foreign.groups.add(self.team)
        self.sign_in(self.teammate)
        self.edit_with_groups(self.foreign, [self.other_team.pk])
        self.assertEqual(set(self.foreign.groups.values_list("pk", flat=True)), {self.other_team.pk})

    def test_clearing_the_activity_log_is_reserved_to_managers(self):
        ActivityLog.objects.create(action="created", poster_title="Shared team paper")
        for user in (self.owner, self.teammate, self.outsider):
            with self.subTest(user=user.username):
                self.sign_in(user)
                self.assertRedirects(
                    self.client.post(reverse("delete_all_activities")),
                    reverse("dashboard"), fetch_redirect_response=False,
                )
        self.assertTrue(ActivityLog.objects.exists())
        self.sign_in(self.admin)
        self.assertRedirects(
            self.client.post(reverse("delete_all_activities")),
            reverse("dashboard"), fetch_redirect_response=False,
        )
        self.assertFalse(ActivityLog.objects.exists())


@override_settings(
    SHIBBOLETH_AUTH=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class WhyUsefulPerGroupTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.member = User.objects.create_user(username="why_member")
        cls.admin = User.objects.create_user(username="why_admin", is_superuser=True)
        cls.vision = ResearchGroup.objects.create(name="Vision")
        cls.robotics = ResearchGroup.objects.create(name="Robotics")
        cls.bare = ResearchGroup.objects.create(name="Without interests")
        ResearchInterest.objects.create(group=cls.vision, text="Segmentation")
        ResearchInterest.objects.create(group=cls.robotics, text="Grasping")
        UserGroupMembership.objects.create(user=cls.member, group=cls.vision, is_primary=True)
        UserGroupMembership.objects.create(user=cls.member, group=cls.robotics)
        UserGroupMembership.objects.create(user=cls.member, group=cls.bare)
        cls.poster = ResearchPoster.objects.create(
            title="Per-group paper", authors="An Author", summary="A summary.",
            validation_status="approved", why_useful="General copy",
        )
        cls.poster.groups.add(cls.vision, cls.robotics, cls.bare)
        PosterGroupWhyUseful.objects.create(poster=cls.poster, group=cls.vision, why_useful="Vision text")
        PosterGroupWhyUseful.objects.create(poster=cls.poster, group=cls.robotics, why_useful="Robotics text")

    def sign_in(self, user):
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")

    def edit(self, **why):
        return self.client.post(reverse("edit_poster", args=[self.poster.pk]), {
            "title": self.poster.title, "authors": "An Author", "summary": "A summary.",
            "category": "other", "validation_status": "approved", **why,
        })

    def group_text(self, group):
        entry = PosterGroupWhyUseful.objects.filter(poster=self.poster, group=group).first()
        return entry.why_useful if entry else None

    def test_the_edit_page_has_one_box_per_group_and_no_general_field(self):
        self.sign_in(self.member)
        response = self.client.get(reverse("edit_poster", args=[self.poster.pk]))
        self.assertContains(response, f'name="why_useful_{self.vision.pk}"')
        self.assertContains(response, f'name="why_useful_{self.robotics.pk}"')
        self.assertContains(response, "Vision text")
        self.assertContains(response, "Robotics text")
        self.assertNotContains(response, 'name="why_useful"')
        self.assertNotContains(response, f'name="why_useful_{self.bare.pk}"')
        self.assertContains(response, "This group has no research interests")

    def test_saving_updates_only_that_groups_text_and_the_poster_page_shows_it(self):
        self.sign_in(self.member)
        self.edit(**{f"why_useful_{self.vision.pk}": "Edited vision text\r\n",
                     f"why_useful_{self.robotics.pk}": "Robotics text"})
        self.assertEqual(self.group_text(self.vision), "Edited vision text")
        self.assertEqual(self.group_text(self.robotics), "Robotics text")
        self.poster.refresh_from_db()
        self.assertEqual(self.poster.why_useful, "General copy")
        with patch("bot_engine.views.generate_why_useful") as generate:
            response = self.client.get(
                reverse("poster_why_useful_for_group", args=[self.poster.pk]), {"group_id": self.vision.pk},
            )
        generate.assert_not_called()
        self.assertEqual(response.json()["why_useful"], "Edited vision text")

    def test_an_unchanged_box_is_not_rewritten(self):
        self.sign_in(self.member)
        before = PosterGroupWhyUseful.objects.get(poster=self.poster, group=self.robotics).updated_at
        self.edit(**{f"why_useful_{self.robotics.pk}": "Robotics text\r\n"})
        after = PosterGroupWhyUseful.objects.get(poster=self.poster, group=self.robotics).updated_at
        self.assertEqual(before, after)

    def test_emptying_a_box_lets_the_ai_write_a_new_text(self):
        self.sign_in(self.member)
        self.edit(**{f"why_useful_{self.vision.pk}": "   "})
        self.assertIsNone(self.group_text(self.vision))
        with patch("bot_engine.views.generate_why_useful", return_value="Fresh AI text"):
            response = self.client.get(
                reverse("poster_why_useful_for_group", args=[self.poster.pk]), {"group_id": self.vision.pk},
            )
        self.assertEqual(response.json()["why_useful"], "Fresh AI text")

    def test_a_group_removed_in_the_same_save_keeps_its_old_text(self):
        self.sign_in(self.member)
        self.edit(**{
            "groups_submitted": "1", "group_ids": [self.vision.pk, self.bare.pk],
            f"why_useful_{self.robotics.pk}": "Should not be saved",
        })
        self.assertEqual(set(self.poster.groups.values_list("pk", flat=True)), {self.vision.pk, self.bare.pk})
        self.assertEqual(self.group_text(self.robotics), "Robotics text")

    def test_the_dashboard_shows_the_users_default_group_text(self):
        self.sign_in(self.member)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Vision text")
        self.assertNotContains(response, "General copy")
        PosterGroupWhyUseful.objects.filter(poster=self.poster, group=self.vision).delete()
        self.assertContains(self.client.get(reverse("dashboard")), "General copy")

    def test_the_default_group_is_the_primary_else_the_first_by_name(self):
        from .views import _attach_why_useful_shown
        self.assertEqual(_attach_why_useful_shown(self.member, [self.poster])[0].why_useful_shown, "Vision text")
        self.poster.groups.remove(self.vision)
        poster = ResearchPoster.objects.get(pk=self.poster.pk)
        self.assertEqual(_attach_why_useful_shown(self.member, [poster])[0].why_useful_shown, "Robotics text")
        self.assertEqual(_attach_why_useful_shown(self.admin, [poster])[0].why_useful_shown, "General copy")

    def test_a_user_outside_the_papers_groups_still_edits_the_general_copy(self):
        self.sign_in(self.admin)
        response = self.client.get(reverse("edit_poster", args=[self.poster.pk]))
        self.assertContains(response, 'name="why_useful"')
        self.client.post(reverse("edit_poster", args=[self.poster.pk]), {
            "title": self.poster.title, "authors": "An Author", "summary": "A summary.",
            "category": "other", "validation_status": "approved", "why_useful": "Admin general copy",
        })
        self.poster.refresh_from_db()
        self.assertEqual(self.poster.why_useful, "Admin general copy")


@override_settings(
    SHIBBOLETH_AUTH=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class GroupDeleteWarningTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.doomed = ResearchGroup.objects.create(name="Doomed")
        cls.other = ResearchGroup.objects.create(name="Other")
        cls.admin = User.objects.create_user(username="admin", is_superuser=True)
        UserGroupMembership.objects.create(user=cls.admin, group=cls.doomed, is_primary=True)
        for first, last in (("Anna", "Bianchi"), ("Bruno", "Rossi"), ("Carla", "Verdi"), ("Dario", "Neri"), ("Elena", "Gallo")):
            user = User.objects.create_user(username=first.lower(), first_name=first, last_name=last)
            UserGroupMembership.objects.create(user=user, group=cls.doomed, is_primary=True)
        cls.in_both = User.objects.create_user(username="both", first_name="Zeno", last_name="Both")
        UserGroupMembership.objects.create(user=cls.in_both, group=cls.doomed, is_primary=True)
        UserGroupMembership.objects.create(user=cls.in_both, group=cls.other)

        only_doomed = [ResearchPoster.objects.create(title=f"Only doomed {i}") for i in range(2)]
        shared = ResearchPoster.objects.create(title="Shared")
        for poster in only_doomed:
            poster.groups.add(cls.doomed)
        shared.groups.add(cls.doomed, cls.other)

    def warnings(self):
        from .views import _group_delete_warnings
        return _group_delete_warnings([self.doomed.pk, self.other.pk])

    def test_warning_counts_orphaned_papers_and_lists_stranded_users(self):
        warning = self.warnings()[self.doomed.pk]
        self.assertIn("2 papers will be left without any group", warning)
        self.assertIn("These users will be left without any group", warning)
        self.assertIn(": Anna Bianchi, Bruno Rossi, Carla Verdi and 2 others.", warning)
        self.assertNotIn("Zeno", warning)

    def test_group_whose_deletion_strands_nothing_has_no_warning(self):
        self.assertNotIn(self.other.pk, self.warnings())

    def test_singular_wording_and_no_overflow_suffix(self):
        UserGroupMembership.objects.filter(group=self.doomed, user__username__in=["anna", "bruno", "carla", "dario"]).delete()
        ResearchPoster.objects.filter(title="Only doomed 1").delete()
        warning = self.warnings()[self.doomed.pk]
        self.assertIn("1 paper will be left", warning)
        self.assertIn("This user will be left without any group and will no longer be able to upload or see posters: Elena Gallo.", warning)
        self.assertNotIn("others", warning)

    def test_group_list_puts_the_warning_in_the_delete_dialog(self):
        self.client.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get(reverse("group_list"))
        self.assertContains(response, 'data-confirm-warning="⚠ 2 papers will be left without any group')


class PrimaryGroupPromotionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta
        from django.utils import timezone

        cls.user = get_user_model().objects.create_user(username="promoted")
        cls.primary, cls.oldest, cls.newest = (
            ResearchGroup.objects.create(name=name) for name in ("Primary", "Oldest", "Newest")
        )
        now = timezone.now()
        for group, age_days, is_primary in ((cls.primary, 1, True), (cls.oldest, 10, False), (cls.newest, 0, False)):
            membership = UserGroupMembership.objects.create(user=cls.user, group=group, is_primary=is_primary)
            UserGroupMembership.objects.filter(pk=membership.pk).update(joined_at=now - timedelta(days=age_days))

    def primary_group(self):
        return UserGroupMembership.objects.get(user=self.user, is_primary=True).group

    def test_removing_the_primary_promotes_the_oldest_remaining_group(self):
        UserGroupMembership.objects.get(user=self.user, group=self.primary).delete()
        self.assertEqual(self.primary_group(), self.oldest)

    def test_deleting_the_primary_group_promotes_the_oldest_remaining_group(self):
        self.primary.delete()
        self.assertEqual(self.primary_group(), self.oldest)

    def test_removing_a_secondary_group_keeps_the_primary(self):
        UserGroupMembership.objects.get(user=self.user, group=self.oldest).delete()
        self.assertEqual(self.primary_group(), self.primary)

    def test_removing_the_last_group_leaves_no_membership(self):
        UserGroupMembership.objects.filter(user=self.user).exclude(group=self.primary).delete()
        UserGroupMembership.objects.get(user=self.user, group=self.primary).delete()
        self.assertFalse(UserGroupMembership.objects.filter(user=self.user).exists())


class ThumbnailOrientationTests(TestCase):
    def test_thumbnail_applies_exif_orientation(self):
        import io as _io
        from PIL import Image
        from django.core.files.base import ContentFile

        # Landscape pixels (400x200) tagged "rotate 90 CW to display" => displays as portrait.
        img = Image.new("RGB", (400, 200), "red")
        exif = Image.Exif()
        exif[0x0112] = 6
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)

        poster = ResearchPoster(title="t")
        poster.image.save("orient.jpg", ContentFile(buf.getvalue()), save=False)
        poster.generate_thumbnail(save=False)

        with Image.open(poster.thumbnail) as thumb:
            self.assertLess(thumb.width, thumb.height)
        poster.image.delete(save=False)
        poster.thumbnail.delete(save=False)


@override_settings(ADMIN_CONTACT_EMAIL="posterhub-admin@example.org")
class BotAdminContactTests(TestCase):

    def linking_reply(self, platform, email):
        from . import views
        with patch.object(views, "send_message") as send:
            views._handle_link_command(platform, "12345", email)
        return send.call_args.args[2]

    def test_unknown_email_reply_points_to_the_admin_contact(self):
        for platform in ("telegram", "whatsapp"):
            with self.subTest(platform=platform):
                self.assertIn("posterhub-admin@example.org", self.linking_reply(platform, "nobody@example.org"))

    def test_linked_user_without_group_is_told_whom_to_contact(self):
        get_user_model().objects.create_user(username="botless", email="botless@example.org")
        for platform in ("telegram", "whatsapp"):
            with self.subTest(platform=platform):
                self.assertIn("posterhub-admin@example.org", self.linking_reply(platform, "botless@example.org"))

    def test_contact_is_omitted_when_not_configured(self):
        with override_settings(ADMIN_CONTACT_EMAIL=""):
            self.assertNotIn("Contact", self.linking_reply("telegram", "nobody@example.org"))


@override_settings(
    SHIBBOLETH_AUTH=False,
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class ConferenceInstitutionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.member = get_user_model().objects.create_user(username="conf_member")
        group = ResearchGroup.objects.create(name="Imaging")
        UserGroupMembership.objects.create(user=cls.member, group=group, is_primary=True)
        cls.poster = ResearchPoster.objects.create(
            title="Conference paper", authors="An Author", summary="A summary.",
            conference="MICCAI 2023", institution="Old Institute",
        )
        cls.poster.groups.add(group)
        ProceedingsSource.objects.create(conference="CVPR", year=2026, url="https://example.org/cvpr",
                                         parser="cvf_html")

    def setUp(self):
        self.client.force_login(self.member, backend="django.contrib.auth.backends.ModelBackend")

    def test_edit_page_offers_known_conferences_and_saves_both_fields(self):
        url = reverse("edit_poster", args=[self.poster.pk])
        response = self.client.get(url)
        self.assertContains(response, 'list="conferenceOptions"')
        self.assertContains(response, '<option value="CVPR 2026">')
        self.assertContains(response, '<option value="MICCAI 2023">')
        self.client.post(url, {
            "title": self.poster.title, "authors": "An Author", "summary": "A summary.",
            "category": "other", "validation_status": "pending",
            "conference": " MICCAI 2026 ", "institution": "University of Modena and Reggio Emilia",
        })
        self.poster.refresh_from_db()
        self.assertEqual((self.poster.conference, self.poster.institution),
                         ("MICCAI 2026", "University of Modena and Reggio Emilia"))

    def test_conference_is_a_chip_everywhere_and_institution_only_on_the_paper_page(self):
        detail = self.client.get(reverse("poster_detail", args=[self.poster.pk]))
        self.assertContains(detail, 'class="detail-tag-item conference-chip"')
        self.assertContains(detail, '<div class="detail-institution">Old Institute</div>', html=True)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, 'data-conf="MICCAI 2023"')
        self.assertNotContains(dashboard, "Old Institute")

    def test_dashboard_search_matches_conference_and_institution(self):
        for term in ("miccai 2023", "old institute"):
            with self.subTest(term=term):
                response = self.client.get(reverse("dashboard"), {"search": term})
                self.assertContains(response, "Conference paper")
