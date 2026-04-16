from django.test import SimpleTestCase

from api.permissions import BabyBuddyDjangoModelPermissions


class PermissionsContractTests(SimpleTestCase):
    # Component: api/permissions.py
    # Intent: HTTP methods should map to the expected Django model permissions.

    def test_get_requires_view_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["GET"],
            ["%(app_label)s.view_%(model_name)s"],
        )

    def test_options_requires_add_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["OPTIONS"],
            ["%(app_label)s.add_%(model_name)s"],
        )

    def test_head_requires_no_permission(self):
        self.assertEqual(BabyBuddyDjangoModelPermissions.perms_map["HEAD"], [])

    def test_post_requires_add_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["POST"],
            ["%(app_label)s.add_%(model_name)s"],
        )

    def test_patch_requires_change_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["PATCH"],
            ["%(app_label)s.change_%(model_name)s"],
        )

    def test_delete_requires_delete_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["DELETE"],
            ["%(app_label)s.delete_%(model_name)s"],
        )

    def test_put_is_not_supported_in_custom_permission_map(self):
        self.assertNotIn("PUT", BabyBuddyDjangoModelPermissions.perms_map)
